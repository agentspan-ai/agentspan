// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.e2e;

import ai.agentspan.Agent;
import ai.agentspan.AgentRuntime;
import ai.agentspan.annotations.Tool;
import ai.agentspan.enums.Strategy;
import ai.agentspan.internal.ToolRegistry;
import org.junit.jupiter.api.*;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Suite 10: synthesize flag — structural plan() assertions.
 *
 * <p>All tests use plan() — no agent execution, no LLM calls.
 *
 * <p>COUNTERFACTUAL: each test must fail if the synthesize flag has no effect.
 */
@Tag("e2e")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class E2eSuite10Synthesize extends E2eBaseTest {

    private static AgentRuntime runtime;

    @BeforeAll
    static void setup() {
        runtime = new AgentRuntime(new ai.agentspan.AgentConfig(BASE_URL, null, null, 100, 1));
    }

    @AfterAll
    static void teardown() {
        if (runtime != null) runtime.close();
    }

    // ── Dummy sub-agents ──────────────────────────────────────────────────

    static class DummyTools {
        @Tool(name = "e2e_synth_tool", description = "Dummy tool for synthesize tests")
        public String run(String input) {
            return input;
        }
    }

    private static Agent makeSubAgent(String name) {
        return Agent.builder()
                .name(name)
                .model(MODEL)
                .instructions("You are " + name)
                .tools(ToolRegistry.fromInstance(new DummyTools()))
                .build();
    }

    // ── Helper: count _final tasks in flat task list ──────────────────────

    private long countFinalTasks(Map<String, Object> workflowDef, String agentName) {
        List<Map<String, Object>> tasks = allTasksFlat(workflowDef);
        String expectedRef = agentName.replace("-", "_") + "_final";
        return tasks.stream()
                .filter(t -> expectedRef.equals(t.get("taskReferenceName")))
                .count();
    }

    // ── Tests ─────────────────────────────────────────────────────────────

    /**
     * Default (synthesize not set) handoff agent: workflow MUST have a _final task.
     *
     * COUNTERFACTUAL: if the final synthesis task is removed, finalTaskCount == 0 → fails.
     */
    @Test
    @Order(1)
    void test_handoff_default_has_final_task() {
        Agent agent = Agent.builder()
                .name("e2e_synth_default_handoff")
                .model(MODEL)
                .strategy(Strategy.HANDOFF)
                .agents(List.of(makeSubAgent("e2e_sub_alpha"), makeSubAgent("e2e_sub_beta")))
                .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        // synthesize defaults to true — must NOT appear in serialized config (we only emit when false)
        assertFalse(agentDef.containsKey("synthesize"),
                "[default handoff] agentDef should NOT contain 'synthesize' when default. Got: " + agentDef.keySet());

        @SuppressWarnings("unchecked")
        Map<String, Object> wfDef = (Map<String, Object>) plan.get("workflowDef");
        long finalCount = countFinalTasks(wfDef, "e2e_synth_default_handoff");
        assertEquals(1, finalCount,
                "[default handoff] expected exactly 1 _final task, got " + finalCount);
    }

    /**
     * synthesize=false handoff: agentDef must contain synthesize=false,
     * and the workflow must NOT have a _final task.
     *
     * COUNTERFACTUAL: if synthesize flag is ignored, the _final task remains → finalCount > 0 → fails.
     */
    @Test
    @Order(2)
    void test_handoff_no_synthesize_omits_final_task() {
        Agent agent = Agent.builder()
                .name("e2e_synth_false_handoff")
                .model(MODEL)
                .strategy(Strategy.HANDOFF)
                .agents(List.of(makeSubAgent("e2e_sub_gamma"), makeSubAgent("e2e_sub_delta")))
                .synthesize(false)
                .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        assertEquals(Boolean.FALSE, agentDef.get("synthesize"),
                "[synthesize=false handoff] agentDef.synthesize must be false. Got: " + agentDef.get("synthesize"));

        @SuppressWarnings("unchecked")
        Map<String, Object> wfDef = (Map<String, Object>) plan.get("workflowDef");
        long finalCount = countFinalTasks(wfDef, "e2e_synth_false_handoff");
        assertEquals(0, finalCount,
                "[synthesize=false handoff] workflow must NOT have a _final task, got " + finalCount);
    }

    /**
     * synthesize=false router: agentDef must contain synthesize=false,
     * and the workflow must NOT have a _final task.
     *
     * COUNTERFACTUAL: if synthesize flag is ignored for router, the _final task remains → fails.
     */
    @Test
    @Order(3)
    void test_router_no_synthesize_omits_final_task() {
        Agent agent = Agent.builder()
                .name("e2e_synth_false_router")
                .model(MODEL)
                .strategy(Strategy.ROUTER)
                .agents(List.of(makeSubAgent("e2e_sub_epsilon"), makeSubAgent("e2e_sub_zeta")))
                .synthesize(false)
                .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        assertEquals(Boolean.FALSE, agentDef.get("synthesize"),
                "[synthesize=false router] agentDef.synthesize must be false. Got: " + agentDef.get("synthesize"));

        @SuppressWarnings("unchecked")
        Map<String, Object> wfDef = (Map<String, Object>) plan.get("workflowDef");
        long finalCount = countFinalTasks(wfDef, "e2e_synth_false_router");
        assertEquals(0, finalCount,
                "[synthesize=false router] workflow must NOT have a _final task, got " + finalCount);
    }

    /**
     * synthesize=false swarm: agentDef must contain synthesize=false,
     * and the workflow must NOT have a _final task.
     *
     * COUNTERFACTUAL: if synthesize flag is ignored for swarm, the _final task remains → fails.
     */
    @Test
    @Order(4)
    void test_swarm_no_synthesize_omits_final_task() {
        Agent agent = Agent.builder()
                .name("e2e_synth_false_swarm")
                .model(MODEL)
                .strategy(Strategy.SWARM)
                .agents(List.of(makeSubAgent("e2e_sub_eta"), makeSubAgent("e2e_sub_theta")))
                .synthesize(false)
                .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        assertEquals(Boolean.FALSE, agentDef.get("synthesize"),
                "[synthesize=false swarm] agentDef.synthesize must be false. Got: " + agentDef.get("synthesize"));

        @SuppressWarnings("unchecked")
        Map<String, Object> wfDef = (Map<String, Object>) plan.get("workflowDef");
        long finalCount = countFinalTasks(wfDef, "e2e_synth_false_swarm");
        assertEquals(0, finalCount,
                "[synthesize=false swarm] workflow must NOT have a _final task, got " + finalCount);
    }
}
