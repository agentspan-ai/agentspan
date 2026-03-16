/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.compiler;

import com.netflix.conductor.common.metadata.workflow.WorkflowDef;
import com.netflix.conductor.common.metadata.workflow.WorkflowTask;
import dev.agentspan.runtime.model.*;
import dev.agentspan.runtime.util.JavaScriptBuilder;
import dev.agentspan.runtime.util.ModelParser;
import dev.agentspan.runtime.util.ModelParser.ParsedModel;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.*;
import java.util.stream.Collectors;

import static dev.agentspan.runtime.compiler.AgentCompiler.ref;

/**
 * Compiles multi-agent strategies into Conductor workflows.
 * Mirrors python/src/conductor/agents/compiler/multi_agent_compiler.py.
 */
public class MultiAgentCompiler {

    private static final Logger log = LoggerFactory.getLogger(MultiAgentCompiler.class);

    private final AgentCompiler agentCompiler;

    public MultiAgentCompiler(AgentCompiler agentCompiler) {
        this.agentCompiler = agentCompiler;
    }

    public WorkflowDef compile(AgentConfig config) {
        // Validate uniqueness
        if (config.getAgents() != null) {
            List<String> names = config.getAgents().stream().map(AgentConfig::getName).toList();
            Set<String> unique = new HashSet<>(names);
            if (unique.size() != names.size()) {
                throw new IllegalArgumentException(
                    "Duplicate agent names in '" + config.getName() + "'. Each sub-agent must have a unique name."
                );
            }
        }

        WorkflowDef strategyWf = compileStrategy(config);

        // Wrap with guardrails if needed
        List<GuardrailConfig> outputGuardrails = agentCompiler.getOutputGuardrails(config);
        if (!outputGuardrails.isEmpty()) {
            return wrapWithGuardrails(config, strategyWf);
        }
        return strategyWf;
    }

    private WorkflowDef compileStrategy(AgentConfig config) {
        String strategy = config.getStrategy() != null ? config.getStrategy() : "handoff";
        return switch (strategy) {
            case "handoff" -> compileHandoff(config);
            case "sequential" -> compileSequential(config);
            case "parallel" -> compileParallel(config);
            case "router" -> compileRouter(config);
            case "round_robin" -> compileRotation(config, false);
            case "random" -> compileRotation(config, true);
            case "swarm" -> compileSwarm(config);
            case "manual" -> compileManual(config);
            default -> throw new IllegalArgumentException("Unknown strategy: " + strategy);
        };
    }

    // ── Handoff strategy ────────────────────────────────────────────

    private WorkflowDef compileHandoff(AgentConfig config) {
        ParsedModel parsed = ModelParser.parse(config.getModel());
        WorkflowDef wf = agentCompiler.createWorkflow(config);
        wf.setDescription("Handoff agent: " + config.getName());

        String instructions = resolveInstructions(config);
        List<AgentConfig> agents = config.getAgents();
        List<String> agentNames = agents.stream().map(AgentConfig::getName).toList();
        int maxTurns = config.getMaxTurns() > 0 ? config.getMaxTurns() : 25;
        String loopRef = config.getName() + "_loop";
        String routerRef = config.getName() + "_router";

        // Build agent descriptions for routing prompt
        StringBuilder agentsInfo = new StringBuilder();
        for (AgentConfig a : agents) {
            String desc = a.getDescription() != null && !a.getDescription().isEmpty()
                ? a.getDescription()
                : (a.getInstructions() instanceof String ? (String) a.getInstructions() : a.getName());
            agentsInfo.append("- ").append(a.getName()).append(": ").append(desc).append("\n");
        }

        // 1. Init: seed conversation variable with prompt
        WorkflowTask initVar = new WorkflowTask();
        initVar.setType("SET_VARIABLE");
        initVar.setTaskReferenceName(config.getName() + "_init");
        String introductions = buildIntroductions(config);
        if (!introductions.isEmpty()) {
            initVar.setInputParameters(Map.of("conversation", introductions + "\n\n${workflow.input.prompt}"));
        } else {
            initVar.setInputParameters(Map.of("conversation", "${workflow.input.prompt}"));
        }

        // 2. Router LLM — reads conversation, picks agent or says DONE
        String systemPrompt = (instructions.isEmpty() ? "" : instructions + "\n\n") +
            "You are a coordinator that delegates tasks to specialized agents.\n\n" +
            "Available agents:\n" + agentsInfo +
            "\nBased on the conversation so far, decide the next action:\n" +
            "- Carefully analyze the user's COMPLETE request. It may contain MULTIPLE parts " +
            "that require DIFFERENT agents.\n" +
            "- If ANY part of the user's request has NOT yet been addressed by an appropriate agent, " +
            "respond with ONLY the name of the agent that should handle the unaddressed part (one of: " +
            String.join(", ", agentNames) + ")\n" +
            "- ONLY if ALL parts of the user's request have been fully addressed, respond with " +
            "ONLY the word DONE\n\n" +
            "Important: Review the full conversation to check which parts have been handled. " +
            "Do NOT say DONE until every distinct part of the request has received a response " +
            "from a suitable agent.\n\n" +
            "Respond with a single word — either an agent name or DONE. No other text.";

        WorkflowTask routerLlm = buildIterativeRouterLlm(routerRef, parsed, systemPrompt);

        // 2b. Record routing decision in conversation so the router sees its own history
        String routeAnnotateRef = config.getName() + "_route_annotate";
        WorkflowTask routeAnnotate = new WorkflowTask();
        routeAnnotate.setType("INLINE");
        routeAnnotate.setTaskReferenceName(routeAnnotateRef);
        Map<String, Object> annotateInputs = new LinkedHashMap<>();
        annotateInputs.put("evaluatorType", "graaljs");
        annotateInputs.put("expression",
            "(function() { var d = $.decision; if (d === 'DONE') return $.prev; " +
            "return $.prev + '\\n\\n[coordinator -> ' + d + ']'; })()");
        annotateInputs.put("prev", "${workflow.variables.conversation}");
        annotateInputs.put("decision", ref(routerRef + ".output.result"));
        routeAnnotate.setInputParameters(annotateInputs);

        WorkflowTask routeAnnotateSet = new WorkflowTask();
        routeAnnotateSet.setType("SET_VARIABLE");
        routeAnnotateSet.setTaskReferenceName(config.getName() + "_route_set");
        routeAnnotateSet.setInputParameters(Map.of(
            "conversation", ref(routeAnnotateRef + ".output.result")
        ));

        // 3. Switch on router output
        WorkflowTask switchTask = new WorkflowTask();
        switchTask.setType("SWITCH");
        switchTask.setTaskReferenceName(config.getName() + "_switch");
        switchTask.setEvaluatorType("value-param");
        switchTask.setExpression("switchCaseValue");
        switchTask.setInputParameters(Map.of(
            "switchCaseValue", ref(routerRef + ".output.result")
        ));

        Map<String, List<WorkflowTask>> cases = new LinkedHashMap<>();
        for (int i = 0; i < agents.size(); i++) {
            AgentConfig sub = agents.get(i);
            List<WorkflowTask> caseTasks = buildHandoffCaseTasks(config, sub, i);
            cases.put(sub.getName(), caseTasks);
        }

        // DONE case: no-op inline task
        WorkflowTask doneTask = new WorkflowTask();
        doneTask.setType("INLINE");
        doneTask.setTaskReferenceName(config.getName() + "_done_noop");
        doneTask.setInputParameters(Map.of(
            "evaluatorType", "graaljs",
            "expression", "(function() { return {result: 'done'}; })()"
        ));
        cases.put("DONE", List.of(doneTask));

        switchTask.setDecisionCases(cases);

        // Default case: first agent (fallback for unexpected LLM output)
        if (!agents.isEmpty()) {
            AgentConfig firstAgent = agents.get(0);
            List<WorkflowTask> defaultTasks = buildHandoffCaseTasks(config, firstAgent, 0, "_default");
            switchTask.setDefaultCase(defaultTasks);
        }

        // 4. DoWhile loop: continue while iteration < max_turns AND router != DONE
        String termCondition = String.format(
            "if ( $.%s['iteration'] < %d && $.%s['result'] != 'DONE' ) { true; } else { false; }",
            loopRef, maxTurns, routerRef
        );
        Map<String, Object> loopInputs = new LinkedHashMap<>();
        loopInputs.put(loopRef, "${" + loopRef + "}");
        loopInputs.put(routerRef, "${" + routerRef + "}");
        WorkflowTask loop = agentCompiler.buildDoWhile(loopRef, termCondition,
            List.of(routerLlm, routeAnnotate, routeAnnotateSet, switchTask), loopInputs);

        // 5. Final answer LLM: synthesize from accumulated conversation
        WorkflowTask finalLlm = new WorkflowTask();
        finalLlm.setName("LLM_CHAT_COMPLETE");
        finalLlm.setTaskReferenceName(config.getName() + "_final");
        finalLlm.setType("LLM_CHAT_COMPLETE");
        Map<String, Object> finalInputs = new LinkedHashMap<>();
        finalInputs.put("llmProvider", parsed.getProvider());
        finalInputs.put("model", parsed.getModel());
        String finalSystemPrompt = (instructions.isEmpty() ? "" : instructions + "\n\n") +
            "Based on the work done by the agents above, provide your final response to the user. " +
            "IMPORTANT: Include ALL details from every agent's response — do NOT summarize or omit " +
            "code examples, technical specifications, or specific recommendations. " +
            "Organize the information coherently but preserve completeness.";
        finalInputs.put("messages", List.of(
            Map.of("role", "system", "message", finalSystemPrompt),
            Map.of("role", "user", "message", "${workflow.variables.conversation}")
        ));
        finalLlm.setInputParameters(finalInputs);

        wf.setTasks(List.of(initVar, loop, finalLlm));
        wf.setOutputParameters(Map.of("result", ref(config.getName() + "_final.output.result")));
        agentCompiler.applyTimeout(wf, config);
        return wf;
    }

    // ── Sequential strategy ─────────────────────────────────────────

    private WorkflowDef compileSequential(AgentConfig config) {
        WorkflowDef wf = agentCompiler.createWorkflow(config);
        wf.setDescription("Sequential pipeline: " + config.getName());

        List<WorkflowTask> tasks = new ArrayList<>();
        String prevOutputRef = "${workflow.input.prompt}";

        for (int i = 0; i < config.getAgents().size(); i++) {
            AgentConfig sub = config.getAgents().get(i);
            String taskRef = config.getName() + "_step_" + i + "_" + sub.getName();
            String mediaRef = i == 0 ? "${workflow.input.media}" : "${workflow.input.media}";

            WorkflowTask task = agentCompiler.compileSubAgent(sub, taskRef, prevOutputRef, mediaRef);
            tasks.add(task);

            // Get raw result ref
            String rawRef = AgentCompiler.subAgentResultRef(sub, taskRef);

            // For non-final stages, add null coercion
            // to prevent deserialization failures when output.result is null
            if (i < config.getAgents().size() - 1) {
                String coerceRef = taskRef + "_coerce";
                tasks.add(AgentCompiler.createCoerceTask(rawRef, coerceRef));
                String coercedRef = AgentCompiler.coercedRef(coerceRef);

                // Gate check: if this stage has a gate, insert INLINE + SWITCH
                if (sub.getGate() != null) {
                    String gateRef = config.getName() + "_gate_" + i;
                    WorkflowTask gateTask = GateCompiler.compileGate(
                            sub.getGate(), gateRef, coercedRef
                    );
                    tasks.add(gateTask);

                    // SWITCH: "continue" → remaining stages, "stop" → end pipeline
                    WorkflowTask switchTask = new WorkflowTask();
                    switchTask.setType("SWITCH");
                    switchTask.setTaskReferenceName(config.getName() + "_gate_switch_" + i);
                    switchTask.setEvaluatorType("value-param");
                    switchTask.setExpression("switchCaseValue");
                    switchTask.setInputParameters(Map.of(
                            "switchCaseValue", "${" + gateRef + ".output.result.decision}"
                    ));

                    // "continue" case: compile remaining stages recursively
                    List<WorkflowTask> continueTasks = compileRemainingStages(
                            config, i + 1, coercedRef
                    );
                    switchTask.setDecisionCases(Map.of(
                            "continue", continueTasks
                    ));
                    // "stop" (default): no-op — pipeline returns current output
                    switchTask.setDefaultCase(List.of());

                    tasks.add(switchTask);

                    // After the SWITCH, add an output-selector INLINE task.
                    // It walks the stages in reverse and returns the first non-null result.
                    // This ensures the workflow output is always the deepest stage that ran.
                    String selectorRef = config.getName() + "_output_selector";
                    WorkflowTask selector = buildOutputSelector(config, i, selectorRef);
                    tasks.add(selector);

                    String selectorOutputRef = "${" + selectorRef + ".output.result}";
                    wf.setTasks(tasks);
                    wf.setOutputParameters(Map.of("result", selectorOutputRef));
                    agentCompiler.applyTimeout(wf, config);
                    return wf;
                }

                prevOutputRef = coercedRef;
            } else {
                prevOutputRef = rawRef;
            }
        }

        wf.setTasks(tasks);
        wf.setOutputParameters(Map.of("result", prevOutputRef));
        agentCompiler.applyTimeout(wf, config);
        return wf;
    }

    /**
     * Compile the remaining stages of a sequential pipeline (from startIndex onward).
     * Used when a gate creates a SWITCH — the "continue" branch contains the rest.
     */
    private List<WorkflowTask> compileRemainingStages(
            AgentConfig config, int startIndex, String prevOutputRef) {

        List<WorkflowTask> tasks = new ArrayList<>();

        for (int i = startIndex; i < config.getAgents().size(); i++) {
            AgentConfig sub = config.getAgents().get(i);
            String taskRef = config.getName() + "_step_" + i + "_" + sub.getName();
            String mediaRef = "${workflow.input.media}";

            WorkflowTask task = agentCompiler.compileSubAgent(sub, taskRef, prevOutputRef, mediaRef);
            tasks.add(task);

            String rawRef = AgentCompiler.subAgentResultRef(sub, taskRef);

            if (i < config.getAgents().size() - 1) {
                String coerceRef = taskRef + "_coerce";
                tasks.add(AgentCompiler.createCoerceTask(rawRef, coerceRef));
                String coercedRef = AgentCompiler.coercedRef(coerceRef);

                // Nested gate
                if (sub.getGate() != null) {
                    String gateRef = config.getName() + "_gate_" + i;
                    WorkflowTask gateTask = GateCompiler.compileGate(
                            sub.getGate(), gateRef, coercedRef
                    );
                    tasks.add(gateTask);

                    WorkflowTask switchTask = new WorkflowTask();
                    switchTask.setType("SWITCH");
                    switchTask.setTaskReferenceName(config.getName() + "_gate_switch_" + i);
                    switchTask.setEvaluatorType("value-param");
                    switchTask.setExpression("switchCaseValue");
                    switchTask.setInputParameters(Map.of(
                            "switchCaseValue", "${" + gateRef + ".output.result.decision}"
                    ));

                    List<WorkflowTask> continueTasks = compileRemainingStages(
                            config, i + 1, coercedRef
                    );
                    switchTask.setDecisionCases(Map.of(
                            "continue", continueTasks
                    ));
                    switchTask.setDefaultCase(List.of());
                    tasks.add(switchTask);
                    return tasks;
                }

                prevOutputRef = coercedRef;
            } else {
                prevOutputRef = rawRef;
            }
        }

        return tasks;
    }

    /**
     * Build an INLINE task that selects the deepest stage output that actually ran.
     * Walks stages in reverse: the first non-null result wins.
     * When a gate stops the pipeline, later stages never execute and their refs are null.
     */
    private WorkflowTask buildOutputSelector(AgentConfig config, int firstGateIndex, String refName) {
        // Build JS that checks each stage in reverse order
        StringBuilder sb = new StringBuilder();
        for (int i = config.getAgents().size() - 1; i >= 0; i--) {
            sb.append("if ($.s").append(i).append(" != null && $.s").append(i).append(" !== '') return $.s").append(i).append("; ");
        }
        sb.append("return '';");

        String script = JavaScriptBuilder.iife(sb.toString());

        Map<String, Object> inputs = new LinkedHashMap<>();
        inputs.put("evaluatorType", "graaljs");
        inputs.put("expression", script);

        // Add each stage's output as s0, s1, s2, ...
        for (int i = 0; i < config.getAgents().size(); i++) {
            AgentConfig sub = config.getAgents().get(i);
            String taskRef = config.getName() + "_step_" + i + "_" + sub.getName();
            String resultRef = AgentCompiler.subAgentResultRef(sub, taskRef);
            inputs.put("s" + i, resultRef);
        }

        WorkflowTask task = new WorkflowTask();
        task.setType("INLINE");
        task.setTaskReferenceName(refName);
        task.setInputParameters(inputs);
        return task;
    }

    // ── Parallel strategy ───────────────────────────────────────────

    private WorkflowDef compileParallel(AgentConfig config) {
        WorkflowDef wf = agentCompiler.createWorkflow(config);
        wf.setDescription("Parallel agents: " + config.getName());

        // Build fork task
        WorkflowTask forkTask = new WorkflowTask();
        forkTask.setType("FORK_JOIN");
        forkTask.setTaskReferenceName(config.getName() + "_fork");

        List<List<WorkflowTask>> forkTasks = new ArrayList<>();
        List<String> joinOn = new ArrayList<>();

        for (int i = 0; i < config.getAgents().size(); i++) {
            AgentConfig sub = config.getAgents().get(i);
            String taskRef = config.getName() + "_parallel_" + i + "_" + sub.getName();
            WorkflowTask task = agentCompiler.compileSubAgent(sub, taskRef, "${workflow.input.prompt}", "${workflow.input.media}");
            forkTasks.add(List.of(task));
            joinOn.add(taskRef);
        }
        forkTask.setForkTasks(forkTasks);
        forkTask.setJoinOn(joinOn);

        // Join task — joinOn on both fork and join (matches Python SDK toJSON)
        WorkflowTask joinTask = new WorkflowTask();
        joinTask.setType("JOIN");
        joinTask.setTaskReferenceName(config.getName() + "_fork_join");
        joinTask.setJoinOn(joinOn);

        // INLINE task to aggregate per-agent results into a consistent format:
        //   { "result": "<joined string>", "subResults": { "agentName": "output", ... } }
        WorkflowTask aggregateTask = new WorkflowTask();
        aggregateTask.setType("INLINE");
        aggregateTask.setTaskReferenceName(config.getName() + "_aggregate");
        Map<String, Object> aggInputs = new LinkedHashMap<>();
        aggInputs.put("evaluatorType", "graaljs");

        // Pass each agent's result as a named input
        Map<String, Object> agentResults = new LinkedHashMap<>();
        for (int i = 0; i < config.getAgents().size(); i++) {
            AgentConfig sub = config.getAgents().get(i);
            String taskRef = config.getName() + "_parallel_" + i + "_" + sub.getName();
            agentResults.put(sub.getName(), AgentCompiler.subAgentResultRef(sub, taskRef));
        }
        aggInputs.put("agentResults", agentResults);

        // Build the aggregation script
        List<String> agentNames = config.getAgents().stream()
            .map(AgentConfig::getName)
            .collect(java.util.stream.Collectors.toList());
        aggInputs.put("expression", buildParallelAggregateScript(agentNames));
        aggregateTask.setInputParameters(aggInputs);

        wf.setTasks(List.of(forkTask, joinTask, aggregateTask));

        // Output references the INLINE task's result
        String aggRef = config.getName() + "_aggregate";
        wf.setOutputParameters(Map.of(
            "result", "${" + aggRef + ".output.result.result}",
            "subResults", "${" + aggRef + ".output.result.subResults}"
        ));
        agentCompiler.applyTimeout(wf, config);
        return wf;
    }

    /**
     * Build a GraalJS script that aggregates parallel agent results into a
     * consistent output format with a joined string result and per-agent subResults.
     */
    private String buildParallelAggregateScript(List<String> agentNames) {
        StringBuilder sb = new StringBuilder();
        sb.append("(function() {\n");
        sb.append("  var results = $.agentResults;\n");
        sb.append("  var subResults = {};\n");
        sb.append("  var parts = [];\n");
        for (String name : agentNames) {
            sb.append("  var v_").append(name).append(" = results['").append(name).append("'];\n");
            sb.append("  subResults['").append(name).append("'] = (v_").append(name).append(" != null) ? String(v_").append(name).append(") : '';\n");
            sb.append("  if (v_").append(name).append(" != null && String(v_").append(name).append(") !== '') {\n");
            sb.append("    parts.push('[").append(name).append("]: ' + String(v_").append(name).append("));\n");
            sb.append("  }\n");
        }
        sb.append("  return { result: parts.join('\\n\\n'), subResults: subResults };\n");
        sb.append("})();");
        return sb.toString();
    }

    // ── Router strategy ─────────────────────────────────────────────

    private WorkflowDef compileRouter(AgentConfig config) {
        ParsedModel parsed = ModelParser.parse(config.getModel());
        WorkflowDef wf = agentCompiler.createWorkflow(config);
        wf.setDescription("Router agent: " + config.getName());

        List<AgentConfig> agents = config.getAgents();
        List<String> agentNames = agents.stream().map(AgentConfig::getName).toList();
        int maxTurns = config.getMaxTurns() > 0 ? config.getMaxTurns() : 25;
        String loopRef = config.getName() + "_loop";
        String routerRef = config.getName() + "_router";

        StringBuilder agentsInfo = new StringBuilder();
        for (AgentConfig a : agents) {
            String desc = a.getDescription() != null && !a.getDescription().isEmpty()
                ? a.getDescription()
                : (a.getInstructions() instanceof String ? (String) a.getInstructions() : a.getName());
            agentsInfo.append("- ").append(a.getName()).append(": ").append(desc).append("\n");
        }

        // 1. Init: seed conversation variable
        WorkflowTask initVar = new WorkflowTask();
        initVar.setType("SET_VARIABLE");
        initVar.setTaskReferenceName(config.getName() + "_init");
        String introductions = buildIntroductions(config);
        if (!introductions.isEmpty()) {
            initVar.setInputParameters(Map.of("conversation", introductions + "\n\n${workflow.input.prompt}"));
        } else {
            initVar.setInputParameters(Map.of("conversation", "${workflow.input.prompt}"));
        }

        // 2. Build router task (supports WorkerRef, AgentConfig, or fallback)
        Object router = config.getRouter();

        // Deserialize router from Map to typed object if needed
        if (router instanceof Map<?, ?> routerMap) {
            if (routerMap.containsKey("taskName")) {
                com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
                router = mapper.convertValue(routerMap, WorkerRef.class);
            } else if (routerMap.containsKey("model") || routerMap.containsKey("name")) {
                com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
                router = mapper.convertValue(routerMap, AgentConfig.class);
            }
        }

        WorkflowTask routerTask;
        if (router instanceof WorkerRef workerRef) {
            // Function-based router -> SIMPLE task reading conversation
            routerTask = new WorkflowTask();
            routerTask.setName(workerRef.getTaskName());
            routerTask.setTaskReferenceName(routerRef);
            routerTask.setType("SIMPLE");
            Map<String, Object> workerInputs = new LinkedHashMap<>();
            workerInputs.put("prompt", "${workflow.variables.conversation}");
            workerInputs.put("conversation", "${workflow.variables.conversation}");
            routerTask.setInputParameters(workerInputs);
            // Worker must return output.result = agent_name or "DONE"
        } else {
            // LLM-based router (AgentConfig or fallback to parent model)
            ParsedModel routerParsed;
            String routerInstr;
            if (router instanceof AgentConfig routerAgent) {
                routerParsed = ModelParser.parse(routerAgent.getModel());
                routerInstr = resolveInstructions(routerAgent);
            } else {
                routerParsed = parsed;
                routerInstr = resolveInstructions(config);
            }
            String systemPrompt = (routerInstr.isEmpty() ? "" : routerInstr + "\n\n") +
                "You are a coordinator that delegates tasks to specialized agents.\n\n" +
                "Available agents:\n" + agentsInfo +
                "\nBased on the conversation so far, decide the next action:\n" +
                "- Carefully analyze the user's COMPLETE request. It may contain MULTIPLE parts " +
                "that require DIFFERENT agents.\n" +
                "- If ANY part of the user's request has NOT yet been addressed by an appropriate agent, " +
                "respond with ONLY the name of the agent that should handle the unaddressed part (one of: " +
                String.join(", ", agentNames) + ")\n" +
                "- ONLY if ALL parts of the user's request have been fully addressed, respond with " +
                "ONLY the word DONE\n\n" +
                "Important: Review the full conversation to check which parts have been handled. " +
                "Do NOT say DONE until every distinct part of the request has received a response " +
                "from a suitable agent.\n\n" +
                "Respond with a single word — either an agent name or DONE. No other text.";
            routerTask = buildIterativeRouterLlm(routerRef, routerParsed, systemPrompt);
        }

        // 2b. Record routing decision in conversation
        String routeAnnotateRef = config.getName() + "_route_annotate";
        WorkflowTask routeAnnotate = new WorkflowTask();
        routeAnnotate.setType("INLINE");
        routeAnnotate.setTaskReferenceName(routeAnnotateRef);
        Map<String, Object> annotateInputs = new LinkedHashMap<>();
        annotateInputs.put("evaluatorType", "graaljs");
        annotateInputs.put("expression",
            "(function() { var d = $.decision; if (d === 'DONE') return $.prev; " +
            "return $.prev + '\\n\\n[coordinator -> ' + d + ']'; })()");
        annotateInputs.put("prev", "${workflow.variables.conversation}");
        annotateInputs.put("decision", ref(routerRef + ".output.result"));
        routeAnnotate.setInputParameters(annotateInputs);

        WorkflowTask routeAnnotateSet = new WorkflowTask();
        routeAnnotateSet.setType("SET_VARIABLE");
        routeAnnotateSet.setTaskReferenceName(config.getName() + "_route_set");
        routeAnnotateSet.setInputParameters(Map.of(
            "conversation", ref(routeAnnotateRef + ".output.result")
        ));

        // 3. Switch on router output
        WorkflowTask switchTask = new WorkflowTask();
        switchTask.setType("SWITCH");
        switchTask.setTaskReferenceName(config.getName() + "_switch");
        switchTask.setEvaluatorType("value-param");
        switchTask.setExpression("switchCaseValue");
        switchTask.setInputParameters(Map.of(
            "switchCaseValue", ref(routerRef + ".output.result")
        ));

        Map<String, List<WorkflowTask>> cases = new LinkedHashMap<>();
        for (int i = 0; i < agents.size(); i++) {
            AgentConfig sub = agents.get(i);
            List<WorkflowTask> caseTasks = buildHandoffCaseTasks(config, sub, i);
            cases.put(sub.getName(), caseTasks);
        }

        // DONE case: no-op
        WorkflowTask doneTask = new WorkflowTask();
        doneTask.setType("INLINE");
        doneTask.setTaskReferenceName(config.getName() + "_done_noop");
        doneTask.setInputParameters(Map.of(
            "evaluatorType", "graaljs",
            "expression", "(function() { return {result: 'done'}; })()"
        ));
        cases.put("DONE", List.of(doneTask));

        switchTask.setDecisionCases(cases);

        // Default case: first agent fallback
        if (!agents.isEmpty()) {
            AgentConfig firstAgent = agents.get(0);
            List<WorkflowTask> defaultTasks = buildHandoffCaseTasks(config, firstAgent, 0, "_default");
            switchTask.setDefaultCase(defaultTasks);
        }

        // 4. DoWhile loop
        String termCondition = String.format(
            "if ( $.%s['iteration'] < %d && $.%s['result'] != 'DONE' ) { true; } else { false; }",
            loopRef, maxTurns, routerRef
        );
        Map<String, Object> loopInputs = new LinkedHashMap<>();
        loopInputs.put(loopRef, "${" + loopRef + "}");
        loopInputs.put(routerRef, "${" + routerRef + "}");
        WorkflowTask loop = agentCompiler.buildDoWhile(loopRef, termCondition,
            List.of(routerTask, routeAnnotate, routeAnnotateSet, switchTask), loopInputs);

        // 5. Final answer LLM
        WorkflowTask finalLlm = new WorkflowTask();
        finalLlm.setName("LLM_CHAT_COMPLETE");
        finalLlm.setTaskReferenceName(config.getName() + "_final");
        finalLlm.setType("LLM_CHAT_COMPLETE");
        Map<String, Object> finalInputs = new LinkedHashMap<>();
        finalInputs.put("llmProvider", parsed.getProvider());
        finalInputs.put("model", parsed.getModel());
        String instructions = resolveInstructions(config);
        String finalSystemPrompt = (instructions.isEmpty() ? "" : instructions + "\n\n") +
            "Based on the work done by the agents above, provide your final response to the user. " +
            "IMPORTANT: Include ALL details from every agent's response — do NOT summarize or omit " +
            "code examples, technical specifications, or specific recommendations. " +
            "Organize the information coherently but preserve completeness.";
        finalInputs.put("messages", List.of(
            Map.of("role", "system", "message", finalSystemPrompt),
            Map.of("role", "user", "message", "${workflow.variables.conversation}")
        ));
        finalLlm.setInputParameters(finalInputs);

        wf.setTasks(List.of(initVar, loop, finalLlm));
        wf.setOutputParameters(Map.of("result", ref(config.getName() + "_final.output.result")));
        agentCompiler.applyTimeout(wf, config);
        return wf;
    }

    // ── Round-robin / Random (shared rotation) ──────────────────────

    private WorkflowDef compileRotation(AgentConfig config, boolean random) {
        WorkflowDef wf = agentCompiler.createWorkflow(config);
        String label = random ? "Random" : "Round-Robin";
        wf.setDescription(label + " discussion: " + config.getName());

        int numAgents = config.getAgents().size();
        String loopRef = config.getName() + "_loop";
        int maxTurns = config.getMaxTurns() > 0 ? config.getMaxTurns() : 25;

        // 1. Init: seed conversation
        WorkflowTask initVar = new WorkflowTask();
        initVar.setType("SET_VARIABLE");
        initVar.setTaskReferenceName(config.getName() + "_init");
        Map<String, Object> initInputs = new LinkedHashMap<>();
        String introductions = buildIntroductions(config);
        if (!introductions.isEmpty()) {
            initInputs.put("conversation", introductions + "\n\n${workflow.input.prompt}");
        } else {
            initInputs.put("conversation", "${workflow.input.prompt}");
        }
        if (config.getAllowedTransitions() != null) {
            initInputs.put("last_agent", "0");
        }
        initVar.setInputParameters(initInputs);

        // 2a. Select agent
        String selectScript = buildSelectScript(config, numAgents, loopRef, random);
        WorkflowTask selectTask = new WorkflowTask();
        selectTask.setType("INLINE");
        selectTask.setTaskReferenceName(config.getName() + "_select");
        Map<String, Object> selectInputs = new LinkedHashMap<>();
        selectInputs.put("evaluatorType", "graaljs");
        selectInputs.put("expression", selectScript);
        selectInputs.put("iteration", ref(loopRef + ".iteration"));
        if (config.getAllowedTransitions() != null) {
            selectInputs.put("last_agent", "${workflow.variables.last_agent}");
        }
        selectTask.setInputParameters(selectInputs);

        // 2b. Switch to selected agent
        WorkflowTask switchTask = new WorkflowTask();
        switchTask.setType("SWITCH");
        switchTask.setTaskReferenceName(config.getName() + "_switch");
        switchTask.setEvaluatorType("value-param");
        switchTask.setExpression("switchCaseValue");
        switchTask.setInputParameters(Map.of("switchCaseValue", ref(config.getName() + "_select.output.result")));

        Map<String, List<WorkflowTask>> cases = new LinkedHashMap<>();
        for (int i = 0; i < numAgents; i++) {
            AgentConfig sub = config.getAgents().get(i);
            List<WorkflowTask> caseTasks = buildRotationCaseTasks(config, sub, i, loopRef);
            cases.put(String.valueOf(i), caseTasks);
        }
        switchTask.setDecisionCases(cases);

        // 3. DoWhile loop
        String termCondition = String.format(
            "if ( $.%s['iteration'] < %d ) { true; } else { false; }",
            loopRef, maxTurns
        );
        Map<String, Object> loopInputs = Map.of(loopRef, "${" + loopRef + "}");
        WorkflowTask loop = agentCompiler.buildDoWhile(loopRef, termCondition, List.of(selectTask, switchTask), loopInputs);

        wf.setTasks(List.of(initVar, loop));
        wf.setOutputParameters(Map.of("result", "${workflow.variables.conversation}"));
        agentCompiler.applyTimeout(wf, config);
        return wf;
    }

    // ── Swarm strategy ──────────────────────────────────────────────

    private WorkflowDef compileSwarm(AgentConfig config) {
        WorkflowDef wf = agentCompiler.createWorkflow(config);
        wf.setDescription("Swarm orchestration: " + config.getName());

        int numAgents = config.getAgents().size();
        String loopRef = config.getName() + "_loop";
        int maxTurns = config.getMaxTurns() > 0 ? config.getMaxTurns() : 25;

        // Build allSwarmAgents list (parent + sub-agents) for transfer tool generation
        AgentConfig parentAsAgent = AgentConfig.builder()
            .name(config.getName())
            .model(config.getModel())
            .instructions(config.getInstructions())
            .tools(config.getTools())
            .guardrails(config.getGuardrails())
            .memory(config.getMemory())
            .temperature(config.getTemperature())
            .maxTokens(config.getMaxTokens())
            .thinkingConfig(config.getThinkingConfig())
            .build();

        List<AgentConfig> allSwarmAgents = new ArrayList<>();
        allSwarmAgents.add(parentAsAgent);
        allSwarmAgents.addAll(config.getAgents());

        // 1. Init — track conversation, active_agent, last_response, transfer state
        WorkflowTask initVar = new WorkflowTask();
        initVar.setType("SET_VARIABLE");
        initVar.setTaskReferenceName(config.getName() + "_init");
        Map<String, Object> initInputs = new LinkedHashMap<>();
        String introductions = buildIntroductions(config);
        initInputs.put("conversation", introductions.isEmpty()
            ? "${workflow.input.prompt}"
            : introductions + "\n\n${workflow.input.prompt}");
        initInputs.put("active_agent", "0");
        initInputs.put("last_response", "");
        initInputs.put("is_transfer", false);
        initInputs.put("transfer_to", "");
        initVar.setInputParameters(initInputs);

        // 2. Switch by active_agent
        WorkflowTask switchTask = new WorkflowTask();
        switchTask.setType("SWITCH");
        switchTask.setTaskReferenceName(config.getName() + "_switch");
        switchTask.setEvaluatorType("value-param");
        switchTask.setExpression("switchCaseValue");
        switchTask.setInputParameters(Map.of("switchCaseValue", "${workflow.variables.active_agent}"));

        // Parent agent as case "0", sub-agents shifted to 1, 2, ...
        Map<String, List<WorkflowTask>> cases = new LinkedHashMap<>();
        List<ToolConfig> parentTransferTools = buildTransferToolsFor(parentAsAgent, allSwarmAgents);
        cases.put("0", buildSwarmCaseTasks(config, parentAsAgent, 0, parentTransferTools));
        for (int i = 0; i < numAgents; i++) {
            AgentConfig sub = config.getAgents().get(i);
            List<ToolConfig> subTransferTools = buildTransferToolsFor(sub, allSwarmAgents);
            List<WorkflowTask> caseTasks = buildSwarmCaseTasks(config, sub, i + 1, subTransferTools);
            cases.put(String.valueOf(i + 1), caseTasks);
        }
        switchTask.setDecisionCases(cases);

        // 3. Handoff check worker — checks transfer first, then conditions
        String handoffRef = config.getName() + "_handoff_check";
        WorkflowTask handoffTask = new WorkflowTask();
        handoffTask.setName(config.getName() + "_handoff_check");
        handoffTask.setTaskReferenceName(handoffRef);
        handoffTask.setType("SIMPLE");
        Map<String, Object> handoffInputs = new LinkedHashMap<>();
        handoffInputs.put("result", "${workflow.variables.last_response}");
        handoffInputs.put("active_agent", "${workflow.variables.active_agent}");
        handoffInputs.put("conversation", "${workflow.variables.conversation}");
        handoffInputs.put("is_transfer", "${workflow.variables.is_transfer}");
        handoffInputs.put("transfer_to", "${workflow.variables.transfer_to}");
        handoffTask.setInputParameters(handoffInputs);

        // Update active_agent
        WorkflowTask updateActive = new WorkflowTask();
        updateActive.setType("SET_VARIABLE");
        updateActive.setTaskReferenceName(config.getName() + "_update_active");
        updateActive.setInputParameters(Map.of(
            "active_agent", ref(handoffRef + ".output.active_agent")
        ));

        // 4. DoWhile — early termination when no handoff triggers
        String termCondition = String.format(
            "if ( $.%s['iteration'] < %d && $.%s['handoff'] == true ) { true; } else { false; }",
            loopRef, maxTurns, handoffRef
        );
        Map<String, Object> loopInputs = new LinkedHashMap<>();
        loopInputs.put(loopRef, "${" + loopRef + "}");
        loopInputs.put(handoffRef, "${" + handoffRef + "}");
        WorkflowTask loop = agentCompiler.buildDoWhile(loopRef, termCondition,
            List.of(switchTask, handoffTask, updateActive), loopInputs);

        // 5. Final synthesis LLM: combine all agents' work into a coherent response
        WorkflowTask finalLlm = new WorkflowTask();
        finalLlm.setName("LLM_CHAT_COMPLETE");
        finalLlm.setTaskReferenceName(config.getName() + "_final");
        finalLlm.setType("LLM_CHAT_COMPLETE");
        Map<String, Object> finalInputs = new LinkedHashMap<>();
        ParsedModel parsed = ModelParser.parse(config.getModel());
        finalInputs.put("llmProvider", parsed.getProvider());
        finalInputs.put("model", parsed.getModel());
        String instructions = resolveInstructions(config);
        String finalSystemPrompt = (instructions.isEmpty() ? "" : instructions + "\n\n") +
            "Based on the work done by the agents above, provide your final response to the user. " +
            "IMPORTANT: Include ALL details from every agent's response — do NOT summarize or omit " +
            "code examples, technical specifications, or specific recommendations. " +
            "Organize the information coherently but preserve completeness.";
        finalInputs.put("messages", List.of(
            Map.of("role", "system", "message", finalSystemPrompt),
            Map.of("role", "user", "message", "${workflow.variables.conversation}")
        ));
        finalLlm.setInputParameters(finalInputs);

        wf.setTasks(List.of(initVar, loop, finalLlm));
        wf.setOutputParameters(Map.of("result", ref(config.getName() + "_final.output.result")));
        agentCompiler.applyTimeout(wf, config);
        return wf;
    }

    /**
     * Build transfer_to_<peer> tools for a swarm agent, excluding itself.
     */
    List<ToolConfig> buildTransferToolsFor(AgentConfig self, List<AgentConfig> allSwarmAgents) {
        List<ToolConfig> transferTools = new ArrayList<>();
        for (AgentConfig peer : allSwarmAgents) {
            if (peer.getName().equals(self.getName())) continue;
            String peerDesc = peer.getDescription() != null && !peer.getDescription().isEmpty()
                ? peer.getDescription()
                : (peer.getInstructions() instanceof String ? (String) peer.getInstructions() : "Agent: " + peer.getName());
            ToolConfig transferTool = ToolConfig.builder()
                .name("transfer_to_" + peer.getName())
                .description("Transfer the conversation to " + peer.getName() + ". " + peerDesc)
                .inputSchema(Map.of("type", "object", "properties", Map.of(), "required", List.of()))
                .toolType("worker")
                .build();
            transferTools.add(transferTool);
        }
        return transferTools;
    }

    /**
     * Compile a single swarm agent into a SUB_WORKFLOW with transfer detection.
     * <p>
     * The inner workflow contains: init_state → DO_WHILE(llm, tool_router, check_transfer)
     * and outputs {result, finishReason, is_transfer, transfer_to}.
     */
    WorkflowDef compileSwarmAgentWorkflow(AgentConfig agent, List<ToolConfig> transferTools) {
        boolean hasSubAgents = agent.getAgents() != null && !agent.getAgents().isEmpty();

        if (hasSubAgents) {
            // Agent has its own strategy (handoff, sequential, etc.)
            // Compile it normally to preserve its multi-agent behavior,
            // then wrap with transfer detection
            return compileSwarmAgentWorkflowWithSubAgents(agent, transferTools);
        }

        // Original flat path for simple/tool-calling agents
        ParsedModel parsed = ModelParser.parse(agent.getModel());
        String llmRef = agent.getName() + "_llm";
        String checkTransferRef = agent.getName() + "_check_transfer";

        // Merge agent's own tools with transfer tools
        List<ToolConfig> allTools = new ArrayList<>();
        if (agent.getTools() != null) {
            allTools.addAll(agent.getTools());
        }
        allTools.addAll(transferTools);

        ToolCompiler tc = new ToolCompiler();
        boolean hasApproval = allTools.stream().anyMatch(ToolConfig::isApprovalRequired);
        List<Map<String, Object>> toolSpecs = tc.compileToolSpecs(allTools);

        // LLM task
        WorkflowTask llmTask = agentCompiler.buildLlmTask(agent, parsed, llmRef, toolSpecs);

        // Tool call routing
        WorkflowTask toolRouter = tc.buildToolCallRouting(
            agent.getName(), llmRef, allTools, hasApproval, agent.getModel()
        );

        // Check-transfer worker
        WorkflowTask checkTransferTask = new WorkflowTask();
        checkTransferTask.setName(agent.getName() + "_check_transfer");
        checkTransferTask.setTaskReferenceName(checkTransferRef);
        checkTransferTask.setType("SIMPLE");
        Map<String, Object> ctInputs = new LinkedHashMap<>();
        ctInputs.put("tool_calls", ref(llmRef + ".output.toolCalls"));
        checkTransferTask.setInputParameters(ctInputs);

        // DoWhile loop: continue while tool calls present and no transfer
        String loopRef = agent.getName() + "_loop";
        int maxTurns = 25;
        String hasToolCalls = String.format(
            "($.%s['toolCalls'] != null && $.%s['toolCalls'].length > 0)",
            llmRef, llmRef
        );
        String notTransfer = String.format("($.%s.is_transfer != true)", checkTransferRef);
        String termCondition = String.format(
            "if ( $.%s['iteration'] < %d && ($.%s['finishReason'] == 'LENGTH' || $.%s['finishReason'] == 'MAX_TOKENS' || (%s && %s)) ) { true; } else { false; }",
            loopRef, maxTurns, llmRef, llmRef, hasToolCalls, notTransfer
        );

        Map<String, Object> loopInputs = new LinkedHashMap<>();
        loopInputs.put(loopRef, "${" + loopRef + "}");
        loopInputs.put(llmRef, "${" + llmRef + "}");
        loopInputs.put(checkTransferRef, "${" + checkTransferRef + "}");
        WorkflowTask loop = agentCompiler.buildDoWhile(loopRef, termCondition,
            List.of(llmTask, toolRouter, checkTransferTask), loopInputs);

        // Initialize _agent_state for ToolContext.state
        WorkflowTask initState = new WorkflowTask();
        initState.setType("SET_VARIABLE");
        initState.setTaskReferenceName(agent.getName() + "_init_state");
        initState.setInputParameters(Map.of("_agent_state", new LinkedHashMap<>()));

        // Build the sub-workflow
        WorkflowDef subWf = agentCompiler.createWorkflow(agent);
        subWf.setName(agent.getName() + "_swarm_wf");
        subWf.setDescription("Swarm agent: " + agent.getName());
        subWf.setTasks(List.of(initState, loop));
        subWf.setOutputParameters(Map.of(
            "result", ref(llmRef + ".output.result"),
            "finishReason", ref(llmRef + ".output.finishReason"),
            "is_transfer", ref(checkTransferRef + ".output.is_transfer"),
            "transfer_to", ref(checkTransferRef + ".output.transfer_to")
        ));
        return subWf;
    }

    /**
     * Compile a swarm agent that has its own sub-agents (hierarchical).
     * The agent's strategy (handoff, sequential, etc.) is preserved via normal compilation,
     * then wrapped with transfer detection logic.
     */
    private WorkflowDef compileSwarmAgentWorkflowWithSubAgents(AgentConfig agent, List<ToolConfig> transferTools) {
        ParsedModel parsed = ModelParser.parse(agent.getModel());
        String innerRef = agent.getName() + "_inner";
        String transferLlmRef = agent.getName() + "_transfer_llm";
        String checkTransferRef = agent.getName() + "_check_transfer";

        // 1. Compile the agent normally to preserve its multi-agent strategy
        WorkflowDef innerWf = agentCompiler.compile(agent);

        // Inner agent as SUB_WORKFLOW
        WorkflowTask innerTask = new WorkflowTask();
        innerTask.setType("SUB_WORKFLOW");
        innerTask.setName(agent.getName() + "_strategy");
        innerTask.setTaskReferenceName(innerRef);
        innerTask.setSubWorkflowParam(new com.netflix.conductor.common.metadata.workflow.SubWorkflowParams());
        innerTask.getSubWorkflowParam().setName(innerWf.getName());
        innerTask.getSubWorkflowParam().setWorkflowDef(innerWf);
        Map<String, Object> innerInputs = new LinkedHashMap<>();
        innerInputs.put("prompt", "${workflow.input.prompt}");
        innerInputs.put("media", "${workflow.input.media}");
        innerInputs.put("session_id", "${workflow.input.session_id}");
        innerTask.setInputParameters(innerInputs);

        // 2. LLM step with transfer tools to decide whether to transfer to a peer
        ToolCompiler tc = new ToolCompiler();
        List<Map<String, Object>> transferToolSpecs = tc.compileToolSpecs(transferTools);

        WorkflowTask transferLlm = new WorkflowTask();
        transferLlm.setName("LLM_CHAT_COMPLETE");
        transferLlm.setTaskReferenceName(transferLlmRef);
        transferLlm.setType("LLM_CHAT_COMPLETE");
        Map<String, Object> llmInputs = new LinkedHashMap<>();
        llmInputs.put("llmProvider", parsed.getProvider());
        llmInputs.put("model", parsed.getModel());
        String transferPrompt = "You have just completed your task. Your result is shown above.\n\n" +
            "If another agent should handle a different part of the request, call the appropriate " +
            "transfer tool. Otherwise, do NOT call any tool — just respond with a brief acknowledgment.";
        llmInputs.put("messages", List.of(
            Map.of("role", "system", "message", transferPrompt),
            Map.of("role", "user", "message", "${workflow.input.prompt}"),
            Map.of("role", "assistant", "message", ref(innerRef + ".output.result"))
        ));
        if (!transferToolSpecs.isEmpty()) {
            llmInputs.put("tools", transferToolSpecs);
        }
        transferLlm.setInputParameters(llmInputs);

        // 3. Check-transfer worker
        WorkflowTask checkTransferTask = new WorkflowTask();
        checkTransferTask.setName(agent.getName() + "_check_transfer");
        checkTransferTask.setTaskReferenceName(checkTransferRef);
        checkTransferTask.setType("SIMPLE");
        Map<String, Object> ctInputs = new LinkedHashMap<>();
        ctInputs.put("tool_calls", ref(transferLlmRef + ".output.toolCalls"));
        checkTransferTask.setInputParameters(ctInputs);

        // Build the wrapper sub-workflow
        WorkflowDef subWf = agentCompiler.createWorkflow(agent);
        subWf.setName(agent.getName() + "_swarm_wf");
        subWf.setDescription("Swarm hierarchical agent: " + agent.getName());
        subWf.setTasks(List.of(innerTask, transferLlm, checkTransferTask));
        subWf.setOutputParameters(Map.of(
            "result", ref(innerRef + ".output.result"),
            "finishReason", "stop",
            "is_transfer", ref(checkTransferRef + ".output.is_transfer"),
            "transfer_to", ref(checkTransferRef + ".output.transfer_to")
        ));
        return subWf;
    }

    // ── Manual strategy ─────────────────────────────────────────────

    private WorkflowDef compileManual(AgentConfig config) {
        WorkflowDef wf = agentCompiler.createWorkflow(config);
        wf.setDescription("Manual selection: " + config.getName());

        int numAgents = config.getAgents().size();
        String loopRef = config.getName() + "_loop";
        int maxTurns = config.getMaxTurns() > 0 ? config.getMaxTurns() : 25;

        // 1. Init
        WorkflowTask initVar = new WorkflowTask();
        initVar.setType("SET_VARIABLE");
        initVar.setTaskReferenceName(config.getName() + "_init");
        Map<String, Object> initInputs = new LinkedHashMap<>();
        String introductions = buildIntroductions(config);
        initInputs.put("conversation", introductions.isEmpty()
            ? "${workflow.input.prompt}"
            : introductions + "\n\n${workflow.input.prompt}");
        initVar.setInputParameters(initInputs);

        // 2. HumanTask
        String humanRef = config.getName() + "_pick_agent";
        WorkflowTask humanTask = new WorkflowTask();
        humanTask.setType("HUMAN");
        humanTask.setTaskReferenceName(humanRef);
        Map<String, Object> humanInputs = new LinkedHashMap<>();
        humanInputs.put("__humanTaskDefinition", Map.of(
            "assignmentCompletionStrategy", "LEAVE_OPEN",
            "displayName", config.getName() + ": Select next agent",
            "userFormTemplate", Map.of("version", 0)
        ));
        Map<String, String> agentOptions = new LinkedHashMap<>();
        for (int i = 0; i < config.getAgents().size(); i++) {
            agentOptions.put(config.getAgents().get(i).getName(), String.valueOf(i));
        }
        humanInputs.put("agent_options", agentOptions);
        humanInputs.put("conversation", "${workflow.variables.conversation}");
        humanTask.setInputParameters(humanInputs);

        // Process selection worker
        String processRef = config.getName() + "_process_selection";
        WorkflowTask processTask = new WorkflowTask();
        processTask.setName(config.getName() + "_process_selection");
        processTask.setTaskReferenceName(processRef);
        processTask.setType("SIMPLE");
        processTask.setInputParameters(Map.of("human_output", ref(humanRef + ".output")));

        // 3. Switch to selected agent
        WorkflowTask switchTask = new WorkflowTask();
        switchTask.setType("SWITCH");
        switchTask.setTaskReferenceName(config.getName() + "_switch");
        switchTask.setEvaluatorType("value-param");
        switchTask.setExpression("switchCaseValue");
        switchTask.setInputParameters(Map.of("switchCaseValue", ref(processRef + ".output.selected")));

        Map<String, List<WorkflowTask>> cases = new LinkedHashMap<>();
        for (int i = 0; i < numAgents; i++) {
            AgentConfig sub = config.getAgents().get(i);
            List<WorkflowTask> caseTasks = buildRotationCaseTasks(config, sub, i, loopRef);
            cases.put(String.valueOf(i), caseTasks);
        }
        switchTask.setDecisionCases(cases);

        // 4. DoWhile
        String termCondition = String.format(
            "if ( $.%s['iteration'] < %d ) { true; } else { false; }",
            loopRef, maxTurns
        );
        Map<String, Object> loopInputs = Map.of(loopRef, "${" + loopRef + "}");
        WorkflowTask loop = agentCompiler.buildDoWhile(loopRef, termCondition,
            List.of(humanTask, processTask, switchTask), loopInputs);

        wf.setTasks(List.of(initVar, loop));
        wf.setOutputParameters(Map.of("result", "${workflow.variables.conversation}"));
        agentCompiler.applyTimeout(wf, config);
        return wf;
    }

    // ── Guardrail wrapping ──────────────────────────────────────────

    private WorkflowDef wrapWithGuardrails(AgentConfig config, WorkflowDef strategyWf) {
        String subRef = config.getName() + "_strategy";

        // Run strategy as inline sub-workflow
        WorkflowTask subTask = new WorkflowTask();
        subTask.setType("SUB_WORKFLOW");
        subTask.setTaskReferenceName(subRef);
        subTask.setSubWorkflowParam(new com.netflix.conductor.common.metadata.workflow.SubWorkflowParams());
        subTask.getSubWorkflowParam().setName(strategyWf.getName());
        subTask.getSubWorkflowParam().setWorkflowDef(strategyWf);
        Map<String, Object> subInputs = new LinkedHashMap<>();
        subInputs.put("prompt", "${workflow.input.prompt}");
        subInputs.put("media", "${workflow.input.media}");
        subInputs.put("session_id", "${workflow.input.session_id}");
        subTask.setInputParameters(subInputs);

        String contentRef = ref(subRef + ".output.result");

        GuardrailCompiler gc = new GuardrailCompiler();
        List<GuardrailConfig> outputGuardrails = agentCompiler.getOutputGuardrails(config);
        List<GuardrailCompiler.GuardrailTaskResult> guardrailResults =
            gc.compileGuardrailTasks(outputGuardrails, config.getName(), contentRef);

        List<WorkflowTask> loopTasks = new ArrayList<>();
        loopTasks.add(subTask);

        List<String[]> guardrailRefs = new ArrayList<>();
        for (int idx = 0; idx < guardrailResults.size(); idx++) {
            GuardrailCompiler.GuardrailTaskResult gr = guardrailResults.get(idx);
            String suffix = guardrailResults.size() > 1 ? "_" + idx : "";
            GuardrailCompiler.GuardrailRoutingResult routing = gc.compileGuardrailRouting(
                outputGuardrails.get(idx), gr.getRefName(), contentRef,
                config.getName(), suffix, gr.isInline()
            );
            loopTasks.addAll(gr.getTasks());
            loopTasks.add(routing.getSwitchTask());
            guardrailRefs.add(new String[]{gr.getRefName(), String.valueOf(gr.isInline())});
        }

        String guardrailContinue = agentCompiler.buildGuardrailContinue(guardrailRefs);
        int maxTurns = config.getMaxTurns() > 0 ? config.getMaxTurns() : 25;
        String loopCondition = String.format(
            "if ( $.%s_guardrail_loop['iteration'] < %d && (%s) ) { true; } else { false; }",
            config.getName(), maxTurns, guardrailContinue
        );

        String guardrailLoopRef = config.getName() + "_guardrail_loop";
        Map<String, Object> loopInputs = new LinkedHashMap<>();
        loopInputs.put(guardrailLoopRef, "${" + guardrailLoopRef + "}");
        agentCompiler.addGuardrailInputs(loopInputs, guardrailRefs);
        WorkflowTask doWhile = agentCompiler.buildDoWhile(
            guardrailLoopRef, loopCondition, loopTasks, loopInputs
        );

        WorkflowDef outerWf = agentCompiler.createWorkflow(config);
        outerWf.setTasks(List.of(doWhile));
        outerWf.setOutputParameters(Map.of("result", contentRef));
        return outerWf;
    }

    // ── Shared helpers ──────────────────────────────────────────────

    private List<WorkflowTask> buildRotationCaseTasks(AgentConfig parent, AgentConfig sub, int idx, String loopRef) {
        List<WorkflowTask> caseTasks = new ArrayList<>();
        String subRef = parent.getName() + "_agent_" + idx + "_" + sub.getName();

        WorkflowTask task = agentCompiler.compileSubAgent(sub, subRef,
            "${workflow.variables.conversation}", "${workflow.input.media}");
        caseTasks.add(task);

        // Concat
        String responseRef = AgentCompiler.subAgentResultRef(sub, subRef);
        WorkflowTask concatTask = new WorkflowTask();
        concatTask.setType("INLINE");
        concatTask.setTaskReferenceName(parent.getName() + "_concat_" + idx);
        Map<String, Object> concatInputs = new LinkedHashMap<>();
        concatInputs.put("evaluatorType", "graaljs");
        concatInputs.put("expression", JavaScriptBuilder.concatScript(sub.getName()));
        concatInputs.put("prev", "${workflow.variables.conversation}");
        concatInputs.put("response", responseRef);
        concatTask.setInputParameters(concatInputs);
        caseTasks.add(concatTask);

        // SetVariable
        WorkflowTask setVar = new WorkflowTask();
        setVar.setType("SET_VARIABLE");
        setVar.setTaskReferenceName(parent.getName() + "_set_" + idx);
        Map<String, Object> setInputs = new LinkedHashMap<>();
        setInputs.put("conversation", ref(parent.getName() + "_concat_" + idx + ".output.result"));
        if (parent.getAllowedTransitions() != null) {
            setInputs.put("last_agent", String.valueOf(idx));
        }
        setVar.setInputParameters(setInputs);
        caseTasks.add(setVar);

        return caseTasks;
    }

    private List<WorkflowTask> buildSwarmCaseTasks(AgentConfig parent, AgentConfig sub, int idx,
                                                    List<ToolConfig> transferTools) {
        List<WorkflowTask> caseTasks = new ArrayList<>();
        String subRef = parent.getName() + "_agent_" + idx + "_" + sub.getName();

        // Compile as SUB_WORKFLOW with inline transfer-aware workflow
        WorkflowDef agentWf = compileSwarmAgentWorkflow(sub, transferTools);
        WorkflowTask task = new WorkflowTask();
        task.setType("SUB_WORKFLOW");
        task.setName(sub.getName());
        task.setTaskReferenceName(subRef);
        task.setSubWorkflowParam(new com.netflix.conductor.common.metadata.workflow.SubWorkflowParams());
        task.getSubWorkflowParam().setName(agentWf.getName());
        task.getSubWorkflowParam().setWorkflowDef(agentWf);
        Map<String, Object> subInputs = new LinkedHashMap<>();
        subInputs.put("prompt", "${workflow.variables.conversation}");
        subInputs.put("media", "${workflow.input.media}");
        subInputs.put("session_id", "${workflow.input.session_id}");
        task.setInputParameters(subInputs);
        caseTasks.add(task);

        // Concat response to conversation
        String responseRef = ref(subRef + ".output.result");
        WorkflowTask concatTask = new WorkflowTask();
        concatTask.setType("INLINE");
        concatTask.setTaskReferenceName(parent.getName() + "_concat_" + idx);
        Map<String, Object> concatInputs = new LinkedHashMap<>();
        concatInputs.put("evaluatorType", "graaljs");
        concatInputs.put("expression", JavaScriptBuilder.concatScript(sub.getName()));
        concatInputs.put("prev", "${workflow.variables.conversation}");
        concatInputs.put("response", responseRef);
        concatTask.setInputParameters(concatInputs);
        caseTasks.add(concatTask);

        // SetVariable — set conversation, last_response, and transfer state from agent output
        String concatRef = parent.getName() + "_concat_" + idx;
        WorkflowTask setVar = new WorkflowTask();
        setVar.setType("SET_VARIABLE");
        setVar.setTaskReferenceName(parent.getName() + "_set_" + idx);
        Map<String, Object> setInputs = new LinkedHashMap<>();
        setInputs.put("conversation", ref(concatRef + ".output.result"));
        setInputs.put("last_response", responseRef);
        setInputs.put("is_transfer", ref(subRef + ".output.is_transfer"));
        setInputs.put("transfer_to", ref(subRef + ".output.transfer_to"));
        setVar.setInputParameters(setInputs);
        caseTasks.add(setVar);

        return caseTasks;
    }

    private WorkflowTask buildRouterLlm(String taskRef, ParsedModel parsed, String systemPrompt) {
        WorkflowTask llm = new WorkflowTask();
        llm.setName("LLM_CHAT_COMPLETE");
        llm.setTaskReferenceName(taskRef);
        llm.setType("LLM_CHAT_COMPLETE");
        Map<String, Object> inputs = new LinkedHashMap<>();
        inputs.put("llmProvider", parsed.getProvider());
        inputs.put("model", parsed.getModel());
        inputs.put("messages", List.of(
            Map.of("role", "system", "message", systemPrompt),
            Map.of("role", "user", "message", "${workflow.input.prompt}")
        ));
        inputs.put("temperature", 0);
        llm.setInputParameters(inputs);
        return llm;
    }

    private String buildSelectScript(AgentConfig config, int numAgents, String loopRef, boolean random) {
        if (config.getAllowedTransitions() != null) {
            Map<String, List<String>> transitions = config.getAllowedTransitions();
            Map<String, List<Integer>> idxMap = new LinkedHashMap<>();
            Map<String, Integer> nameToIdx = new LinkedHashMap<>();
            for (int i = 0; i < config.getAgents().size(); i++) {
                nameToIdx.put(config.getAgents().get(i).getName(), i);
            }
            for (Map.Entry<String, List<String>> entry : transitions.entrySet()) {
                Integer srcIdx = nameToIdx.get(entry.getKey());
                if (srcIdx == null) continue;
                List<Integer> dstIndices = entry.getValue().stream()
                    .map(nameToIdx::get)
                    .filter(Objects::nonNull)
                    .toList();
                if (!dstIndices.isEmpty()) {
                    idxMap.put(String.valueOf(srcIdx), dstIndices);
                }
            }
            String idxMapJson = JavaScriptBuilder.toJson(idxMap);
            return random
                ? JavaScriptBuilder.constrainedRandomScript(idxMapJson, numAgents)
                : JavaScriptBuilder.constrainedRoundRobinScript(idxMapJson, numAgents);
        }

        return random
            ? JavaScriptBuilder.randomSelectScript(numAgents)
            : JavaScriptBuilder.roundRobinSelectScript(numAgents);
    }

    private String buildIntroductions(AgentConfig config) {
        if (config.getAgents() == null) return "";
        List<String> intros = new ArrayList<>();
        for (AgentConfig sub : config.getAgents()) {
            if (sub.getIntroduction() != null && !sub.getIntroduction().isEmpty()) {
                intros.add("[" + sub.getName() + "]: " + sub.getIntroduction());
            }
        }
        return String.join("\n", intros);
    }

    /**
     * Build router LLM task wrapped in a SUB_WORKFLOW.
     * <p>
     * Using a sub-workflow prevents Conductor's DoWhile from accumulating
     * previous iteration LLM outputs as assistant messages.  The router
     * must make a fresh routing decision each iteration based solely on
     * the conversation variable — stale assistant messages confuse the
     * model and cause failures (e.g. consecutive/empty assistant messages
     * that Gemini rejects).
     */
    private WorkflowTask buildIterativeRouterLlm(String taskRef, ParsedModel parsed, String systemPrompt) {
        // Inner LLM task inside the sub-workflow
        WorkflowTask llm = new WorkflowTask();
        llm.setName("LLM_CHAT_COMPLETE");
        llm.setTaskReferenceName(taskRef + "_llm");
        llm.setType("LLM_CHAT_COMPLETE");
        Map<String, Object> llmInputs = new LinkedHashMap<>();
        llmInputs.put("llmProvider", parsed.getProvider());
        llmInputs.put("model", parsed.getModel());
        llmInputs.put("messages", List.of(
            Map.of("role", "system", "message", systemPrompt),
            Map.of("role", "user", "message", "${workflow.input.conversation}")
        ));
        llmInputs.put("temperature", 0);
        llm.setInputParameters(llmInputs);

        // Sub-workflow definition containing just the LLM task
        WorkflowDef routerWf = new WorkflowDef();
        routerWf.setName(taskRef + "_wf");
        routerWf.setVersion(1);
        routerWf.setDescription("Router sub-workflow for " + taskRef);
        routerWf.setInputParameters(List.of("conversation"));
        routerWf.setTasks(List.of(llm));
        routerWf.setOutputParameters(Map.of("result", ref(taskRef + "_llm.output.result")));

        // SUB_WORKFLOW task that passes conversation as input
        WorkflowTask subTask = new WorkflowTask();
        subTask.setType("SUB_WORKFLOW");
        subTask.setName(taskRef);
        subTask.setTaskReferenceName(taskRef);
        subTask.setSubWorkflowParam(new com.netflix.conductor.common.metadata.workflow.SubWorkflowParams());
        subTask.getSubWorkflowParam().setName(routerWf.getName());
        subTask.getSubWorkflowParam().setWorkflowDef(routerWf);
        subTask.setInputParameters(Map.of(
            "conversation", "${workflow.variables.conversation}"
        ));

        return subTask;
    }

    /**
     * Build case tasks for handoff: sub-agent -> concat -> SetVariable.
     */
    private List<WorkflowTask> buildHandoffCaseTasks(AgentConfig parent, AgentConfig sub, int idx) {
        return buildHandoffCaseTasks(parent, sub, idx, "");
    }

    private List<WorkflowTask> buildHandoffCaseTasks(AgentConfig parent, AgentConfig sub, int idx, String suffix) {
        List<WorkflowTask> caseTasks = new ArrayList<>();
        String subRef = parent.getName() + "_handoff_" + idx + "_" + sub.getName() + suffix;

        WorkflowTask task = agentCompiler.compileSubAgent(sub, subRef,
            "${workflow.variables.conversation}", "${workflow.input.media}");
        caseTasks.add(task);

        // Concat response to conversation
        String responseRef = AgentCompiler.subAgentResultRef(sub, subRef);
        WorkflowTask concatTask = new WorkflowTask();
        concatTask.setType("INLINE");
        concatTask.setTaskReferenceName(parent.getName() + "_hconcat_" + idx + suffix);
        Map<String, Object> concatInputs = new LinkedHashMap<>();
        concatInputs.put("evaluatorType", "graaljs");
        concatInputs.put("expression", JavaScriptBuilder.concatScript(sub.getName()));
        concatInputs.put("prev", "${workflow.variables.conversation}");
        concatInputs.put("response", responseRef);
        concatTask.setInputParameters(concatInputs);
        caseTasks.add(concatTask);

        // Persist updated conversation
        WorkflowTask setVar = new WorkflowTask();
        setVar.setType("SET_VARIABLE");
        setVar.setTaskReferenceName(parent.getName() + "_hset_" + idx + suffix);
        setVar.setInputParameters(Map.of(
            "conversation", ref(parent.getName() + "_hconcat_" + idx + suffix + ".output.result")
        ));
        caseTasks.add(setVar);

        return caseTasks;
    }

    private String resolveInstructions(AgentConfig config) {
        Object instr = config.getInstructions();
        if (instr == null) return "";
        if (instr instanceof String s) return s;
        return instr.toString();
    }
}
