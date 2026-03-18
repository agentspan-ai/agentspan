/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.compiler;

import com.netflix.conductor.common.metadata.workflow.WorkflowDef;
import com.netflix.conductor.common.metadata.workflow.WorkflowTask;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import dev.agentspan.runtime.model.*;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.*;

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
        // Should have SET_VARIABLE (init state) + DoWhile loop
        assertThat(wf.getTasks()).hasSize(2);
        assertThat(wf.getTasks().get(0).getType()).isEqualTo("SET_VARIABLE");
        WorkflowTask loop = wf.getTasks().get(1);
        assertThat(loop.getType()).isEqualTo("DO_WHILE");
        assertThat(loop.getTaskReferenceName()).isEqualTo("tool_agent_loop");

        // Loop should contain LLM + tool_router at minimum
        assertThat(loop.getLoopOver().size()).isGreaterThanOrEqualTo(2);
        assertThat(loop.getLoopOver().get(0).getType()).isEqualTo("LLM_CHAT_COMPLETE");
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

        // init_state + loop
        WorkflowTask loop = wf.getTasks().get(1);
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

        // init_state + loop
        WorkflowTask loop = wf.getTasks().get(1);
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

        // Should have init_state + DoWhile + transfer switch
        assertThat(wf.getTasks().size()).isGreaterThanOrEqualTo(3);
        assertThat(wf.getTasks().get(0).getType()).isEqualTo("SET_VARIABLE");
        assertThat(wf.getTasks().get(1).getType()).isEqualTo("DO_WHILE");
        assertThat(wf.getTasks().get(2).getType()).isEqualTo("SWITCH");
    }

    @Test
    void testExternalAgentCannotBeCompiled() {
        AgentConfig config = AgentConfig.builder()
            .name("external_agent")
            .external(true)
            .build();

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
        assertThat(AgentCompiler.subAgentResultRef(withTools, "ref1"))
            .isEqualTo("${ref1.output.result}");

        // Simple agent -> .output.result
        AgentConfig simple = AgentConfig.builder()
            .name("agent2")
            .model("openai/gpt-4o")
            .build();
        assertThat(AgentCompiler.subAgentResultRef(simple, "ref2"))
            .isEqualTo("${ref2.output.result}");

        // External agent -> .output.result
        AgentConfig external = AgentConfig.builder()
            .name("agent3")
            .external(true)
            .build();
        assertThat(AgentCompiler.subAgentResultRef(external, "ref3"))
            .isEqualTo("${ref3.output.result}");
    }

    @Test
    void testCompileWithPromptTemplate() {
        AgentConfig config = AgentConfig.builder()
            .name("template_agent")
            .model("openai/gpt-4o")
            .instructions(Map.of(
                "type", "prompt_template",
                "name", "my_template",
                "variables", Map.of("role", "assistant"),
                "version", 1
            ))
            .build();

        WorkflowDef wf = compiler.compile(config);
        WorkflowTask llm = wf.getTasks().get(0);
        assertThat(llm.getInputParameters().get("instructionsTemplate")).isEqualTo("my_template");
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
                CallbackConfig.builder().position("before_model").taskName("log_before").build(),
                CallbackConfig.builder().position("after_model").taskName("inspect_after").build(),
                CallbackConfig.builder().position("before_agent").taskName("agent_start").build(),
                CallbackConfig.builder().position("after_agent").taskName("agent_end").build()
            ))
            .build();

        WorkflowDef wf = compiler.compile(config);

        // Should have: before_agent + init_state + DoWhile + after_agent
        assertThat(wf.getTasks()).hasSize(4);

        // First task: before_agent callback (SIMPLE worker)
        WorkflowTask beforeAgent = wf.getTasks().get(0);
        assertThat(beforeAgent.getType()).isEqualTo("SIMPLE");
        assertThat(beforeAgent.getName()).isEqualTo("agent_start");
        assertThat(beforeAgent.getTaskReferenceName()).isEqualTo("callback_agent_before_agent");
        assertThat(beforeAgent.getInputParameters().get("callback_position")).isEqualTo("before_agent");

        // Second task: init_state SET_VARIABLE
        assertThat(wf.getTasks().get(1).getType()).isEqualTo("SET_VARIABLE");

        // Third task: DoWhile loop
        WorkflowTask loop = wf.getTasks().get(2);
        assertThat(loop.getType()).isEqualTo("DO_WHILE");

        // Inside loop: before_model + LLM + after_model + guardrails + tool_router + ...
        List<WorkflowTask> loopTasks = loop.getLoopOver();
        // First in loop should be before_model callback
        assertThat(loopTasks.get(0).getType()).isEqualTo("SIMPLE");
        assertThat(loopTasks.get(0).getName()).isEqualTo("log_before");
        // Second should be LLM
        assertThat(loopTasks.get(1).getType()).isEqualTo("LLM_CHAT_COMPLETE");
        // Third should be after_model callback
        assertThat(loopTasks.get(2).getType()).isEqualTo("SIMPLE");
        assertThat(loopTasks.get(2).getName()).isEqualTo("inspect_after");
        // after_model should have llm_result input wired
        assertThat(loopTasks.get(2).getInputParameters().get("llm_result")).isNotNull();

        // Last task: after_agent callback
        WorkflowTask afterAgent = wf.getTasks().get(3);
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

        // Should have: init_state + outer DO_WHILE (containing inner loop + check)
        assertThat(wf.getTasks()).hasSize(2);
        assertThat(wf.getTasks().get(0).getType()).isEqualTo("SET_VARIABLE");

        WorkflowTask outerLoop = wf.getTasks().get(1);
        assertThat(outerLoop.getType()).isEqualTo("DO_WHILE");
        assertThat(outerLoop.getTaskReferenceName()).isEqualTo("filing_agent_required_tools_loop");

        // Outer loop should contain: inner loop + INLINE check
        assertThat(outerLoop.getLoopOver()).hasSize(2);
        assertThat(outerLoop.getLoopOver().get(0).getType()).isEqualTo("DO_WHILE");
        assertThat(outerLoop.getLoopOver().get(0).getTaskReferenceName()).isEqualTo("filing_agent_loop");
        assertThat(outerLoop.getLoopOver().get(1).getType()).isEqualTo("INLINE");
        assertThat(outerLoop.getLoopOver().get(1).getTaskReferenceName()).isEqualTo("filing_agent_required_tools_check");
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

        // Should have init_state + inner loop (no outer loop)
        assertThat(wf.getTasks()).hasSize(2);
        WorkflowTask loop = wf.getTasks().get(1);
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

        // Should compile to init_state + DoWhile loop
        assertThat(wf.getTasks()).hasSize(2);
        assertThat(wf.getTasks().get(0).getType()).isEqualTo("SET_VARIABLE");
        WorkflowTask loop = wf.getTasks().get(1);
        assertThat(loop.getType()).isEqualTo("DO_WHILE");

        // LLM task should have both tools in its tool specs
        WorkflowTask llmTask = loop.getLoopOver().get(0);
        assertThat(llmTask.getType()).isEqualTo("LLM_CHAT_COMPLETE");
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> tools = (List<Map<String, Object>>) llmTask.getInputParameters().get("tools");
        assertThat(tools).hasSize(2);
        assertThat(tools.stream().map(t -> t.get("name")).toList())
            .containsExactlyInAnyOrder("researcher", "calculator");
        // agent_tool should have SUB_WORKFLOW type in spec
        Map<String, Object> agentToolSpec = tools.stream()
            .filter(t -> "researcher".equals(t.get("name"))).findFirst().orElseThrow();
        assertThat(agentToolSpec.get("type")).isEqualTo("SUB_WORKFLOW");
    }
}
