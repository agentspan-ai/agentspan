/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.compiler;

import static org.assertj.core.api.Assertions.*;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import com.netflix.conductor.common.metadata.workflow.WorkflowDef;
import com.netflix.conductor.common.metadata.workflow.WorkflowTask;

import dev.agentspan.runtime.model.*;

class AgentCompilerTest {

    private AgentCompiler compiler;

    @BeforeEach
    void setUp() {
        compiler = new AgentCompiler();
    }

    @Test
    void testCompileSimple() {
        AgentConfig config = AgentConfig.builder()
                .name("test_agent")
                .model("openai/gpt-4o")
                .instructions("You are helpful.")
                .build();

        WorkflowDef wf = compiler.compile(config);

        assertThat(wf.getName()).isEqualTo("test_agent");
        assertThat(wf.getVersion()).isEqualTo(1);
        assertThat(wf.getTasks()).hasSize(1);

        WorkflowTask llmTask = wf.getTasks().get(0);
        assertThat(llmTask.getType()).isEqualTo("LLM_CHAT_COMPLETE");
        assertThat(llmTask.getTaskReferenceName()).isEqualTo("test_agent_llm");
        assertThat(llmTask.getInputParameters().get("llmProvider")).isEqualTo("openai");
        assertThat(llmTask.getInputParameters().get("model")).isEqualTo("gpt-4o");
    }

    @Test
    void testCompileWithTools() {
        ToolConfig tool = ToolConfig.builder()
                .name("search")
                .description("Search the web")
                .inputSchema(Map.of("type", "object", "properties", Map.of("query", Map.of("type", "string"))))
                .toolType("worker")
                .build();

        AgentConfig config = AgentConfig.builder()
                .name("tool_agent")
                .model("openai/gpt-4o")
                .instructions("You can search the web.")
                .tools(List.of(tool))
                .build();

        WorkflowDef wf = compiler.compile(config);

        assertThat(wf.getName()).isEqualTo("tool_agent");
        // Should have INLINE (ctx_resolve) + SET_VARIABLE (init state) + DoWhile loop
        assertThat(wf.getTasks()).hasSize(3);
        assertThat(wf.getTasks().get(0).getType()).isEqualTo("INLINE");
        assertThat(wf.getTasks().get(1).getType()).isEqualTo("SET_VARIABLE");
        WorkflowTask loop = wf.getTasks().get(2);
        assertThat(loop.getType()).isEqualTo("DO_WHILE");
        assertThat(loop.getTaskReferenceName()).isEqualTo("tool_agent_loop");

        // Loop should contain ctx_inject + LLM + tool_router at minimum
        assertThat(loop.getLoopOver().size()).isGreaterThanOrEqualTo(3);
        assertThat(loop.getLoopOver().get(0).getType()).isEqualTo("INLINE"); // ctx_inject
        assertThat(loop.getLoopOver().get(1).getType()).isEqualTo("LLM_CHAT_COMPLETE");
    }

    @Test
    void testCompileSimpleWithGuardrails() {
        GuardrailConfig guardrail = GuardrailConfig.builder()
                .name("no_pii")
                .guardrailType("regex")
                .position("output")
                .onFail("retry")
                .patterns(List.of("\\d{3}-\\d{2}-\\d{4}"))
                .mode("block")
                .build();

        AgentConfig config = AgentConfig.builder()
                .name("guarded_agent")
                .model("openai/gpt-4o")
                .instructions("Be helpful.")
                .guardrails(List.of(guardrail))
                .build();

        WorkflowDef wf = compiler.compile(config);

        // Should wrap in DoWhile + resolve_output
        assertThat(wf.getTasks()).hasSize(2);
        WorkflowTask loop = wf.getTasks().get(0);
        assertThat(loop.getType()).isEqualTo("DO_WHILE");
        WorkflowTask resolve = wf.getTasks().get(1);
        assertThat(resolve.getType()).isEqualTo("INLINE");
        assertThat(resolve.getTaskReferenceName()).isEqualTo("guarded_agent_resolve_output");

        // Loop should have LLM + guardrail + guardrail_route
        assertThat(loop.getLoopOver().size()).isGreaterThanOrEqualTo(3);
    }

    @Test
    void testCompileWithTermination() {
        TerminationConfig term = TerminationConfig.builder()
                .type("text_mention")
                .text("DONE")
                .caseSensitive(false)
                .build();

        ToolConfig tool = ToolConfig.builder()
                .name("calc")
                .description("Calculator")
                .inputSchema(Map.of("type", "object"))
                .toolType("worker")
                .build();

        AgentConfig config = AgentConfig.builder()
                .name("term_agent")
                .model("openai/gpt-4o")
                .tools(List.of(tool))
                .termination(term)
                .build();

        WorkflowDef wf = compiler.compile(config);

        // ctx_resolve + init_state + loop
        WorkflowTask loop = wf.getTasks().get(2);
        assertThat(loop.getType()).isEqualTo("DO_WHILE");

        // Loop condition should include termination check
        String loopCondition = loop.getLoopCondition();
        assertThat(loopCondition).contains("term_agent_termination.should_continue");
    }

    @Test
    void testCompileWithStopWhen() {
        ToolConfig tool = ToolConfig.builder()
                .name("search")
                .description("Search")
                .inputSchema(Map.of("type", "object"))
                .toolType("worker")
                .build();

        AgentConfig config = AgentConfig.builder()
                .name("stop_agent")
                .model("openai/gpt-4o")
                .tools(List.of(tool))
                .stopWhen(WorkerRef.builder().taskName("stop_agent_stop_when").build())
                .build();

        WorkflowDef wf = compiler.compile(config);

        // ctx_resolve + init_state + loop
        WorkflowTask loop = wf.getTasks().get(2);
        String loopCondition = loop.getLoopCondition();
        assertThat(loopCondition).contains("stop_agent_stop_when.should_continue");
    }

    @Test
    void testCompileHybrid() {
        ToolConfig tool = ToolConfig.builder()
                .name("search")
                .description("Search the web")
                .inputSchema(Map.of("type", "object"))
                .toolType("worker")
                .build();

        AgentConfig subAgent = AgentConfig.builder()
                .name("summarizer")
                .model("openai/gpt-4o")
                .instructions("Summarize the conversation.")
                .build();

        AgentConfig config = AgentConfig.builder()
                .name("hybrid_agent")
                .model("openai/gpt-4o")
                .instructions("You are a research assistant.")
                .tools(List.of(tool))
                .agents(List.of(subAgent))
                .build();

        WorkflowDef wf = compiler.compile(config);

        // Should have ctx_resolve + init_state + DoWhile + transfer switch
        assertThat(wf.getTasks().size()).isGreaterThanOrEqualTo(4);
        assertThat(wf.getTasks().get(0).getType()).isEqualTo("INLINE"); // ctx_resolve
        assertThat(wf.getTasks().get(1).getType()).isEqualTo("SET_VARIABLE");
        assertThat(wf.getTasks().get(2).getType()).isEqualTo("DO_WHILE");
        assertThat(wf.getTasks().get(3).getType()).isEqualTo("SWITCH");
    }

    @Test
    void testExternalAgentCannotBeCompiled() {
        AgentConfig config =
                AgentConfig.builder().name("external_agent").external(true).build();

        assertThatThrownBy(() -> compiler.compile(config))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Cannot compile external agent");
    }

    @Test
    void testSubAgentResultRef() {
        // All sub-workflow tasks use .output.result (Conductor SUB_WORKFLOW
        // exposes child workflow's outputParameters directly)

        // Agent with tools -> .output.result
        AgentConfig withTools = AgentConfig.builder()
                .name("agent1")
                .model("openai/gpt-4o")
                .tools(List.of(ToolConfig.builder().name("t").toolType("worker").build()))
                .build();
        assertThat(AgentCompiler.subAgentResultRef(withTools, "ref1")).isEqualTo("${ref1.output.result}");

        // Simple agent -> .output.result
        AgentConfig simple =
                AgentConfig.builder().name("agent2").model("openai/gpt-4o").build();
        assertThat(AgentCompiler.subAgentResultRef(simple, "ref2")).isEqualTo("${ref2.output.result}");

        // External agent -> .output.result
        AgentConfig external =
                AgentConfig.builder().name("agent3").external(true).build();
        assertThat(AgentCompiler.subAgentResultRef(external, "ref3")).isEqualTo("${ref3.output.result}");
    }

    @Test
    void testCompileWithPromptTemplate() {
        AgentConfig config = AgentConfig.builder()
                .name("template_agent")
                .model("openai/gpt-4o")
                .instructions(Map.of(
                        "type",
                        "prompt_template",
                        "name",
                        "my_template",
                        "variables",
                        Map.of("role", "assistant"),
                        "version",
                        1))
                .build();

        WorkflowDef wf = compiler.compile(config);
        WorkflowTask llm = wf.getTasks().get(0);
        assertThat(llm.getInputParameters().get("instructionsTemplate")).isEqualTo("my_template");
    }

    @Test
    void testCompileWithDynamicInstructions() {
        AgentConfig config = AgentConfig.builder()
                .name("dynamic_agent")
                .model("openai/gpt-4o")
                .instructions(Map.of(
                        "_worker_ref", "get_dynamic_instructions",
                        "description", "Generate dynamic instructions"))
                .build();

        WorkflowDef wf = compiler.compile(config);

        assertThat(wf.getTasks()).hasSize(3);

        WorkflowTask workerTask = wf.getTasks().get(0);
        assertThat(workerTask.getType()).isEqualTo("SIMPLE");
        assertThat(workerTask.getName()).isEqualTo("get_dynamic_instructions");
        assertThat(workerTask.getTaskReferenceName()).isEqualTo("dynamic_agent_instructions_worker");

        WorkflowTask normalizeTask = wf.getTasks().get(1);
        assertThat(normalizeTask.getType()).isEqualTo("INLINE");
        assertThat(normalizeTask.getTaskReferenceName()).isEqualTo("dynamic_agent_instructions");

        WorkflowTask llmTask = wf.getTasks().get(2);
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> messages =
                (List<Map<String, Object>>) llmTask.getInputParameters().get("messages");
        String systemMsg = messages.stream()
                .filter(m -> "system".equals(m.get("role")))
                .map(m -> (String) m.get("message"))
                .findFirst()
                .orElse("");
        assertThat(systemMsg).contains("${dynamic_agent_instructions.output.result}");
    }

    @Test
    void testCompileWithOutputType() {
        AgentConfig config = AgentConfig.builder()
                .name("structured_agent")
                .model("openai/gpt-4o")
                .instructions("Return structured data.")
                .outputType(OutputTypeConfig.builder()
                        .schema(Map.of("properties", Map.of("name", Map.of("type", "string"))))
                        .className("Person")
                        .build())
                .build();

        WorkflowDef wf = compiler.compile(config);
        WorkflowTask llm = wf.getTasks().get(0);
        assertThat(llm.getInputParameters().get("jsonOutput")).isEqualTo(true);
    }

    @Test
    void testCompileWithCallbacks() {
        ToolConfig tool = ToolConfig.builder()
                .name("search")
                .description("Search")
                .inputSchema(Map.of("type", "object"))
                .toolType("worker")
                .build();

        AgentConfig config = AgentConfig.builder()
                .name("callback_agent")
                .model("openai/gpt-4o")
                .instructions("You are helpful.")
                .tools(List.of(tool))
                .callbacks(List.of(
                        CallbackConfig.builder()
                                .position("before_model")
                                .taskName("log_before")
                                .build(),
                        CallbackConfig.builder()
                                .position("after_model")
                                .taskName("inspect_after")
                                .build(),
                        CallbackConfig.builder()
                                .position("before_agent")
                                .taskName("agent_start")
                                .build(),
                        CallbackConfig.builder()
                                .position("after_agent")
                                .taskName("agent_end")
                                .build()))
                .build();

        WorkflowDef wf = compiler.compile(config);

        // Should have: before_agent + ctx_resolve + init_state + DoWhile + after_agent
        assertThat(wf.getTasks()).hasSize(5);

        // First task: before_agent callback (SIMPLE worker)
        WorkflowTask beforeAgent = wf.getTasks().get(0);
        assertThat(beforeAgent.getType()).isEqualTo("SIMPLE");
        assertThat(beforeAgent.getName()).isEqualTo("agent_start");
        assertThat(beforeAgent.getTaskReferenceName()).isEqualTo("callback_agent_before_agent");
        assertThat(beforeAgent.getInputParameters().get("callback_position")).isEqualTo("before_agent");

        // Second task: ctx_resolve INLINE
        assertThat(wf.getTasks().get(1).getType()).isEqualTo("INLINE");

        // Third task: init_state SET_VARIABLE
        assertThat(wf.getTasks().get(2).getType()).isEqualTo("SET_VARIABLE");

        // Fourth task: DoWhile loop
        WorkflowTask loop = wf.getTasks().get(3);
        assertThat(loop.getType()).isEqualTo("DO_WHILE");

        // Inside loop: ctx_inject + before_model + LLM + after_model + guardrails + tool_router + ...
        List<WorkflowTask> loopTasks = loop.getLoopOver();
        // First in loop should be ctx_inject INLINE
        assertThat(loopTasks.get(0).getType()).isEqualTo("INLINE"); // ctx_inject
        // Second in loop should be before_model callback
        assertThat(loopTasks.get(1).getType()).isEqualTo("SIMPLE");
        assertThat(loopTasks.get(1).getName()).isEqualTo("log_before");
        // Third should be LLM
        assertThat(loopTasks.get(2).getType()).isEqualTo("LLM_CHAT_COMPLETE");
        // Fourth should be after_model callback
        assertThat(loopTasks.get(3).getType()).isEqualTo("SIMPLE");
        assertThat(loopTasks.get(3).getName()).isEqualTo("inspect_after");
        // after_model should have llm_result input wired
        assertThat(loopTasks.get(3).getInputParameters().get("llm_result")).isNotNull();

        // Last task: after_agent callback
        WorkflowTask afterAgent = wf.getTasks().get(4);
        assertThat(afterAgent.getType()).isEqualTo("SIMPLE");
        assertThat(afterAgent.getName()).isEqualTo("agent_end");
    }

    @Test
    void testCompileWithRequiredTools() {
        ToolConfig tool = ToolConfig.builder()
                .name("submit_filing")
                .description("Submit a filing")
                .inputSchema(Map.of("type", "object"))
                .toolType("worker")
                .build();

        AgentConfig config = AgentConfig.builder()
                .name("filing_agent")
                .model("openai/gpt-4o")
                .instructions("You must submit a filing.")
                .tools(List.of(tool))
                .requiredTools(List.of("submit_filing"))
                .build();

        WorkflowDef wf = compiler.compile(config);

        // Should have: ctx_resolve + init_state + outer DO_WHILE (containing inner loop + check)
        assertThat(wf.getTasks()).hasSize(3);
        assertThat(wf.getTasks().get(0).getType()).isEqualTo("INLINE"); // ctx_resolve
        assertThat(wf.getTasks().get(1).getType()).isEqualTo("SET_VARIABLE");

        WorkflowTask outerLoop = wf.getTasks().get(2);
        assertThat(outerLoop.getType()).isEqualTo("DO_WHILE");
        assertThat(outerLoop.getTaskReferenceName()).isEqualTo("filing_agent_required_tools_loop");

        // Outer loop should contain: inner loop + INLINE check
        assertThat(outerLoop.getLoopOver()).hasSize(2);
        assertThat(outerLoop.getLoopOver().get(0).getType()).isEqualTo("DO_WHILE");
        assertThat(outerLoop.getLoopOver().get(0).getTaskReferenceName()).isEqualTo("filing_agent_loop");
        assertThat(outerLoop.getLoopOver().get(1).getType()).isEqualTo("INLINE");
        assertThat(outerLoop.getLoopOver().get(1).getTaskReferenceName())
                .isEqualTo("filing_agent_required_tools_check");
    }

    @Test
    void testCompileWithoutRequiredToolsHasNoOuterLoop() {
        ToolConfig tool = ToolConfig.builder()
                .name("search")
                .description("Search")
                .inputSchema(Map.of("type", "object"))
                .toolType("worker")
                .build();

        AgentConfig config = AgentConfig.builder()
                .name("normal_agent")
                .model("openai/gpt-4o")
                .tools(List.of(tool))
                .build();

        WorkflowDef wf = compiler.compile(config);

        // Should have ctx_resolve + init_state + inner loop (no outer loop)
        assertThat(wf.getTasks()).hasSize(3);
        WorkflowTask loop = wf.getTasks().get(2);
        assertThat(loop.getType()).isEqualTo("DO_WHILE");
        assertThat(loop.getTaskReferenceName()).isEqualTo("normal_agent_loop");
    }

    @Test
    void testCompileWithAgentTool() {
        // Agent tool: a tool that wraps another agent
        ToolConfig agentTool = ToolConfig.builder()
                .name("researcher")
                .description("Research agent")
                .toolType("agent_tool")
                .inputSchema(Map.of(
                        "type", "object",
                        "properties", Map.of("request", Map.of("type", "string")),
                        "required", List.of("request")))
                .config(Map.of("workflowName", "researcher_agent_wf"))
                .build();

        ToolConfig regularTool = ToolConfig.builder()
                .name("calculator")
                .description("Math calculator")
                .inputSchema(Map.of("type", "object"))
                .toolType("worker")
                .build();

        AgentConfig config = AgentConfig.builder()
                .name("manager")
                .model("openai/gpt-4o")
                .instructions("You manage a research team.")
                .tools(List.of(agentTool, regularTool))
                .build();

        WorkflowDef wf = compiler.compile(config);

        // Should compile to ctx_resolve + init_state + DoWhile loop
        assertThat(wf.getTasks()).hasSize(3);
        assertThat(wf.getTasks().get(0).getType()).isEqualTo("INLINE"); // ctx_resolve
        assertThat(wf.getTasks().get(1).getType()).isEqualTo("SET_VARIABLE");
        WorkflowTask loop = wf.getTasks().get(2);
        assertThat(loop.getType()).isEqualTo("DO_WHILE");

        // LLM task should have both tools in its tool specs (after ctx_inject at index 0)
        WorkflowTask llmTask = loop.getLoopOver().get(1);
        assertThat(llmTask.getType()).isEqualTo("LLM_CHAT_COMPLETE");
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> tools =
                (List<Map<String, Object>>) llmTask.getInputParameters().get("tools");
        assertThat(tools).hasSize(2);
        assertThat(tools.stream().map(t -> t.get("name")).toList())
                .containsExactlyInAnyOrder("researcher", "calculator");
        // agent_tool should have SUB_WORKFLOW type in spec
        Map<String, Object> agentToolSpec = tools.stream()
                .filter(t -> "researcher".equals(t.get("name")))
                .findFirst()
                .orElseThrow();
        assertThat(agentToolSpec.get("type")).isEqualTo("SUB_WORKFLOW");
    }

    @Test
    void testCompileFrameworkPassthrough() {
        // Build a passthrough AgentConfig as produced by LangGraphNormalizer
        dev.agentspan.runtime.model.ToolConfig worker = dev.agentspan.runtime.model.ToolConfig.builder()
                .name("my_graph")
                .toolType("worker")
                .build();

        AgentConfig config = AgentConfig.builder()
                .name("my_graph")
                .metadata(Map.of("_framework_passthrough", true))
                .tools(List.of(worker))
                .build();

        WorkflowDef wf = compiler.compile(config);

        assertThat(wf.getName()).isEqualTo("my_graph");
        assertThat(wf.getTasks()).hasSize(1);
        WorkflowTask task = wf.getTasks().get(0);
        assertThat(task.getType()).isEqualTo("SIMPLE");
        assertThat(task.getName()).isEqualTo("my_graph");
        assertThat(task.getTaskReferenceName()).isEqualTo("_fw_task");
        // prompt/session_id/media must be wired from workflow input
        assertThat(task.getInputParameters().get("prompt")).isEqualTo("${workflow.input.prompt}");
        assertThat(task.getInputParameters().get("session_id")).isEqualTo("${workflow.input.session_id}");
        // Output must reference the _fw_task
        assertThat(wf.getOutputParameters().get("result")).isEqualTo("${_fw_task.output.result}");
    }

    @Test
    void testPassthroughGuardPreventsCrashOnNullModel() {
        // Passthrough configs have no model — this must NOT throw.
        // Without the passthrough guard, compile() falls through to compileSimple()
        // which calls ModelParser.parse(null) and throws NullPointerException.
        AgentConfig config = AgentConfig.builder()
                .name("my_graph")
                .metadata(Map.of("_framework_passthrough", true))
                .tools(List.of(dev.agentspan.runtime.model.ToolConfig.builder()
                        .name("my_graph")
                        .toolType("worker")
                        .build()))
                .build();

        assertThatNoException().isThrownBy(() -> compiler.compile(config));
    }

    // ── Graph-structure compilation tests ──────────────────────────────

    @Test
    void testCompileGraphStructureSequential() {
        // Sequential graph: __start__ → fetch → process → __end__
        Map<String, Object> graphStructure = Map.of(
                "nodes",
                        List.of(
                                Map.of("name", "fetch", "_worker_ref", "seq_graph_fetch"),
                                Map.of("name", "process", "_worker_ref", "seq_graph_process")),
                "edges",
                        List.of(
                                Map.of("source", "__start__", "target", "fetch"),
                                Map.of("source", "fetch", "target", "process"),
                                Map.of("source", "process", "target", "__end__")),
                "input_key", "query");

        AgentConfig config = AgentConfig.builder()
                .name("seq_graph")
                .metadata(Map.of("_graph_structure", graphStructure))
                .tools(List.of(
                        ToolConfig.builder()
                                .name("seq_graph_fetch")
                                .toolType("worker")
                                .build(),
                        ToolConfig.builder()
                                .name("seq_graph_process")
                                .toolType("worker")
                                .build()))
                .build();

        WorkflowDef wf = compiler.compile(config);

        assertThat(wf.getName()).isEqualTo("seq_graph");
        assertThat(wf.getTasks()).hasSize(2);

        WorkflowTask first = wf.getTasks().get(0);
        assertThat(first.getType()).isEqualTo("SIMPLE");
        assertThat(first.getName()).isEqualTo("seq_graph_fetch");

        WorkflowTask second = wf.getTasks().get(1);
        assertThat(second.getType()).isEqualTo("SIMPLE");
        assertThat(second.getName()).isEqualTo("seq_graph_process");

        // Second task's state should reference first task's output
        assertThat(second.getInputParameters().get("state").toString()).contains("seq_graph_fetch");
    }

    @Test
    void testCompileGraphStructureConditionalSwitch() {
        // Graph with conditional routing: __start__ → classify → SWITCH(positive | negative)
        Map<String, Object> graphStructure = Map.of(
                "nodes",
                        List.of(
                                Map.of("name", "classify", "_worker_ref", "test_classify"),
                                Map.of("name", "positive", "_worker_ref", "test_positive"),
                                Map.of("name", "negative", "_worker_ref", "test_negative")),
                "edges", List.of(Map.of("source", "__start__", "target", "classify")),
                "conditional_edges",
                        List.of(Map.of(
                                "source", "classify",
                                "_router_ref", "test_classify_router",
                                "targets", Map.of("positive", "positive", "negative", "negative"))));

        AgentConfig config = AgentConfig.builder()
                .name("cond_graph")
                .model("openai/gpt-4o")
                .metadata(Map.of("_graph_structure", graphStructure))
                .tools(List.of(
                        ToolConfig.builder()
                                .name("test_classify")
                                .toolType("worker")
                                .build(),
                        ToolConfig.builder()
                                .name("test_positive")
                                .toolType("worker")
                                .build(),
                        ToolConfig.builder()
                                .name("test_negative")
                                .toolType("worker")
                                .build(),
                        ToolConfig.builder()
                                .name("test_classify_router")
                                .toolType("worker")
                                .build()))
                .build();

        WorkflowDef wf = compiler.compile(config);

        // Should contain at least: classify SIMPLE, router SIMPLE, SWITCH
        List<String> taskTypes =
                wf.getTasks().stream().map(WorkflowTask::getType).toList();
        assertThat(taskTypes).contains("SIMPLE", "SWITCH");

        // Find the router task
        WorkflowTask routerTask = wf.getTasks().stream()
                .filter(t -> "SIMPLE".equals(t.getType()) && "test_classify_router".equals(t.getName()))
                .findFirst()
                .orElse(null);
        assertThat(routerTask).isNotNull();

        // Find the SWITCH task
        WorkflowTask switchTask = wf.getTasks().stream()
                .filter(t -> "SWITCH".equals(t.getType()))
                .findFirst()
                .orElseThrow();
        assertThat(switchTask.getDecisionCases()).containsKey("positive");
        assertThat(switchTask.getDecisionCases()).containsKey("negative");
    }

    @Test
    void testCompileGraphStructureForkJoin() {
        // Fan-out from START: __start__ → pros, __start__ → cons, pros → merge, cons → merge, merge → __end__
        Map<String, Object> graphStructure = new java.util.LinkedHashMap<>();
        graphStructure.put(
                "nodes",
                List.of(
                        Map.of("name", "pros", "_worker_ref", "test_pros"),
                        Map.of("name", "cons", "_worker_ref", "test_cons"),
                        Map.of("name", "merge", "_worker_ref", "test_merge")));
        graphStructure.put(
                "edges",
                List.of(
                        Map.of("source", "__start__", "target", "pros"),
                        Map.of("source", "__start__", "target", "cons"),
                        Map.of("source", "pros", "target", "merge"),
                        Map.of("source", "cons", "target", "merge"),
                        Map.of("source", "merge", "target", "__end__")));
        graphStructure.put("_reducers", Map.of("arguments", "add"));

        Map<String, Object> metadata = new java.util.LinkedHashMap<>();
        metadata.put("_graph_structure", graphStructure);
        metadata.put("_reducers", Map.of("arguments", "add"));

        AgentConfig config = AgentConfig.builder()
                .name("fork_graph")
                .metadata(metadata)
                .tools(List.of(
                        ToolConfig.builder()
                                .name("test_pros")
                                .toolType("worker")
                                .build(),
                        ToolConfig.builder()
                                .name("test_cons")
                                .toolType("worker")
                                .build(),
                        ToolConfig.builder()
                                .name("test_merge")
                                .toolType("worker")
                                .build()))
                .build();

        WorkflowDef wf = compiler.compile(config);

        List<String> taskTypes =
                wf.getTasks().stream().map(WorkflowTask::getType).toList();

        // Should include FORK_JOIN and JOIN tasks
        assertThat(taskTypes).contains("FORK_JOIN");
        assertThat(taskTypes).contains("JOIN");

        // Should include an INLINE merge task
        WorkflowTask inlineMerge = wf.getTasks().stream()
                .filter(t -> "INLINE".equals(t.getType()))
                .findFirst()
                .orElse(null);
        assertThat(inlineMerge).isNotNull();
    }

    @Test
    void testCompileGraphStructureLlmNode() {
        // Graph with LLM node: __start__ → prepare → analyze(LLM) → __end__
        Map<String, Object> graphStructure = Map.of(
                "nodes",
                        List.of(
                                Map.of("name", "prepare", "_worker_ref", "test_prepare"),
                                Map.of(
                                        "name",
                                        "analyze",
                                        "_worker_ref",
                                        "test_analyze_prep",
                                        "_llm_node",
                                        true,
                                        "_llm_prep_ref",
                                        "test_analyze_prep",
                                        "_llm_finish_ref",
                                        "test_analyze_finish")),
                "edges",
                        List.of(
                                Map.of("source", "__start__", "target", "prepare"),
                                Map.of("source", "prepare", "target", "analyze"),
                                Map.of("source", "analyze", "target", "__end__")));

        AgentConfig config = AgentConfig.builder()
                .name("llm_graph")
                .model("openai/gpt-4o")
                .metadata(Map.of("_graph_structure", graphStructure))
                .tools(List.of(
                        ToolConfig.builder()
                                .name("test_prepare")
                                .toolType("worker")
                                .build(),
                        ToolConfig.builder()
                                .name("test_analyze_prep")
                                .toolType("worker")
                                .build(),
                        ToolConfig.builder()
                                .name("test_analyze_finish")
                                .toolType("worker")
                                .build()))
                .build();

        WorkflowDef wf = compiler.compile(config);

        List<String> taskTypes =
                wf.getTasks().stream().map(WorkflowTask::getType).toList();

        // Should contain a SWITCH task (for _skip_llm)
        assertThat(taskTypes).contains("SWITCH");

        // Find the SWITCH task for the LLM node
        WorkflowTask switchTask = wf.getTasks().stream()
                .filter(t -> "SWITCH".equals(t.getType()))
                .findFirst()
                .orElseThrow();

        // Default case should contain LLM_CHAT_COMPLETE task
        assertThat(switchTask.getDefaultCase()).isNotEmpty();
        boolean hasLlmTask =
                switchTask.getDefaultCase().stream().anyMatch(t -> "LLM_CHAT_COMPLETE".equals(t.getType()));
        assertThat(hasLlmTask).isTrue();

        // Should have an INLINE coalesce task
        WorkflowTask coalesceTask = wf.getTasks().stream()
                .filter(t -> "INLINE".equals(t.getType()))
                .findFirst()
                .orElse(null);
        assertThat(coalesceTask).isNotNull();
    }

    @Test
    void testCompileGraphStructureSubgraphNode() {
        // Build a simple sub-agent config (passthrough)
        AgentConfig subAgent = AgentConfig.builder()
                .name("sub_graph")
                .metadata(Map.of("_framework_passthrough", true))
                .tools(List.of(ToolConfig.builder()
                        .name("sub_graph")
                        .toolType("worker")
                        .build()))
                .build();

        // Graph with subgraph node: __start__ → sub → __end__
        Map<String, Object> graphStructure = Map.of(
                "nodes",
                        List.of(Map.of(
                                "name",
                                "sub",
                                "_worker_ref",
                                "test_sub_prep",
                                "_subgraph_node",
                                true,
                                "_subgraph_prep_ref",
                                "test_sub_prep",
                                "_subgraph_finish_ref",
                                "test_sub_finish")),
                "edges",
                        List.of(
                                Map.of("source", "__start__", "target", "sub"),
                                Map.of("source", "sub", "target", "__end__")));

        Map<String, Object> metadata = new java.util.LinkedHashMap<>();
        metadata.put("_graph_structure", graphStructure);
        metadata.put("_subgraph_configs", Map.of("sub", subAgent));

        AgentConfig config = AgentConfig.builder()
                .name("sg_graph")
                .metadata(metadata)
                .tools(List.of(
                        ToolConfig.builder()
                                .name("test_sub_prep")
                                .toolType("worker")
                                .build(),
                        ToolConfig.builder()
                                .name("test_sub_finish")
                                .toolType("worker")
                                .build(),
                        ToolConfig.builder()
                                .name("sub_graph")
                                .toolType("worker")
                                .build()))
                .build();

        WorkflowDef wf = compiler.compile(config);

        List<String> taskTypes =
                wf.getTasks().stream().map(WorkflowTask::getType).toList();

        // Should contain a SWITCH task (for _skip_subgraph)
        assertThat(taskTypes).contains("SWITCH");

        // Find the SWITCH task
        WorkflowTask switchTask = wf.getTasks().stream()
                .filter(t -> "SWITCH".equals(t.getType()))
                .findFirst()
                .orElseThrow();

        // Default case should contain a SUB_WORKFLOW task
        assertThat(switchTask.getDefaultCase()).isNotEmpty();
        boolean hasSubWf = switchTask.getDefaultCase().stream().anyMatch(t -> "SUB_WORKFLOW".equals(t.getType()));
        assertThat(hasSubWf).isTrue();

        // Should have an INLINE coalesce task
        WorkflowTask coalesceTask = wf.getTasks().stream()
                .filter(t -> "INLINE".equals(t.getType()))
                .findFirst()
                .orElse(null);
        assertThat(coalesceTask).isNotNull();
    }

    @Test
    void testApplyRetryPolicyMapsAllParams() {
        WorkflowTask task = new WorkflowTask();
        Map<String, Object> policy = Map.of(
                "max_attempts", 5,
                "initial_interval", 2.5,
                "backoff_factor", 3);

        AgentCompiler.applyRetryPolicy(task, policy);

        // max_attempts 5 → retryCount = 5 - 1 = 4
        assertThat(task.getRetryCount()).isEqualTo(4);
        // initial_interval and backoff_factor are stored in _retry_meta (TaskDef-level properties)
        @SuppressWarnings("unchecked")
        Map<String, Object> retryMeta =
                (Map<String, Object>) task.getInputParameters().get("_retry_meta");
        assertThat(retryMeta).isNotNull();
        assertThat(retryMeta.get("retryDelaySeconds")).isEqualTo(3);
        assertThat(retryMeta.get("backoffScaleFactor")).isEqualTo(3);
    }
}
