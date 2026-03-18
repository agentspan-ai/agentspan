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
import java.util.Set;

import static org.assertj.core.api.Assertions.*;

class MultiAgentCompilerTest {

    private AgentCompiler compiler;

    @BeforeEach
    void setUp() {
        compiler = new AgentCompiler();
    }

    private AgentConfig simpleSubAgent(String name, String instructions) {
        return AgentConfig.builder()
            .name(name)
            .model("openai/gpt-4o")
            .instructions(instructions)
            .build();
    }

    @Test
    void testHandoff() {
        AgentConfig config = AgentConfig.builder()
            .name("team")
            .model("openai/gpt-4o")
            .instructions("Route to the best agent.")
            .strategy("handoff")
            .agents(List.of(
                simpleSubAgent("agent_a", "Handle A tasks"),
                simpleSubAgent("agent_b", "Handle B tasks")
            ))
            .build();

        WorkflowDef wf = compiler.compile(config);
        assertThat(wf.getName()).isEqualTo("team");

        // Handoff: init + DoWhile loop + final LLM
        assertThat(wf.getTasks()).hasSize(3);
        assertThat(wf.getTasks().get(0).getType()).isEqualTo("SET_VARIABLE");
        assertThat(wf.getTasks().get(1).getType()).isEqualTo("DO_WHILE");

        // Loop should contain router LLM + switch with agent cases
        WorkflowTask loop = wf.getTasks().get(1);
        boolean hasSwitchInLoop = loop.getLoopOver().stream()
            .anyMatch(t -> "SWITCH".equals(t.getType()));
        assertThat(hasSwitchInLoop).isTrue();

        // Switch should have 2 cases (one per agent)
        WorkflowTask switchTask = loop.getLoopOver().stream()
            .filter(t -> "SWITCH".equals(t.getType())).findFirst().orElseThrow();
        assertThat(switchTask.getDecisionCases()).containsKeys("agent_a", "agent_b");
    }

    @Test
    void testSequential() {
        AgentConfig config = AgentConfig.builder()
            .name("pipeline")
            .model("openai/gpt-4o")
            .strategy("sequential")
            .agents(List.of(
                simpleSubAgent("writer", "Write content"),
                simpleSubAgent("reviewer", "Review content")
            ))
            .build();

        WorkflowDef wf = compiler.compile(config);

        // SUB_WORKFLOW(writer) + coerce + SUB_WORKFLOW(reviewer)
        assertThat(wf.getTasks()).hasSize(3);
        assertThat(wf.getTasks().get(0).getType()).isEqualTo("SUB_WORKFLOW");
        assertThat(wf.getTasks().get(0).getTaskReferenceName()).contains("writer");
        assertThat(wf.getTasks().get(1).getType()).isEqualTo("INLINE");
        assertThat(wf.getTasks().get(1).getTaskReferenceName()).contains("coerce");
        assertThat(wf.getTasks().get(2).getType()).isEqualTo("SUB_WORKFLOW");
        assertThat(wf.getTasks().get(2).getTaskReferenceName()).contains("reviewer");
    }

    @Test
    void testParallel() {
        AgentConfig config = AgentConfig.builder()
            .name("parallel_team")
            .model("openai/gpt-4o")
            .strategy("parallel")
            .agents(List.of(
                simpleSubAgent("analyst", "Analyze data"),
                simpleSubAgent("researcher", "Research topic")
            ))
            .build();

        WorkflowDef wf = compiler.compile(config);

        // Fork + Join + Aggregate INLINE
        assertThat(wf.getTasks()).hasSize(3);
        assertThat(wf.getTasks().get(0).getType()).isEqualTo("FORK_JOIN");
        assertThat(wf.getTasks().get(1).getType()).isEqualTo("JOIN");
        assertThat(wf.getTasks().get(2).getType()).isEqualTo("INLINE");
        assertThat(wf.getTasks().get(2).getTaskReferenceName()).isEqualTo("parallel_team_aggregate");

        // Output references the aggregate task — result is always a string
        assertThat(wf.getOutputParameters().get("result").toString()).contains("_aggregate");
        assertThat(wf.getOutputParameters()).containsKey("subResults");
    }

    @Test
    void testRoundRobin() {
        AgentConfig config = AgentConfig.builder()
            .name("discussion")
            .model("openai/gpt-4o")
            .strategy("round_robin")
            .maxTurns(10)
            .agents(List.of(
                simpleSubAgent("alice", "Alice's perspective"),
                simpleSubAgent("bob", "Bob's perspective")
            ))
            .build();

        WorkflowDef wf = compiler.compile(config);

        // Init + DoWhile
        assertThat(wf.getTasks()).hasSize(2);
        assertThat(wf.getTasks().get(0).getType()).isEqualTo("SET_VARIABLE");
        assertThat(wf.getTasks().get(1).getType()).isEqualTo("DO_WHILE");

        // DoWhile should have select + switch
        WorkflowTask loop = wf.getTasks().get(1);
        assertThat(loop.getLoopOver()).hasSize(2);
        assertThat(loop.getLoopOver().get(0).getType()).isEqualTo("INLINE");
        assertThat(loop.getLoopOver().get(1).getType()).isEqualTo("SWITCH");
    }

    @Test
    void testRandom() {
        AgentConfig config = AgentConfig.builder()
            .name("random_team")
            .model("openai/gpt-4o")
            .strategy("random")
            .agents(List.of(
                simpleSubAgent("alice", "Alice"),
                simpleSubAgent("bob", "Bob")
            ))
            .build();

        WorkflowDef wf = compiler.compile(config);

        // Init + DoWhile
        assertThat(wf.getTasks()).hasSize(2);
        WorkflowTask loop = wf.getTasks().get(1);

        // Select script should use Math.random
        WorkflowTask selectTask = loop.getLoopOver().get(0);
        String script = (String) selectTask.getInputParameters().get("expression");
        assertThat(script).contains("Math.random()");
    }

    @Test
    void testSwarm() {
        AgentConfig config = AgentConfig.builder()
            .name("swarm")
            .model("openai/gpt-4o")
            .instructions("Triage requests")
            .strategy("swarm")
            .handoffs(List.of(
                HandoffConfig.builder()
                    .type("on_text_mention")
                    .target("agent_b")
                    .text("transfer to b")
                    .build()
            ))
            .agents(List.of(
                simpleSubAgent("agent_a", "Handle A"),
                simpleSubAgent("agent_b", "Handle B")
            ))
            .build();

        WorkflowDef wf = compiler.compile(config);

        // Init + DoWhile + Final LLM
        assertThat(wf.getTasks()).hasSize(3);
        assertThat(wf.getTasks().get(1).getType()).isEqualTo("DO_WHILE");
        assertThat(wf.getTasks().get(2).getType()).isEqualTo("LLM_CHAT_COMPLETE");

        // Init should contain last_response, is_transfer, transfer_to
        WorkflowTask init = wf.getTasks().get(0);
        assertThat(init.getInputParameters()).containsKey("last_response");
        assertThat(init.getInputParameters()).containsKey("is_transfer");
        assertThat(init.getInputParameters()).containsKey("transfer_to");

        // Loop: switch + handoff_check + update_active
        WorkflowTask loop = wf.getTasks().get(1);
        assertThat(loop.getLoopOver()).hasSize(3);

        // Switch should have 3 cases: "0" (parent), "1" (agent_a), "2" (agent_b)
        WorkflowTask switchTask = loop.getLoopOver().stream()
            .filter(t -> "SWITCH".equals(t.getType())).findFirst().orElseThrow();
        assertThat(switchTask.getDecisionCases()).containsKeys("0", "1", "2");
        assertThat(switchTask.getDecisionCases()).hasSize(3);

        // Each case should have a SUB_WORKFLOW with inline workflow containing DO_WHILE with check_transfer
        for (String caseKey : List.of("0", "1", "2")) {
            List<WorkflowTask> caseTasks = switchTask.getDecisionCases().get(caseKey);
            assertThat(caseTasks).isNotEmpty();
            WorkflowTask subWfTask = caseTasks.get(0);
            assertThat(subWfTask.getType()).isEqualTo("SUB_WORKFLOW");
            // Verify inline workflow definition exists
            assertThat(subWfTask.getSubWorkflowParam()).isNotNull();
            assertThat(subWfTask.getSubWorkflowParam().getWorkflowDef()).isNotNull();
            WorkflowDef inlineWf = subWfTask.getSubWorkflowParam().getWorkflowDef();
            // Inline workflow should have init_state + DO_WHILE
            assertThat(inlineWf.getTasks()).hasSize(2);
            assertThat(inlineWf.getTasks().get(0).getType()).isEqualTo("SET_VARIABLE");
            assertThat(inlineWf.getTasks().get(1).getType()).isEqualTo("DO_WHILE");
            // DO_WHILE should contain check_transfer
            WorkflowTask innerLoop = inlineWf.getTasks().get(1);
            boolean hasCheckTransfer = innerLoop.getLoopOver().stream()
                .anyMatch(t -> t.getName() != null && t.getName().contains("check_transfer"));
            assertThat(hasCheckTransfer).isTrue();
            // Output should include is_transfer and transfer_to
            assertThat(inlineWf.getOutputParameters()).containsKey("is_transfer");
            assertThat(inlineWf.getOutputParameters()).containsKey("transfer_to");
        }

        // Handoff check inputs should include is_transfer and transfer_to
        WorkflowTask handoffTask = loop.getLoopOver().stream()
            .filter(t -> "SIMPLE".equals(t.getType())).findFirst().orElseThrow();
        assertThat(handoffTask.getInputParameters()).containsKey("is_transfer");
        assertThat(handoffTask.getInputParameters()).containsKey("transfer_to");

        // Output should reference final LLM
        assertThat(wf.getOutputParameters().get("result").toString())
            .contains("_final.output.result");

        // Loop condition should include handoff check for early termination
        assertThat(loop.getLoopCondition()).contains("handoff");
    }

    @Test
    void testManual() {
        AgentConfig config = AgentConfig.builder()
            .name("manual_team")
            .model("openai/gpt-4o")
            .strategy("manual")
            .agents(List.of(
                simpleSubAgent("writer", "Write"),
                simpleSubAgent("editor", "Edit")
            ))
            .build();

        WorkflowDef wf = compiler.compile(config);

        // Init + DoWhile
        assertThat(wf.getTasks()).hasSize(2);
        WorkflowTask loop = wf.getTasks().get(1);

        // Loop: human + process_selection + switch
        assertThat(loop.getLoopOver()).hasSize(3);
        assertThat(loop.getLoopOver().get(0).getType()).isEqualTo("HUMAN");
    }

    @Test
    void testRouter_Worker() {
        AgentConfig config = AgentConfig.builder()
            .name("routed")
            .model("openai/gpt-4o")
            .strategy("router")
            .router(WorkerRef.builder().taskName("my_router_fn").build())
            .agents(List.of(
                simpleSubAgent("agent_a", "A"),
                simpleSubAgent("agent_b", "B")
            ))
            .build();

        WorkflowDef wf = compiler.compile(config);

        // Iterative: init + DoWhile + final LLM
        assertThat(wf.getTasks()).hasSize(3);
        assertThat(wf.getTasks().get(0).getType()).isEqualTo("SET_VARIABLE");
        assertThat(wf.getTasks().get(1).getType()).isEqualTo("DO_WHILE");
        assertThat(wf.getTasks().get(2).getType()).isEqualTo("LLM_CHAT_COMPLETE");

        // Loop should contain the worker router task
        WorkflowTask loop = wf.getTasks().get(1);
        WorkflowTask routerInLoop = loop.getLoopOver().get(0);
        assertThat(routerInLoop.getType()).isEqualTo("SIMPLE");
        assertThat(routerInLoop.getName()).isEqualTo("my_router_fn");
    }

    @Test
    void testRouter_Agent() {
        AgentConfig routerAgent = AgentConfig.builder()
            .name("router_agent")
            .model("anthropic/claude-sonnet-4-20250514")
            .instructions("Route intelligently.")
            .build();

        AgentConfig config = AgentConfig.builder()
            .name("routed")
            .model("openai/gpt-4o")
            .strategy("router")
            .router(routerAgent)
            .agents(List.of(
                simpleSubAgent("agent_a", "A"),
                simpleSubAgent("agent_b", "B")
            ))
            .build();

        WorkflowDef wf = compiler.compile(config);

        // Iterative: init + DoWhile + final LLM
        assertThat(wf.getTasks()).hasSize(3);
        assertThat(wf.getTasks().get(0).getType()).isEqualTo("SET_VARIABLE");
        assertThat(wf.getTasks().get(1).getType()).isEqualTo("DO_WHILE");

        // Loop should contain router sub-workflow (using anthropic model) + annotation + switch
        WorkflowTask loop = wf.getTasks().get(1);
        boolean hasSwitchInLoop = loop.getLoopOver().stream()
            .anyMatch(t -> "SWITCH".equals(t.getType()));
        assertThat(hasSwitchInLoop).isTrue();

        // Switch should have agent cases + DONE
        WorkflowTask switchTask = loop.getLoopOver().stream()
            .filter(t -> "SWITCH".equals(t.getType())).findFirst().orElseThrow();
        assertThat(switchTask.getDecisionCases()).containsKeys("agent_a", "agent_b", "DONE");
    }

    @Test
    void testAllowedTransitions() {
        AgentConfig config = AgentConfig.builder()
            .name("constrained")
            .model("openai/gpt-4o")
            .strategy("round_robin")
            .allowedTransitions(Map.of(
                "alice", List.of("bob"),
                "bob", List.of("alice")
            ))
            .agents(List.of(
                simpleSubAgent("alice", "Alice"),
                simpleSubAgent("bob", "Bob")
            ))
            .build();

        WorkflowDef wf = compiler.compile(config);

        // Init should set last_agent
        WorkflowTask init = wf.getTasks().get(0);
        assertThat(init.getInputParameters()).containsKey("last_agent");

        // Select script should reference allowed transitions
        WorkflowTask loop = wf.getTasks().get(1);
        WorkflowTask select = loop.getLoopOver().get(0);
        String script = (String) select.getInputParameters().get("expression");
        assertThat(script).contains("allowed");
    }

    @Test
    void testDuplicateAgentNames() {
        AgentConfig config = AgentConfig.builder()
            .name("dupes")
            .model("openai/gpt-4o")
            .strategy("handoff")
            .agents(List.of(
                simpleSubAgent("same_name", "A"),
                simpleSubAgent("same_name", "B")
            ))
            .build();

        assertThatThrownBy(() -> compiler.compile(config))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("Duplicate agent names");
    }

    @Test
    void testHandoffWithAllowedTransitions() {
        AgentConfig config = AgentConfig.builder()
            .name("team")
            .model("openai/gpt-4o")
            .instructions("Route to the best agent.")
            .strategy("handoff")
            .allowedTransitions(Map.of(
                "specialist_a", List.of("specialist_b"),
                "specialist_b", List.of("specialist_a", "team"),
                "specialist_c", List.of("team")
            ))
            .agents(List.of(
                simpleSubAgent("specialist_a", "Handle A tasks"),
                simpleSubAgent("specialist_b", "Handle B tasks"),
                simpleSubAgent("specialist_c", "Summarize")
            ))
            .build();

        WorkflowDef wf = compiler.compile(config);
        assertThat(wf.getName()).isEqualTo("team");

        // With allowedTransitions, handoff compiles as init + loop + final
        assertThat(wf.getTasks()).hasSize(3);
        assertThat(wf.getTasks().get(0).getType()).isEqualTo("SET_VARIABLE");
        assertThat(wf.getTasks().get(1).getType()).isEqualTo("DO_WHILE");

        // Loop should contain sub-agent routing logic
        WorkflowTask loop = wf.getTasks().get(1);
        assertThat(loop.getLoopOver()).isNotEmpty();
    }

    @Test
    void testRoundRobinWithTransferControlConstraints() {
        // Simulates ADK's disallow_transfer_to_parent/peers mapped to allowedTransitions
        AgentConfig config = AgentConfig.builder()
            .name("coordinator")
            .model("openai/gpt-4o")
            .strategy("round_robin")
            .allowedTransitions(Map.of(
                "data_collector", List.of("analyst"),
                "analyst", List.of("coordinator", "data_collector", "summarizer"),
                "summarizer", List.of("coordinator")
            ))
            .agents(List.of(
                simpleSubAgent("data_collector", "Gather data"),
                simpleSubAgent("analyst", "Analyze data"),
                simpleSubAgent("summarizer", "Summarize")
            ))
            .build();

        WorkflowDef wf = compiler.compile(config);

        // Init + DoWhile
        assertThat(wf.getTasks()).hasSize(2);
        assertThat(wf.getTasks().get(0).getType()).isEqualTo("SET_VARIABLE");
        assertThat(wf.getTasks().get(1).getType()).isEqualTo("DO_WHILE");

        // Select script should contain allowed transitions mapping
        WorkflowTask loop = wf.getTasks().get(1);
        WorkflowTask selectTask = loop.getLoopOver().get(0);
        String script = (String) selectTask.getInputParameters().get("expression");
        assertThat(script).contains("allowed");
    }

    @SuppressWarnings("unchecked")
    @Test
    void testCapabilitiesMetadata() {
        // Simple agent → ["simple"]
        AgentConfig simple = AgentConfig.builder()
            .name("basic")
            .model("openai/gpt-4o")
            .instructions("Hello")
            .build();
        WorkflowDef simpleWf = compiler.compile(simple);
        List<String> simpleCaps = (List<String>) simpleWf.getMetadata().get("agent_capabilities");
        assertThat(simpleCaps).containsExactly("simple");

        // Agent with tools → ["tool-calling"]
        ToolConfig tool = ToolConfig.builder()
            .name("search")
            .description("Search")
            .inputSchema(Map.of("type", "object"))
            .toolType("worker")
            .build();
        AgentConfig withTools = AgentConfig.builder()
            .name("tooler")
            .model("openai/gpt-4o")
            .instructions("Use tools")
            .tools(List.of(tool))
            .build();
        WorkflowDef toolWf = compiler.compile(withTools);
        List<String> toolCaps = (List<String>) toolWf.getMetadata().get("agent_capabilities");
        assertThat(toolCaps).containsExactly("tool-calling");

        // Swarm with tool-using sub-agent → includes both "multi-agent-swarm" and "tool-calling"
        AgentConfig swarmConfig = AgentConfig.builder()
            .name("swarm_team")
            .model("openai/gpt-4o")
            .instructions("Triage")
            .strategy("swarm")
            .agents(List.of(
                AgentConfig.builder()
                    .name("tool_agent")
                    .model("openai/gpt-4o")
                    .instructions("Use tools")
                    .tools(List.of(tool))
                    .build(),
                simpleSubAgent("helper", "Help")
            ))
            .build();
        WorkflowDef swarmWf = compiler.compile(swarmConfig);
        List<String> swarmCaps = (List<String>) swarmWf.getMetadata().get("agent_capabilities");
        assertThat(swarmCaps).contains("multi-agent-swarm", "tool-calling");

        // Handoff with simple sub-agents → ["multi-agent-handoff", "simple"]
        AgentConfig handoffConfig = AgentConfig.builder()
            .name("team")
            .model("openai/gpt-4o")
            .instructions("Route")
            .strategy("handoff")
            .agents(List.of(
                simpleSubAgent("a", "A"),
                simpleSubAgent("b", "B")
            ))
            .build();
        WorkflowDef handoffWf = compiler.compile(handoffConfig);
        List<String> handoffCaps = (List<String>) handoffWf.getMetadata().get("agent_capabilities");
        assertThat(handoffCaps).contains("multi-agent-handoff", "simple");
    }

    @Test
    void testCollectCapabilities() {
        // Direct unit test of the static helper
        AgentConfig simple = AgentConfig.builder()
            .name("s")
            .model("openai/gpt-4o")
            .build();
        assertThat(AgentCompiler.collectCapabilities(simple)).containsExactly("simple");

        ToolConfig tool = ToolConfig.builder()
            .name("t")
            .description("T")
            .inputSchema(Map.of("type", "object"))
            .toolType("worker")
            .build();

        // Hybrid: tools + agents
        AgentConfig hybrid = AgentConfig.builder()
            .name("h")
            .model("openai/gpt-4o")
            .tools(List.of(tool))
            .agents(List.of(simple))
            .build();
        Set<String> hybridCaps = AgentCompiler.collectCapabilities(hybrid);
        assertThat(hybridCaps).contains("tool-calling", "multi-agent-hybrid", "simple");

        // round_robin strategy
        AgentConfig rr = AgentConfig.builder()
            .name("rr")
            .model("openai/gpt-4o")
            .strategy("round_robin")
            .agents(List.of(simple))
            .build();
        assertThat(AgentCompiler.collectCapabilities(rr)).contains("multi-agent-round-robin");
    }

    @Test
    void testSequentialWithToolsHasCoercion() {
        // Sub-agents with tools produce SUB_WORKFLOW tasks whose output.result
        // may be null. A coercion INLINE task must be inserted between stages
        // to convert null → empty string before the next stage's message.
        ToolConfig tool = ToolConfig.builder()
            .name("search")
            .description("Search")
            .inputSchema(Map.of("type", "object"))
            .toolType("worker")
            .build();

        AgentConfig config = AgentConfig.builder()
            .name("pipeline")
            .model("openai/gpt-4o")
            .strategy("sequential")
            .agents(List.of(
                // Agent with tools → SUB_WORKFLOW → needs coercion
                AgentConfig.builder()
                    .name("researcher")
                    .model("openai/gpt-4o")
                    .instructions("Research")
                    .tools(List.of(tool))
                    .build(),
                // Simple agent → inline LLM → receives coerced ref
                simpleSubAgent("writer", "Write content")
            ))
            .build();

        WorkflowDef wf = compiler.compile(config);

        // Should have: SUB_WORKFLOW(researcher) + INLINE(coerce) + SUB_WORKFLOW(writer)
        assertThat(wf.getTasks()).hasSize(3);
        assertThat(wf.getTasks().get(0).getType()).isEqualTo("SUB_WORKFLOW");
        assertThat(wf.getTasks().get(1).getType()).isEqualTo("INLINE");
        assertThat(wf.getTasks().get(1).getTaskReferenceName()).contains("coerce");
        assertThat(wf.getTasks().get(2).getType()).isEqualTo("SUB_WORKFLOW");

        // The sub-workflow's prompt input should reference the coerced output
        String promptInput = (String) wf.getTasks().get(2).getInputParameters().get("prompt");
        assertThat(promptInput).contains("coerce");
        assertThat(promptInput).contains(".output.result");
    }

    @Test
    void testSwarmWithHierarchicalSubAgent() {
        // Swarm with a handoff sub-agent — the handoff structure should be preserved
        AgentConfig config = AgentConfig.builder()
            .name("ceo")
            .model("openai/gpt-4o")
            .instructions("Delegate to the right team lead")
            .strategy("swarm")
            .agents(List.of(
                // engineering_lead has its own sub-agents (handoff strategy)
                AgentConfig.builder()
                    .name("engineering_lead")
                    .model("openai/gpt-4o")
                    .instructions("Route to backend or frontend dev")
                    .strategy("handoff")
                    .agents(List.of(
                        simpleSubAgent("backend_dev", "Handle backend tasks"),
                        simpleSubAgent("frontend_dev", "Handle frontend tasks")
                    ))
                    .build(),
                simpleSubAgent("marketing_lead", "Handle marketing tasks")
            ))
            .build();

        WorkflowDef wf = compiler.compile(config);

        // Init + DoWhile + Final LLM
        assertThat(wf.getTasks()).hasSize(3);

        WorkflowTask loop = wf.getTasks().get(1);
        WorkflowTask switchTask = loop.getLoopOver().stream()
            .filter(t -> "SWITCH".equals(t.getType())).findFirst().orElseThrow();

        // Case "1" is engineering_lead (hierarchical)
        List<WorkflowTask> engCase = switchTask.getDecisionCases().get("1");
        assertThat(engCase).isNotEmpty();
        WorkflowTask engSubWf = engCase.get(0);
        assertThat(engSubWf.getType()).isEqualTo("SUB_WORKFLOW");

        // The inline workflow should use the hierarchical path:
        // inner SUB_WORKFLOW (handoff strategy) + transfer LLM + check_transfer
        WorkflowDef engInlineWf = engSubWf.getSubWorkflowParam().getWorkflowDef();
        assertThat(engInlineWf.getTasks()).hasSize(3);
        assertThat(engInlineWf.getTasks().get(0).getType()).isEqualTo("SUB_WORKFLOW"); // inner handoff
        assertThat(engInlineWf.getTasks().get(1).getType()).isEqualTo("LLM_CHAT_COMPLETE"); // transfer decision
        assertThat(engInlineWf.getTasks().get(2).getType()).isEqualTo("SIMPLE"); // check_transfer

        // The inner SUB_WORKFLOW should contain the handoff strategy (init + loop + final)
        WorkflowDef innerHandoff = engInlineWf.getTasks().get(0).getSubWorkflowParam().getWorkflowDef();
        assertThat(innerHandoff.getTasks()).hasSize(3);
        assertThat(innerHandoff.getTasks().get(0).getType()).isEqualTo("SET_VARIABLE"); // init
        assertThat(innerHandoff.getTasks().get(1).getType()).isEqualTo("DO_WHILE"); // handoff loop
        assertThat(innerHandoff.getTasks().get(2).getType()).isEqualTo("LLM_CHAT_COMPLETE"); // handoff final

        // Verify the handoff loop has the switch with backend_dev and frontend_dev
        WorkflowTask handoffLoop = innerHandoff.getTasks().get(1);
        WorkflowTask handoffSwitch = handoffLoop.getLoopOver().stream()
            .filter(t -> "SWITCH".equals(t.getType())).findFirst().orElseThrow();
        assertThat(handoffSwitch.getDecisionCases()).containsKeys("backend_dev", "frontend_dev");

        // Case "2" is marketing_lead (flat) — should use the original flat path
        List<WorkflowTask> mktCase = switchTask.getDecisionCases().get("2");
        assertThat(mktCase).isNotEmpty();
        WorkflowTask mktSubWf = mktCase.get(0);
        WorkflowDef mktInlineWf = mktSubWf.getSubWorkflowParam().getWorkflowDef();
        // Flat path: init_state + DO_WHILE(llm, tool_router, check_transfer)
        assertThat(mktInlineWf.getTasks()).hasSize(2);
        assertThat(mktInlineWf.getTasks().get(0).getType()).isEqualTo("SET_VARIABLE");
        assertThat(mktInlineWf.getTasks().get(1).getType()).isEqualTo("DO_WHILE");
    }

    @Test
    void testHandoffRouterPromptCoversAllParts() {
        AgentConfig config = AgentConfig.builder()
            .name("team")
            .model("openai/gpt-4o")
            .instructions("Route to the best agent.")
            .strategy("handoff")
            .agents(List.of(
                simpleSubAgent("agent_a", "Handle A tasks"),
                simpleSubAgent("agent_b", "Handle B tasks")
            ))
            .build();

        WorkflowDef wf = compiler.compile(config);

        // Extract the router LLM system prompt from the loop
        // The router is a SUB_WORKFLOW wrapping an inner LLM task
        WorkflowTask loop = wf.getTasks().get(1);
        WorkflowTask routerSubWf = loop.getLoopOver().get(0);
        WorkflowTask innerLlm = routerSubWf.getSubWorkflowParam().getWorkflowDef().getTasks().get(0);
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> messages = (List<Map<String, Object>>) innerLlm.getInputParameters().get("messages");
        String systemMsg = (String) messages.get(0).get("message");

        // Should contain multi-part awareness language
        assertThat(systemMsg).contains("ALL parts");
        assertThat(systemMsg).contains("MULTIPLE parts");
        assertThat(systemMsg).contains("COMPLETE request");
        // Should NOT contain the old early-termination language
        assertThat(systemMsg).doesNotContain("Once an agent has responded, you should typically respond DONE");
    }

    // ── Timeout tests ──────────────────────────────────────────────────

    @Test
    void testHandoffAppliesTimeout() {
        AgentConfig config = AgentConfig.builder()
            .name("team")
            .model("openai/gpt-4o")
            .instructions("Route tasks.")
            .strategy("handoff")
            .timeoutSeconds(120)
            .agents(List.of(
                simpleSubAgent("a", "A"),
                simpleSubAgent("b", "B")
            ))
            .build();

        WorkflowDef wf = compiler.compile(config);
        assertThat(wf.getTimeoutSeconds()).isEqualTo(120L);
        assertThat(wf.getTimeoutPolicy()).isEqualTo(WorkflowDef.TimeoutPolicy.TIME_OUT_WF);
    }

    @Test
    void testSequentialAppliesTimeout() {
        AgentConfig config = AgentConfig.builder()
            .name("pipeline")
            .model("openai/gpt-4o")
            .instructions("Run steps.")
            .strategy("sequential")
            .timeoutSeconds(60)
            .agents(List.of(
                simpleSubAgent("step1", "First"),
                simpleSubAgent("step2", "Second")
            ))
            .build();

        WorkflowDef wf = compiler.compile(config);
        assertThat(wf.getTimeoutSeconds()).isEqualTo(60L);
        assertThat(wf.getTimeoutPolicy()).isEqualTo(WorkflowDef.TimeoutPolicy.TIME_OUT_WF);
    }

    @Test
    void testParallelAppliesTimeout() {
        AgentConfig config = AgentConfig.builder()
            .name("parallel_team")
            .model("openai/gpt-4o")
            .instructions("Run in parallel.")
            .strategy("parallel")
            .timeoutSeconds(90)
            .agents(List.of(
                simpleSubAgent("p1", "Agent 1"),
                simpleSubAgent("p2", "Agent 2")
            ))
            .build();

        WorkflowDef wf = compiler.compile(config);
        assertThat(wf.getTimeoutSeconds()).isEqualTo(90L);
    }

    @Test
    void testRouterAppliesTimeout() {
        AgentConfig config = AgentConfig.builder()
            .name("router_team")
            .model("openai/gpt-4o")
            .instructions("Route intelligently.")
            .strategy("router")
            .timeoutSeconds(45)
            .agents(List.of(
                simpleSubAgent("r1", "Agent 1"),
                simpleSubAgent("r2", "Agent 2")
            ))
            .build();

        WorkflowDef wf = compiler.compile(config);
        assertThat(wf.getTimeoutSeconds()).isEqualTo(45L);
    }

    @Test
    void testSwarmAppliesTimeout() {
        AgentConfig config = AgentConfig.builder()
            .name("swarm_team")
            .model("openai/gpt-4o")
            .instructions("Swarm orchestration.")
            .strategy("swarm")
            .timeoutSeconds(200)
            .agents(List.of(
                simpleSubAgent("s1", "Agent 1"),
                simpleSubAgent("s2", "Agent 2")
            ))
            .build();

        WorkflowDef wf = compiler.compile(config);
        assertThat(wf.getTimeoutSeconds()).isEqualTo(200L);
    }

    @Test
    void testRoundRobinAppliesTimeout() {
        AgentConfig config = AgentConfig.builder()
            .name("rr_team")
            .model("openai/gpt-4o")
            .instructions("Take turns.")
            .strategy("round_robin")
            .timeoutSeconds(30)
            .agents(List.of(
                simpleSubAgent("rr1", "Agent 1"),
                simpleSubAgent("rr2", "Agent 2")
            ))
            .build();

        WorkflowDef wf = compiler.compile(config);
        assertThat(wf.getTimeoutSeconds()).isEqualTo(30L);
    }

    @Test
    void testMultiAgentNoTimeoutSetsNoPolicy() {
        AgentConfig config = AgentConfig.builder()
            .name("no_timeout_team")
            .model("openai/gpt-4o")
            .instructions("No timeout set.")
            .strategy("handoff")
            .agents(List.of(
                simpleSubAgent("a", "A"),
                simpleSubAgent("b", "B")
            ))
            .build();

        WorkflowDef wf = compiler.compile(config);
        // Default AgentCompiler timeoutSeconds is 0, so no timeout should be set
        assertThat(wf.getTimeoutPolicy()).isNull();
    }

    // ── Gate tests ──────────────────────────────────────────────────

    @Test
    void testSequentialWithTextGate() {
        AgentConfig config = AgentConfig.builder()
            .name("pipeline")
            .model("openai/gpt-4o")
            .strategy("sequential")
            .agents(List.of(
                AgentConfig.builder()
                    .name("fetcher")
                    .model("openai/gpt-4o")
                    .instructions("Fetch issues")
                    .gate(Map.of("type", "text_contains", "text", "NO_OPEN_ISSUES", "caseSensitive", true))
                    .build(),
                simpleSubAgent("coder", "Write code"),
                simpleSubAgent("pusher", "Push PR")
            ))
            .build();

        WorkflowDef wf = compiler.compile(config);

        // SUB_WORKFLOW(fetcher) + coerce + INLINE(gate) + SWITCH(gate_switch) + output_selector
        assertThat(wf.getTasks()).hasSize(5);
        assertThat(wf.getTasks().get(0).getType()).isEqualTo("SUB_WORKFLOW");
        assertThat(wf.getTasks().get(0).getTaskReferenceName()).contains("fetcher");
        assertThat(wf.getTasks().get(1).getType()).isEqualTo("INLINE"); // coerce
        assertThat(wf.getTasks().get(2).getType()).isEqualTo("INLINE"); // gate
        assertThat(wf.getTasks().get(2).getTaskReferenceName()).isEqualTo("pipeline_gate_0");
        assertThat(wf.getTasks().get(3).getType()).isEqualTo("SWITCH");
        assertThat(wf.getTasks().get(3).getTaskReferenceName()).isEqualTo("pipeline_gate_switch_0");
        assertThat(wf.getTasks().get(4).getType()).isEqualTo("INLINE"); // output_selector
        assertThat(wf.getTasks().get(4).getTaskReferenceName()).isEqualTo("pipeline_output_selector");

        // SWITCH should have "continue" case with remaining stages
        WorkflowTask switchTask = wf.getTasks().get(3);
        assertThat(switchTask.getDecisionCases()).containsKey("continue");
        List<WorkflowTask> continueTasks = switchTask.getDecisionCases().get("continue");
        // coder SUB_WORKFLOW + coerce + pusher SUB_WORKFLOW
        assertThat(continueTasks).hasSize(3);
        assertThat(continueTasks.get(0).getType()).isEqualTo("SUB_WORKFLOW");
        assertThat(continueTasks.get(0).getTaskReferenceName()).contains("coder");
        assertThat(continueTasks.get(2).getType()).isEqualTo("SUB_WORKFLOW");
        assertThat(continueTasks.get(2).getTaskReferenceName()).contains("pusher");

        // Default case (stop) should be empty
        assertThat(switchTask.getDefaultCase()).isEmpty();
    }

    @Test
    void testSequentialWithoutGate() {
        // Ensure no gate = no SWITCH task
        AgentConfig config = AgentConfig.builder()
            .name("pipeline")
            .model("openai/gpt-4o")
            .strategy("sequential")
            .agents(List.of(
                simpleSubAgent("a", "Step A"),
                simpleSubAgent("b", "Step B")
            ))
            .build();

        WorkflowDef wf = compiler.compile(config);

        // SUB_WORKFLOW(a) + coerce + SUB_WORKFLOW(b) — no SWITCH
        assertThat(wf.getTasks()).hasSize(3);
        boolean hasSwitch = wf.getTasks().stream()
            .anyMatch(t -> "SWITCH".equals(t.getType()));
        assertThat(hasSwitch).isFalse();
    }

    @Test
    void testSequentialWithWorkerGate() {
        AgentConfig config = AgentConfig.builder()
            .name("pipeline")
            .model("openai/gpt-4o")
            .strategy("sequential")
            .agents(List.of(
                AgentConfig.builder()
                    .name("fetcher")
                    .model("openai/gpt-4o")
                    .instructions("Fetch")
                    .gate(Map.of("taskName", "fetcher_gate"))
                    .build(),
                simpleSubAgent("coder", "Code")
            ))
            .build();

        WorkflowDef wf = compiler.compile(config);

        // SUB_WORKFLOW + coerce + SIMPLE(gate) + SWITCH + output_selector
        assertThat(wf.getTasks()).hasSize(5);
        assertThat(wf.getTasks().get(2).getType()).isEqualTo("SIMPLE");
        assertThat(wf.getTasks().get(2).getName()).isEqualTo("fetcher_gate");
        assertThat(wf.getTasks().get(3).getType()).isEqualTo("SWITCH");
        assertThat(wf.getTasks().get(4).getType()).isEqualTo("INLINE"); // output_selector
    }

    @Test
    void testSequentialWithMultipleGates() {
        // Two gates: stage 0 and stage 1 both have gates, stage 2 has none
        AgentConfig config = AgentConfig.builder()
            .name("pipeline")
            .model("openai/gpt-4o")
            .strategy("sequential")
            .agents(List.of(
                AgentConfig.builder()
                    .name("a")
                    .model("openai/gpt-4o")
                    .instructions("A")
                    .gate(Map.of("type", "text_contains", "text", "STOP_A", "caseSensitive", true))
                    .build(),
                AgentConfig.builder()
                    .name("b")
                    .model("openai/gpt-4o")
                    .instructions("B")
                    .gate(Map.of("type", "text_contains", "text", "STOP_B", "caseSensitive", true))
                    .build(),
                simpleSubAgent("c", "C")
            ))
            .build();

        WorkflowDef wf = compiler.compile(config);

        // Top level: SUB_WORKFLOW(a) + coerce + gate_0 + SWITCH_0 + output_selector
        assertThat(wf.getTasks()).hasSize(5);
        assertThat(wf.getTasks().get(3).getType()).isEqualTo("SWITCH");
        assertThat(wf.getTasks().get(4).getType()).isEqualTo("INLINE"); // output_selector

        // Inside SWITCH_0's "continue" case: SUB_WORKFLOW(b) + coerce + gate_1 + SWITCH_1
        List<WorkflowTask> continueCase0 = wf.getTasks().get(3).getDecisionCases().get("continue");
        assertThat(continueCase0).hasSize(4);
        assertThat(continueCase0.get(2).getTaskReferenceName()).isEqualTo("pipeline_gate_1");
        assertThat(continueCase0.get(3).getType()).isEqualTo("SWITCH");

        // Inside SWITCH_1's "continue" case: SUB_WORKFLOW(c)
        List<WorkflowTask> continueCase1 = continueCase0.get(3).getDecisionCases().get("continue");
        assertThat(continueCase1).hasSize(1);
        assertThat(continueCase1.get(0).getTaskReferenceName()).contains("c");
    }
}
