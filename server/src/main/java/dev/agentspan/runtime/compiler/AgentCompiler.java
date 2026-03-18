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
import org.springframework.stereotype.Component;

import java.util.*;

/**
 * Compiles an AgentConfig into a Conductor WorkflowDef.
 * Mirrors python/src/conductor/agents/compiler/agent_compiler.py.
 */
@Component
public class AgentCompiler {

    private static final Logger log = LoggerFactory.getLogger(AgentCompiler.class);

    private static final List<String> WORKFLOW_INPUTS = List.of("prompt", "session_id", "media");
    private static final Map<String, Object> USER_MESSAGE = Map.of(
        "role", "user",
        "message", "${workflow.input.prompt}",
        "media", "${workflow.input.media}"
    );

    private int timeoutSeconds = 0;
    private int llmRetryCount = 3;

    /**
     * Main entry point: compile an AgentConfig into a WorkflowDef.
     */
    public WorkflowDef compile(AgentConfig config) {
        if (config.isExternal()) {
            throw new IllegalArgumentException(
                "Cannot compile external agent '" + config.getName() + "' directly. " +
                "External agents are compiled as SubWorkflowTask references."
            );
        }

        boolean hasAgents = config.getAgents() != null && !config.getAgents().isEmpty();
        boolean hasTools = config.getTools() != null && !config.getTools().isEmpty();

        WorkflowDef wf;

        // Multi-agent with NO tools -> delegate to MultiAgentCompiler
        if (hasAgents && !hasTools) {
            wf = new MultiAgentCompiler(this).compile(config);
        } else if (hasAgents && hasTools) {
            // Both tools AND sub-agents -> hybrid mode
            log.debug("Hybrid mode: agent '{}' has {} tools and {} sub-agents",
                config.getName(), config.getTools().size(), config.getAgents().size());
            wf = compileHybrid(config);
        } else if (!hasTools) {
            // No tools -> simple single LLM call
            wf = compileSimple(config);
        } else {
            // Tools -> unified native FC path
            wf = compileWithTools(config);
        }

        // Stamp agent capability tags into workflow metadata
        Set<String> caps = collectCapabilities(config);
        Map<String, Object> metadata = wf.getMetadata() != null
            ? new LinkedHashMap<>(wf.getMetadata()) : new LinkedHashMap<>();
        metadata.put("agent_capabilities", new ArrayList<>(caps));
        wf.setMetadata(metadata);

        // Ensure every task has a name (Conductor requires it for execution)
        if (wf.getTasks() != null) {
            wf.getTasks().forEach(AgentCompiler::ensureTaskNames);
        }
        return wf;
    }

    // ── Simple agent (no tools) ─────────────────────────────────────

    WorkflowDef compileSimple(AgentConfig config) {
        ParsedModel parsed = ModelParser.parse(config.getModel());
        String llmRef = config.getName() + "_llm";

        WorkflowDef wf = createWorkflow(config);

        // Build LLM task
        WorkflowTask llmTask = buildLlmTask(config, parsed, llmRef, null);

        // Check for output guardrails
        List<GuardrailConfig> outputGuardrails = getOutputGuardrails(config);

        if (outputGuardrails.isEmpty()) {
            // Simple path: single LLM call, no loop
            wf.setTasks(List.of(llmTask));
            wf.setOutputParameters(Map.of(
                "result", ref(llmRef + ".output.result"),
                "finishReason", ref(llmRef + ".output.finishReason")
            ));
            return wf;
        }

        // Guarded path: LLM + guardrails in DoWhile loop
        String contentRef = ref(llmRef + ".output.result");
        String loopRef = config.getName() + "_loop";
        int maxTurns = config.getMaxTurns() > 0 ? config.getMaxTurns() : 25;

        List<WorkflowTask> loopTasks = new ArrayList<>();
        loopTasks.add(llmTask);

        // Compile guardrails inside loop
        GuardrailCompiler gc = new GuardrailCompiler();
        List<GuardrailCompiler.GuardrailTaskResult> guardrailResults =
            gc.compileGuardrailTasks(outputGuardrails, config.getName(), contentRef);

        List<String[]> guardrailRefs = new ArrayList<>(); // [refName, isInline]
        List<String> retryRefs = new ArrayList<>();

        for (int idx = 0; idx < guardrailResults.size(); idx++) {
            GuardrailCompiler.GuardrailTaskResult gr = guardrailResults.get(idx);
            String suffix = guardrailResults.size() > 1 ? "_" + idx : "";
            GuardrailCompiler.GuardrailRoutingResult routing = gc.compileGuardrailRouting(
                outputGuardrails.get(idx), gr.getRefName(), contentRef,
                config.getName(), suffix, gr.isInline(), config.getModel()
            );
            loopTasks.addAll(gr.getTasks());
            loopTasks.add(routing.getSwitchTask());
            guardrailRefs.add(new String[]{gr.getRefName(), String.valueOf(gr.isInline())});
            retryRefs.add(routing.getRetryRef());
        }

        // Wire retry feedback into LLM participants
        if (!retryRefs.isEmpty()) {
            Map<String, Object> participants = new LinkedHashMap<>();
            for (String rr : retryRefs) {
                participants.put(rr, "user");
            }
            llmTask.getInputParameters().put("participants", participants);
        }

        // Build termination condition
        String guardrailContinue = buildGuardrailContinue(guardrailRefs);
        String termCondition = String.format(
            "if ( $.%s['iteration'] < %d && ($.%s['finishReason'] == 'LENGTH' || $.%s['finishReason'] == 'MAX_TOKENS' || (%s)) ) { true; } else { false; }",
            loopRef, maxTurns, llmRef, llmRef, guardrailContinue
        );

        Map<String, Object> loopInputs = new LinkedHashMap<>();
        loopInputs.put(loopRef, "${" + loopRef + "}");
        loopInputs.put(llmRef, "${" + llmRef + "}");
        addGuardrailInputs(loopInputs, guardrailRefs);
        WorkflowTask loop = buildDoWhile(loopRef, termCondition, loopTasks, loopInputs);

        // Post-loop: resolve output (guardrail fix or human edit may override LLM output)
        String resolveRef = config.getName() + "_resolve_output";
        WorkflowTask resolveTask = buildResolveOutputTask(resolveRef, llmRef);

        wf.setTasks(List.of(loop, resolveTask));
        wf.setOutputParameters(Map.of(
            "result", ref(resolveRef + ".output.result.result"),
            "finishReason", ref(resolveRef + ".output.result.finishReason")
        ));
        applyTimeout(wf, config);
        return wf;
    }

    // ── Agent with tools ────────────────────────────────────────────

    WorkflowDef compileWithTools(AgentConfig config) {
        ParsedModel parsed = ModelParser.parse(config.getModel());
        String llmRef = config.getName() + "_llm";
        List<ToolConfig> tools = config.getTools();

        ToolCompiler tc = new ToolCompiler();
        boolean hasApproval = tools.stream().anyMatch(ToolConfig::isApprovalRequired);
        boolean hasMcp = tools.stream().anyMatch(t -> "mcp".equals(t.getToolType()));

        WorkflowDef wf = createWorkflow(config);

        // ── MCP discovery (pre-loop tasks) or static tool specs ──────
        ToolCompiler.McpDiscoveryResult mcpResult = null;
        List<Map<String, Object>> toolSpecs = null;

        if (hasMcp) {
            List<ToolConfig> staticTools = tools.stream()
                    .filter(t -> !"mcp".equals(t.getToolType())).toList();
            List<ToolConfig> mcpTools = tools.stream()
                    .filter(t -> "mcp".equals(t.getToolType())).toList();

            List<Map<String, Object>> staticSpecs = tc.compileToolSpecs(staticTools);
            mcpResult = tc.buildMcpDiscoveryTasks(
                    config.getName(), mcpTools, staticSpecs, config.getModel());
        } else {
            toolSpecs = tc.compileToolSpecs(tools);
        }

        // Build LLM task
        WorkflowTask llmTask;
        if (mcpResult != null) {
            // LLM task with null toolSpecs; wire dynamic tools ref after
            llmTask = buildLlmTask(config, parsed, llmRef, null);
            llmTask.getInputParameters().put("tools", mcpResult.getToolsRef());
        } else {
            llmTask = buildLlmTask(config, parsed, llmRef, toolSpecs);
        }

        // Inject human feedback context for agents with approval-required tools.
        // When a human responds with custom data (e.g. {"approved": true, "department": "eng"}),
        // the extra fields are stored in workflow.variables._human_feedback.
        // This message makes those fields visible to the LLM on subsequent iterations.
        if (hasApproval) {
            @SuppressWarnings("unchecked")
            List<Object> msgs = (List<Object>) llmTask.getInputParameters().get("messages");
            msgs.add(Map.of(
                "role", "system",
                "message", "${workflow.variables._human_feedback}"
            ));
        }

        // Tool call routing SwitchTask (with tool-level guardrail metadata)
        ToolCompiler.ToolCallRoutingResult toolRoutingResult;
        if (mcpResult != null) {
            toolRoutingResult = tc.buildToolCallRoutingDynamicWithResult(
                config.getName(), llmRef, tools, hasApproval, config.getModel(),
                mcpResult.getMcpConfigRef());
        } else {
            toolRoutingResult = tc.buildToolCallRoutingWithResult(
                config.getName(), llmRef, tools, hasApproval, config.getModel()
            );
        }
        WorkflowTask toolRouter = toolRoutingResult.getRouterTask();

        // Build loop body
        List<WorkflowTask> loopTasks = new ArrayList<>();

        // Callback: before_model (runs before each LLM call in the loop)
        CallbackConfig beforeModel = findCallback(config, "before_model");
        if (beforeModel != null) {
            loopTasks.add(buildCallbackTask(beforeModel, config.getName(), llmRef));
        }

        loopTasks.add(llmTask);

        // Callback: after_model (runs after each LLM call in the loop)
        CallbackConfig afterModel = findCallback(config, "after_model");
        if (afterModel != null) {
            loopTasks.add(buildCallbackTask(afterModel, config.getName(), llmRef));
        }

        // Output guardrails (inside loop, after LLM)
        List<GuardrailConfig> outputGuardrails = getOutputGuardrails(config);
        List<String[]> guardrailRefs = new ArrayList<>();
        List<String> retryRefs = new ArrayList<>();

        if (!outputGuardrails.isEmpty()) {
            String contentRef = ref(llmRef + ".output.result");
            GuardrailCompiler gc = new GuardrailCompiler();
            List<GuardrailCompiler.GuardrailTaskResult> guardrailResults =
                gc.compileGuardrailTasks(outputGuardrails, config.getName(), contentRef);

            for (int idx = 0; idx < guardrailResults.size(); idx++) {
                GuardrailCompiler.GuardrailTaskResult gr = guardrailResults.get(idx);
                String suffix = guardrailResults.size() > 1 ? "_" + idx : "";
                GuardrailCompiler.GuardrailRoutingResult routing = gc.compileGuardrailRouting(
                    outputGuardrails.get(idx), gr.getRefName(), contentRef,
                    config.getName(), suffix, gr.isInline(), config.getModel()
                );
                loopTasks.addAll(gr.getTasks());
                loopTasks.add(routing.getSwitchTask());
                guardrailRefs.add(new String[]{gr.getRefName(), String.valueOf(gr.isInline())});
                retryRefs.add(routing.getRetryRef());
            }
        }

        loopTasks.add(toolRouter);

        // Merge tool-level guardrail refs (from tool routing) into tracking lists
        guardrailRefs.addAll(toolRoutingResult.getToolGuardrailRefs());
        retryRefs.addAll(toolRoutingResult.getToolGuardrailRetryRefs());

        // Wire all retry refs (agent + tool guardrails) into LLM participants
        if (!retryRefs.isEmpty()) {
            Map<String, Object> participants = new LinkedHashMap<>();
            for (String rr : retryRefs) {
                participants.put(rr, "user");
            }
            llmTask.getInputParameters().put("participants", participants);
        }

        // Optional stop_when worker
        String stopWhenRef = null;
        if (config.getStopWhen() != null) {
            WorkflowTask stopWhenTask = TerminationCompiler.compileStopWhen(
                config.getStopWhen().getTaskName(), config.getName(), llmRef
            );
            loopTasks.add(stopWhenTask);
            stopWhenRef = config.getName() + "_stop_when";
        }

        // Optional termination condition
        String terminationRef = null;
        if (config.getTermination() != null) {
            WorkflowTask termTask = TerminationCompiler.compileTermination(
                config.getTermination(), config.getName(), llmRef
            );
            loopTasks.add(termTask);
            terminationRef = config.getName() + "_termination";
        }

        // DoWhile loop
        String loopRef = config.getName() + "_loop";
        int maxTurns = config.getMaxTurns() > 0 ? config.getMaxTurns() : 25;

        String hasToolCalls = String.format(
            "($.%s['toolCalls'] != null && $.%s['toolCalls'].length > 0)",
            llmRef, llmRef
        );

        String loopReason;
        if (!guardrailRefs.isEmpty()) {
            String guardrailContinue = buildGuardrailContinue(guardrailRefs);
            loopReason = "(" + hasToolCalls + " || " + guardrailContinue + ")";
        } else {
            loopReason = hasToolCalls;
        }

        StringBuilder termCondition = new StringBuilder();
        termCondition.append(String.format(
            "if ( $.%s['iteration'] < %d && ($.%s['finishReason'] == 'LENGTH' || $.%s['finishReason'] == 'MAX_TOKENS' || %s)",
            loopRef, maxTurns, llmRef, llmRef, loopReason
        ));
        if (stopWhenRef != null) {
            termCondition.append(String.format(" && $.%s.should_continue == true", stopWhenRef));
        }
        if (terminationRef != null) {
            termCondition.append(String.format(" && $.%s.should_continue == true", terminationRef));
        }
        termCondition.append(" ) { true; } else { false; }");

        Map<String, Object> loopInputs = new LinkedHashMap<>();
        loopInputs.put(loopRef, "${" + loopRef + "}");
        loopInputs.put(llmRef, "${" + llmRef + "}");
        if (stopWhenRef != null) loopInputs.put(stopWhenRef, "${" + stopWhenRef + "}");
        if (terminationRef != null) loopInputs.put(terminationRef, "${" + terminationRef + "}");
        addGuardrailInputs(loopInputs, guardrailRefs);
        WorkflowTask loop = buildDoWhile(loopRef, termCondition.toString(), loopTasks, loopInputs);

        // ── Final workflow tasks ─────────────────────────────────────
        List<WorkflowTask> allTasks = new ArrayList<>();

        // Callback: before_agent (runs once before the loop)
        CallbackConfig beforeAgent = findCallback(config, "before_agent");
        if (beforeAgent != null) {
            allTasks.add(buildCallbackTask(beforeAgent, config.getName(), null));
        }

        if (mcpResult != null) {
            allTasks.addAll(mcpResult.getPreTasks());
        }

        // Initialize workflow variables
        Map<String, Object> initVars = new LinkedHashMap<>();
        initVars.put("_agent_state", new LinkedHashMap<>());
        if (hasApproval) {
            // Pre-initialize to empty string so the system message doesn't
            // have null content on the first loop iteration.
            initVars.put("_human_feedback", "");
        }
        WorkflowTask initState = new WorkflowTask();
        initState.setType("SET_VARIABLE");
        initState.setTaskReferenceName(config.getName() + "_init_state");
        initState.setInputParameters(initVars);
        allTasks.add(initState);

        // Required tools enforcement: wrap loop + check in outer DO_WHILE
        if (config.getRequiredTools() != null && !config.getRequiredTools().isEmpty()) {
            String checkRef = config.getName() + "_required_tools_check";
            WorkflowTask checkTask = new WorkflowTask();
            checkTask.setType("INLINE");
            checkTask.setTaskReferenceName(checkRef);
            checkTask.setInputParameters(Map.of(
                "evaluatorType", "graaljs",
                "expression", JavaScriptBuilder.requiredToolsCheckScript(config.getRequiredTools()),
                "completedTaskNames", ref(loopRef + ".output")
            ));

            String outerLoopRef = config.getName() + "_required_tools_loop";
            String outerCondition = String.format(
                "if ( $.%s.output.satisfied == false && $.%s['iteration'] < 3 ) { true; } else { false; }",
                checkRef, outerLoopRef
            );
            Map<String, Object> outerInputs = new LinkedHashMap<>();
            outerInputs.put(checkRef, "${" + checkRef + "}");
            outerInputs.put(outerLoopRef, "${" + outerLoopRef + "}");

            WorkflowTask outerLoop = buildDoWhile(
                outerLoopRef, outerCondition, List.of(loop, checkTask), outerInputs
            );
            allTasks.add(outerLoop);
        } else {
            allTasks.add(loop);
        }

        // Callback: after_agent (runs once after the loop)
        CallbackConfig afterAgent = findCallback(config, "after_agent");
        if (afterAgent != null) {
            allTasks.add(buildCallbackTask(afterAgent, config.getName(), llmRef));
        }

        // Post-loop: resolve output (guardrail fix or human edit may override LLM output)
        List<GuardrailConfig> outGuardrails = getOutputGuardrails(config);
        if (!outGuardrails.isEmpty()) {
            String resolveRef = config.getName() + "_resolve_output";
            allTasks.add(buildResolveOutputTask(resolveRef, llmRef));

            Map<String, Object> outputParams = new LinkedHashMap<>();
            outputParams.put("result", ref(resolveRef + ".output.result.result"));
            outputParams.put("finishReason", ref(resolveRef + ".output.result.finishReason"));
            outputParams.put("rejectionReason", "${workflow.variables.rejectionReason}");
            wf.setOutputParameters(outputParams);
        } else {
            Map<String, Object> outputParams = new LinkedHashMap<>();
            outputParams.put("result", ref(llmRef + ".output.result"));
            outputParams.put("finishReason", ref(llmRef + ".output.finishReason"));
            outputParams.put("rejectionReason", "${workflow.variables.rejectionReason}");
            wf.setOutputParameters(outputParams);
        }

        wf.setTasks(allTasks);
        applyTimeout(wf, config);
        return wf;
    }

    // ── Hybrid: tools AND sub-agents ────────────────────────────────

    WorkflowDef compileHybrid(AgentConfig config) {
        ParsedModel parsed = ModelParser.parse(config.getModel());
        String llmRef = config.getName() + "_llm";

        // Build transfer tools for each sub-agent
        List<ToolConfig> allTools = new ArrayList<>(config.getTools());
        for (AgentConfig sub : config.getAgents()) {
            String subDesc = sub.getDescription() != null && !sub.getDescription().isEmpty()
                ? sub.getDescription()
                : (sub.getInstructions() instanceof String ? (String) sub.getInstructions() : "Agent: " + sub.getName());
            ToolConfig transferTool = ToolConfig.builder()
                .name("transfer_to_" + sub.getName())
                .description("Transfer the conversation to " + sub.getName() + ". " + subDesc)
                .inputSchema(Map.of("type", "object", "properties", Map.of(), "required", List.of()))
                .toolType("worker")
                .build();
            allTools.add(transferTool);
        }

        ToolCompiler tc = new ToolCompiler();
        boolean hasApproval = allTools.stream().anyMatch(ToolConfig::isApprovalRequired);
        boolean hasMcp = allTools.stream().anyMatch(t -> "mcp".equals(t.getToolType()));

        WorkflowDef wf = createWorkflow(config);
        wf.setDescription("Hybrid agent: " + config.getName());

        // ── MCP discovery or static tool specs ───────────────────────
        ToolCompiler.McpDiscoveryResult mcpResult = null;
        List<Map<String, Object>> toolSpecs = null;

        if (hasMcp) {
            List<ToolConfig> staticTools = allTools.stream()
                    .filter(t -> !"mcp".equals(t.getToolType())).toList();
            List<ToolConfig> mcpTools = allTools.stream()
                    .filter(t -> "mcp".equals(t.getToolType())).toList();
            List<Map<String, Object>> staticSpecs = tc.compileToolSpecs(staticTools);
            mcpResult = tc.buildMcpDiscoveryTasks(
                    config.getName(), mcpTools, staticSpecs, config.getModel());
        } else {
            toolSpecs = tc.compileToolSpecs(allTools);
        }

        // Build LLM task
        WorkflowTask llmTask;
        if (mcpResult != null) {
            llmTask = buildLlmTask(config, parsed, llmRef, null);
            llmTask.getInputParameters().put("tools", mcpResult.getToolsRef());
        } else {
            llmTask = buildLlmTask(config, parsed, llmRef, toolSpecs);
        }

        // Tool call routing (with tool-level guardrail metadata)
        ToolCompiler.ToolCallRoutingResult toolRoutingResult;
        if (mcpResult != null) {
            toolRoutingResult = tc.buildToolCallRoutingDynamicWithResult(
                config.getName(), llmRef, allTools, hasApproval, config.getModel(),
                mcpResult.getMcpConfigRef());
        } else {
            toolRoutingResult = tc.buildToolCallRoutingWithResult(
                config.getName(), llmRef, allTools, hasApproval, config.getModel()
            );
        }
        WorkflowTask toolRouter = toolRoutingResult.getRouterTask();

        // Check-transfer worker
        String checkTransferRef = config.getName() + "_check_transfer";
        WorkflowTask checkTransferTask = new WorkflowTask();
        checkTransferTask.setName(config.getName() + "_check_transfer");
        checkTransferTask.setTaskReferenceName(checkTransferRef);
        checkTransferTask.setType("SIMPLE");
        Map<String, Object> ctInputs = new LinkedHashMap<>();
        ctInputs.put("tool_calls", ref(llmRef + ".output.toolCalls"));
        checkTransferTask.setInputParameters(ctInputs);

        // Build loop body
        List<WorkflowTask> loopTasks = new ArrayList<>();
        loopTasks.add(llmTask);

        // Output guardrails
        List<GuardrailConfig> outputGuardrails = getOutputGuardrails(config);
        List<String[]> guardrailRefs = new ArrayList<>();
        List<String> retryRefs = new ArrayList<>();

        if (!outputGuardrails.isEmpty()) {
            String contentRef = ref(llmRef + ".output.result");
            GuardrailCompiler gc = new GuardrailCompiler();
            List<GuardrailCompiler.GuardrailTaskResult> guardrailResults =
                gc.compileGuardrailTasks(outputGuardrails, config.getName(), contentRef);
            for (int idx = 0; idx < guardrailResults.size(); idx++) {
                GuardrailCompiler.GuardrailTaskResult gr = guardrailResults.get(idx);
                String suffix = guardrailResults.size() > 1 ? "_" + idx : "";
                GuardrailCompiler.GuardrailRoutingResult routing = gc.compileGuardrailRouting(
                    outputGuardrails.get(idx), gr.getRefName(), contentRef,
                    config.getName(), suffix, gr.isInline(), config.getModel()
                );
                loopTasks.addAll(gr.getTasks());
                loopTasks.add(routing.getSwitchTask());
                guardrailRefs.add(new String[]{gr.getRefName(), String.valueOf(gr.isInline())});
                retryRefs.add(routing.getRetryRef());
            }
        }

        loopTasks.add(toolRouter);

        // Merge tool-level guardrail refs
        guardrailRefs.addAll(toolRoutingResult.getToolGuardrailRefs());
        retryRefs.addAll(toolRoutingResult.getToolGuardrailRetryRefs());

        // Wire all retry refs into LLM participants
        if (!retryRefs.isEmpty()) {
            Map<String, Object> participants = new LinkedHashMap<>();
            for (String rr : retryRefs) participants.put(rr, "user");
            llmTask.getInputParameters().put("participants", participants);
        }
        loopTasks.add(checkTransferTask);

        // DoWhile loop
        String loopRef = config.getName() + "_loop";
        int maxTurns = config.getMaxTurns() > 0 ? config.getMaxTurns() : 25;

        String hasToolCalls = String.format(
            "($.%s['toolCalls'] != null && $.%s['toolCalls'].length > 0)",
            llmRef, llmRef
        );
        String notTransfer = String.format("($.%s.is_transfer != true)", checkTransferRef);

        String loopReason;
        if (!guardrailRefs.isEmpty()) {
            String guardrailContinue = buildGuardrailContinue(guardrailRefs);
            loopReason = "(" + hasToolCalls + " || " + guardrailContinue + ")";
        } else {
            loopReason = hasToolCalls;
        }

        String termCondition = String.format(
            "if ( $.%s['iteration'] < %d && ($.%s['finishReason'] == 'LENGTH' || $.%s['finishReason'] == 'MAX_TOKENS' || (%s && %s)) ) { true; } else { false; }",
            loopRef, maxTurns, llmRef, llmRef, loopReason, notTransfer
        );

        Map<String, Object> loopInputs = new LinkedHashMap<>();
        loopInputs.put(loopRef, "${" + loopRef + "}");
        loopInputs.put(llmRef, "${" + llmRef + "}");
        loopInputs.put(checkTransferRef, "${" + checkTransferRef + "}");
        addGuardrailInputs(loopInputs, guardrailRefs);
        WorkflowTask loop = buildDoWhile(loopRef, termCondition, loopTasks, loopInputs);

        // After loop: SwitchTask routing to sub-agents
        WorkflowTask transferSwitch = new WorkflowTask();
        transferSwitch.setType("SWITCH");
        transferSwitch.setTaskReferenceName(config.getName() + "_transfer_check");
        transferSwitch.setEvaluatorType("value-param");
        transferSwitch.setExpression("switchCaseValue");
        transferSwitch.setInputParameters(Map.of(
            "switchCaseValue", ref(checkTransferRef + ".output.transfer_to")
        ));

        Map<String, List<WorkflowTask>> transferCases = new LinkedHashMap<>();
        for (AgentConfig sub : config.getAgents()) {
            String subTaskRef = config.getName() + "_transfer_" + sub.getName();
            WorkflowTask subTask = compileSubAgent(sub, subTaskRef, "${workflow.input.prompt}", "${workflow.input.media}");
            transferCases.put(sub.getName(), List.of(subTask));
        }
        transferSwitch.setDecisionCases(transferCases);

        // Initialize workflow variables
        Map<String, Object> initHybridVars = new LinkedHashMap<>();
        initHybridVars.put("_agent_state", new LinkedHashMap<>());
        if (hasApproval) {
            initHybridVars.put("_human_feedback", "");
        }
        WorkflowTask initStateHybrid = new WorkflowTask();
        initStateHybrid.setType("SET_VARIABLE");
        initStateHybrid.setTaskReferenceName(config.getName() + "_init_state");
        initStateHybrid.setInputParameters(initHybridVars);

        if (mcpResult != null) {
            List<WorkflowTask> allTasks = new ArrayList<>(mcpResult.getPreTasks());
            allTasks.add(initStateHybrid);
            allTasks.add(loop);
            allTasks.add(transferSwitch);
            wf.setTasks(allTasks);
        } else {
            wf.setTasks(List.of(initStateHybrid, loop, transferSwitch));
        }

        // Output: direct result or transfer result
        Map<String, Object> outputRefs = new LinkedHashMap<>();
        outputRefs.put("direct", ref(llmRef + ".output.result"));
        for (AgentConfig sub : config.getAgents()) {
            outputRefs.put(sub.getName(), ref(config.getName() + "_transfer_" + sub.getName() + ".output.result"));
        }
        wf.setOutputParameters(Map.of(
            "result", outputRefs,
            "finishReason", ref(llmRef + ".output.finishReason")
        ));
        applyTimeout(wf, config);
        return wf;
    }

    // ── Sub-agent compilation ───────────────────────────────────────

    /**
     * Compile a sub-agent into a workflow task.
     * External -> SUB_WORKFLOW referencing by name.
     * Local -> SUB_WORKFLOW with inline workflowDef.
     */
    WorkflowTask compileSubAgent(AgentConfig sub, String taskRef, String promptRef, String mediaRef) {
        WorkflowTask task = new WorkflowTask();
        task.setTaskReferenceName(taskRef);

        Map<String, Object> inputs = new LinkedHashMap<>();
        inputs.put("prompt", promptRef);
        inputs.put("media", mediaRef);
        inputs.put("session_id", "${workflow.input.session_id}");
        // When includeContents is "none", signal the sub-workflow to skip parent context
        if ("none".equalsIgnoreCase(sub.getIncludeContents())) {
            inputs.put("include_contents", "none");
        }

        if (sub.isExternal()) {
            task.setType("SUB_WORKFLOW");
            task.setName(sub.getName());
            task.setSubWorkflowParam(new com.netflix.conductor.common.metadata.workflow.SubWorkflowParams());
            task.getSubWorkflowParam().setName(sub.getName());
            task.setInputParameters(inputs);
        } else {
            // Compile inline
            WorkflowDef subWf = compile(sub);
            task.setType("SUB_WORKFLOW");
            task.setName(sub.getName());
            task.setSubWorkflowParam(new com.netflix.conductor.common.metadata.workflow.SubWorkflowParams());
            task.getSubWorkflowParam().setName(subWf.getName());
            task.getSubWorkflowParam().setWorkflowDef(subWf);
            task.setInputParameters(inputs);
        }

        return task;
    }

    /**
     * Return the Conductor expression for a sub-agent's string result.
     * Sub-workflow tasks expose the child workflow's outputParameters directly,
     * so output.result is always the resolved string value.
     */
    static String subAgentResultRef(AgentConfig sub, String taskRef) {
        return ref(taskRef + ".output.result");
    }

    /**
     * Create an INLINE task that coerces a sub-agent's result to a string.
     * When a sub-agent's LLM ends on a tool call (no text), output.result is null.
     * This safely converts null → "", objects → JSON string, anything else → String.
     */
    static WorkflowTask createCoerceTask(String rawRef, String coerceRefName) {
        WorkflowTask task = new WorkflowTask();
        task.setType("INLINE");
        task.setTaskReferenceName(coerceRefName);
        task.setInputParameters(Map.of(
            "evaluatorType", "graaljs",
            "expression", "(function(){ var v = $.raw; " +
                "return (v == null || v === undefined) ? '' : " +
                "(typeof v === 'object' ? JSON.stringify(v) : String(v)); })()",
            "raw", rawRef
        ));
        return task;
    }

    /**
     * Return the Conductor expression for a coerced task's string result.
     */
    static String coercedRef(String coerceRefName) {
        return ref(coerceRefName + ".output.result");
    }

    // ── Shared helpers ──────────────────────────────────────────────

    WorkflowDef createWorkflow(AgentConfig config) {
        WorkflowDef wf = new WorkflowDef();
        wf.setName(config.getName());
        wf.setVersion(1);
        wf.setDescription("Agent workflow for " + config.getName());
        // Match Python SDK's ConductorWorkflow defaults
        wf.setTimeoutSeconds(60L);
        wf.setTimeoutPolicy(null);
        wf.setInputParameters(WORKFLOW_INPUTS);
        return wf;
    }

    WorkflowTask buildLlmTask(AgentConfig config, ParsedModel parsed, String llmRef, List<Map<String, Object>> toolSpecs) {
        WorkflowTask llm = new WorkflowTask();
        llm.setName("LLM_CHAT_COMPLETE");
        llm.setTaskReferenceName(llmRef);
        llm.setType("LLM_CHAT_COMPLETE");

        Map<String, Object> inputs = new LinkedHashMap<>();
        inputs.put("llmProvider", parsed.getProvider());
        inputs.put("model", parsed.getModel());

        // Build messages
        List<Object> messages = new ArrayList<>();

        // Handle instructions
        Object instructions = config.getInstructions();
        boolean useTemplate = instructions instanceof Map &&
            ((Map<?, ?>) instructions).containsKey("name") &&
            ((Map<?, ?>) instructions).containsKey("type") &&
            "prompt_template".equals(((Map<?, ?>) instructions).get("type"));

        if (useTemplate) {
            @SuppressWarnings("unchecked")
            Map<String, Object> tmpl = (Map<String, Object>) instructions;
            inputs.put("instructionsTemplate", tmpl.get("name"));
            if (tmpl.get("variables") != null) {
                inputs.put("templateVariables", tmpl.get("variables"));
            }
            if (tmpl.get("version") != null) {
                inputs.put("promptVersion", tmpl.get("version"));
            }
        } else {
            // Inline string instructions
            String instrText = instructions != null ? instructions.toString() : "";
            if (toolSpecs != null && instrText.isEmpty()) {
                instrText = "You are a helpful assistant.";
            }

            // Append structured output schema to system prompt (both tool and simple agents)
            if (config.getOutputType() != null && config.getOutputType().getSchema() != null) {
                @SuppressWarnings("unchecked")
                Map<String, Object> schema = config.getOutputType().getSchema();
                Object properties = schema.get("properties");
                String schemaStr = properties != null ? pythonDictRepr(properties) : schema.toString();
                if (toolSpecs != null) {
                    instrText += "\n\nWhen providing your final answer, respond "
                        + "with a JSON object matching this schema: " + schemaStr + ". "
                        + "Output only valid JSON.";
                } else {
                    instrText += (instrText.isEmpty() ? "" : "\n\n")
                        + "Respond with a JSON object matching this schema: "
                        + schemaStr + ". Output only valid JSON, no other text.";
                    inputs.put("jsonOutput", true);
                }
            }

            // Append code execution instructions (both tool and simple agents)
            if (config.getCodeExecution() != null && config.getCodeExecution().isEnabled()) {
                instrText += "\n\n" + buildCodeExecInstructions(config);
            }

            // Append CLI command execution instructions
            if (config.getCliConfig() != null && config.getCliConfig().isEnabled()) {
                instrText += "\n\n" + buildCliInstructions(config);
            }

            // Planner: enhance instructions with plan-then-execute prompt
            if (Boolean.TRUE.equals(config.getPlanner())) {
                instrText += "\n\nBefore executing, create a step-by-step plan. "
                        + "Think through each step carefully, then execute the plan "
                        + "systematically using your available tools. After each step, "
                        + "verify progress before moving to the next.";
            }

            if (!instrText.isEmpty()) {
                messages.add(Map.of("role", "system", "message", instrText));
            }
        }

        // Memory messages
        if (config.getMemory() != null && config.getMemory().getMessages() != null) {
            messages.addAll(config.getMemory().getMessages());
        }

        // User message
        messages.add(USER_MESSAGE);

        inputs.put("messages", messages);

        if (toolSpecs != null) {
            inputs.put("tools", toolSpecs);
        }

        if (config.getMaxTokens() != null) {
            inputs.put("maxTokens", config.getMaxTokens());
        }

        // Temperature: default 0 for tool agents, null otherwise
        if (config.getTemperature() != null) {
            inputs.put("temperature", config.getTemperature());
        } else if (toolSpecs != null) {
            inputs.put("temperature", 0);
        }

        // Thinking config: extended reasoning
        if (config.getThinkingConfig() != null && config.getThinkingConfig().isEnabled()) {
            Map<String, Object> thinking = new LinkedHashMap<>();
            thinking.put("enabled", true);
            if (config.getThinkingConfig().getBudgetTokens() != null) {
                thinking.put("budgetTokens", config.getThinkingConfig().getBudgetTokens());
            }
            inputs.put("thinkingConfig", thinking);
        }

        llm.setInputParameters(inputs);
        return llm;
    }

    WorkflowTask buildDoWhile(String loopRef, String termCondition, List<WorkflowTask> loopTasks,
                              Map<String, Object> inputParams) {
        WorkflowTask doWhile = new WorkflowTask();
        doWhile.setType("DO_WHILE");
        doWhile.setTaskReferenceName(loopRef);
        doWhile.setLoopCondition(termCondition);
        doWhile.setLoopOver(loopTasks);
        doWhile.setInputParameters(inputParams);
        return doWhile;
    }

    void addGuardrailInputs(Map<String, Object> inputs, List<String[]> guardrailRefs) {
        for (String[] gr : guardrailRefs) {
            String refName = gr[0];
            inputs.put(refName, "${" + refName + "}");
        }
    }

    /**
     * Build a post-loop InlineTask that resolves the final output.
     * Checks workflow variables for guardrail fix or human edit overrides.
     */
    WorkflowTask buildResolveOutputTask(String resolveRef, String llmRef) {
        WorkflowTask task = new WorkflowTask();
        task.setType("INLINE");
        task.setTaskReferenceName(resolveRef);

        Map<String, Object> inputs = new LinkedHashMap<>();
        inputs.put("evaluatorType", "graaljs");
        inputs.put("expression", JavaScriptBuilder.resolveOutputScript());
        inputs.put("llm_result", ref(llmRef + ".output.result"));
        inputs.put("finish_reason", ref(llmRef + ".output.finishReason"));
        inputs.put("fixed_output", "${workflow.variables._fixed_output}");
        inputs.put("edited_output", "${workflow.variables._human_edited_output}");
        task.setInputParameters(inputs);

        return task;
    }

    List<GuardrailConfig> getOutputGuardrails(AgentConfig config) {
        if (config.getGuardrails() == null) return List.of();
        return config.getGuardrails().stream()
            .filter(g -> "output".equals(g.getPosition()))
            .toList();
    }

    String buildGuardrailContinue(List<String[]> guardrailRefs) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < guardrailRefs.size(); i++) {
            if (i > 0) sb.append(" || ");
            String refName = guardrailRefs.get(i)[0];
            boolean isInline = Boolean.parseBoolean(guardrailRefs.get(i)[1]);
            if (isInline) {
                sb.append("$.").append(refName).append(".result.should_continue == true");
            } else {
                sb.append("$.").append(refName).append(".should_continue == true");
            }
        }
        return sb.toString();
    }

    // ── Callback helpers ───────────────────────────────────────────

    /**
     * Find a callback by position from the agent's callback list.
     */
    CallbackConfig findCallback(AgentConfig config, String position) {
        if (config.getCallbacks() == null) return null;
        return config.getCallbacks().stream()
                .filter(cb -> position.equals(cb.getPosition()))
                .findFirst().orElse(null);
    }

    /**
     * Build a SIMPLE worker task for a callback.
     */
    WorkflowTask buildCallbackTask(CallbackConfig callback, String agentName, String llmRef) {
        WorkflowTask task = new WorkflowTask();
        task.setName(callback.getTaskName());
        task.setTaskReferenceName(agentName + "_" + callback.getPosition());
        task.setType("SIMPLE");

        Map<String, Object> inputs = new LinkedHashMap<>();
        inputs.put("callback_position", callback.getPosition());
        inputs.put("agent_name", agentName);
        if (llmRef != null) {
            inputs.put("llm_result", ref(llmRef + ".output.result"));
            inputs.put("tool_calls", ref(llmRef + ".output.toolCalls"));
        }
        task.setInputParameters(inputs);
        return task;
    }

    void applyTimeout(WorkflowDef wf, AgentConfig config) {
        int timeout = config.getTimeoutSeconds() > 0 ? config.getTimeoutSeconds() : timeoutSeconds;
        if (timeout > 0) {
            wf.setTimeoutSeconds((long) timeout);
            wf.setTimeoutPolicy(WorkflowDef.TimeoutPolicy.TIME_OUT_WF);
        } else {
            // Explicitly clear the base workflow timeout (60s from createBaseWorkflow)
            // so that timeout_seconds=0 means "no timeout"
            wf.setTimeoutSeconds(0L);
            wf.setTimeoutPolicy(null);
        }
    }

    static String ref(String path) {
        return "${" + path + "}";
    }

    /**
     * Recursively set task names to match the Python compiler's convention:
     * - LLM_CHAT_COMPLETE: name = "llm_chat_complete" (lowercase type)
     * - All other tasks: name = taskReferenceName
     *
     * This is called after compilation to ensure consistent naming.
     */
    static void ensureTaskNames(WorkflowTask task) {
        if (task == null) return;
        if ("LLM_CHAT_COMPLETE".equals(task.getType())) {
            task.setName("llm_chat_complete");
        } else if ("SIMPLE".equals(task.getType()) && task.getName() != null && !task.getName().isEmpty()) {
            // SIMPLE tasks: preserve the task definition name (workers poll on it)
        } else if (task.getName() == null || task.getName().isEmpty()) {
            task.setName(task.getTaskReferenceName());
        }
        if (task.getLoopOver() != null) {
            task.getLoopOver().forEach(AgentCompiler::ensureTaskNames);
        }
        if (task.getDecisionCases() != null) {
            task.getDecisionCases().values().forEach(
                tasks -> tasks.forEach(AgentCompiler::ensureTaskNames)
            );
        }
        if (task.getDefaultCase() != null) {
            task.getDefaultCase().forEach(AgentCompiler::ensureTaskNames);
        }
        if (task.getForkTasks() != null) {
            task.getForkTasks().forEach(
                branch -> branch.forEach(AgentCompiler::ensureTaskNames)
            );
        }
        // Recurse into sub-workflow's inline workflowDef
        if (task.getSubWorkflowParam() != null
                && task.getSubWorkflowParam().getWorkflowDef() != null
                && task.getSubWorkflowParam().getWorkflowDef().getTasks() != null) {
            task.getSubWorkflowParam().getWorkflowDef().getTasks()
                .forEach(AgentCompiler::ensureTaskNames);
        }
    }

    /**
     * Build code execution instruction text matching the Python compiler output.
     */
    private String buildCodeExecInstructions(AgentConfig config) {
        List<String> languages = config.getCodeExecution().getAllowedLanguages();
        String langs = (languages != null && !languages.isEmpty())
                ? String.join(", ", languages)
                : "python, javascript, bash";
        String msg = "You have code execution capabilities. Use the execute_code tool to write and run code. Supported languages: " + langs + "."
                + " Each execution runs in an isolated environment — no state, variables, or imports persist between calls."
                + " Always include all necessary imports at the top of every code block (e.g. import subprocess, import os, import json).";
        if (config.getCodeExecution().getAllowedCommands() != null && !config.getCodeExecution().getAllowedCommands().isEmpty()) {
            String cmds = String.join(", ", config.getCodeExecution().getAllowedCommands());
            msg += " Allowed shell commands: " + cmds + ". Do not use other commands.";
        }
        return msg;
    }

    /**
     * Build CLI command execution instruction text for the system prompt.
     */
    private String buildCliInstructions(AgentConfig config) {
        String msg = "You have CLI command execution capabilities. "
            + "Use the run_command tool to execute shell commands directly. "
            + "By default commands run without a shell interpreter (safer). "
            + "Set shell=True only when you need pipes, redirects, or glob expansion.";
        if (config.getCliConfig().getAllowedCommands() != null
                && !config.getCliConfig().getAllowedCommands().isEmpty()) {
            String cmds = String.join(", ", config.getCliConfig().getAllowedCommands());
            msg += " Allowed commands: " + cmds + ". Do not use other commands.";
        }
        if (!config.getCliConfig().isAllowShell()) {
            msg += " Shell mode is disabled — do not set shell=True.";
        }
        return msg;
    }

    /**
     * Format a Java object as Python dict repr: {'key': 'value', ...}
     * This matches Python's str() on a dict for system prompt embedding.
     */
    @SuppressWarnings("unchecked")
    static String pythonDictRepr(Object obj) {
        if (obj == null) return "None";
        if (obj instanceof Map<?, ?> map) {
            StringBuilder sb = new StringBuilder("{");
            boolean first = true;
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                if (!first) sb.append(", ");
                first = false;
                sb.append("'").append(entry.getKey()).append("': ").append(pythonDictRepr(entry.getValue()));
            }
            sb.append("}");
            return sb.toString();
        }
        if (obj instanceof List<?> list) {
            StringBuilder sb = new StringBuilder("[");
            boolean first = true;
            for (Object item : list) {
                if (!first) sb.append(", ");
                first = false;
                sb.append(pythonDictRepr(item));
            }
            sb.append("]");
            return sb.toString();
        }
        if (obj instanceof String) {
            return "'" + obj + "'";
        }
        if (obj instanceof Boolean) {
            return (Boolean) obj ? "True" : "False";
        }
        if (obj instanceof Number) {
            return obj.toString();
        }
        return "'" + obj + "'";
    }

    /**
     * Recursively walk the config tree and collect capability tags.
     */
    static Set<String> collectCapabilities(AgentConfig config) {
        Set<String> caps = new LinkedHashSet<>();
        boolean hasAgents = config.getAgents() != null && !config.getAgents().isEmpty();
        boolean hasTools = config.getTools() != null && !config.getTools().isEmpty();

        if (hasAgents && hasTools) {
            caps.add("tool-calling");
            caps.add("multi-agent-hybrid");
        } else if (hasAgents) {
            String strategy = config.getStrategy() != null ? config.getStrategy() : "handoff";
            caps.add("multi-agent-" + strategy.replace("_", "-"));
        } else if (hasTools) {
            caps.add("tool-calling");
        } else {
            caps.add("simple");
        }

        // Recurse into sub-agents
        if (hasAgents) {
            for (AgentConfig sub : config.getAgents()) {
                caps.addAll(collectCapabilities(sub));
            }
        }
        return caps;
    }

    // Setters for configuration
    public void setTimeoutSeconds(int timeoutSeconds) {
        this.timeoutSeconds = timeoutSeconds;
    }

    public void setLlmRetryCount(int llmRetryCount) {
        this.llmRetryCount = llmRetryCount;
    }
}
