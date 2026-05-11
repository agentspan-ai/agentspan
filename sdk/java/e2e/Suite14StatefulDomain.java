// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.


import ai.agentspan.Agent;
import ai.agentspan.AgentRuntime;
import ai.agentspan.enums.Strategy;
import ai.agentspan.model.ToolDef;
import org.junit.jupiter.api.*;

import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Suite 12: Stateful domain propagation — structural plan() assertions.
 *
 * <p>Tests that {@code Agent.stateful(true/false)} propagates correctly through
 * the plan:
 * <ol>
 *   <li>stateful=true propagates to agentDef (plan-level, no LLM)</li>
 *   <li>stateful=false (default) does NOT set stateful in agentDef tools</li>
 *   <li>stateful=true agent with tool — tool inherits stateful domain</li>
 *   <li>stateful swarm — all sub-agents inherit stateful flag</li>
 * </ol>
 *
 * <p>All tests use plan() — no LLM calls.
 * COUNTERFACTUAL: each test is designed to fail if the corresponding
 * stateful flag serializes incorrectly or is silently dropped.
 */
@Tag("e2e")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
@Timeout(value = 300, unit = TimeUnit.SECONDS)
class Suite14StatefulDomain extends BaseTest {

    private static AgentRuntime runtime;

    @BeforeAll
    static void setup() {
        runtime = new AgentRuntime(new ai.agentspan.AgentConfig(BASE_URL, null, null, 100, 1));
    }

    @AfterAll
    static void teardown() {
        if (runtime != null) runtime.close();
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    /** Build a minimal worker ToolDef with the given name. */
    private static ToolDef workerTool(String name) {
        return ToolDef.builder()
            .name(name)
            .description("A test worker tool.")
            .inputSchema(Map.of("type", "object", "properties", Map.of()))
            .toolType("worker")
            .func(input -> input)
            .build();
    }

    // ── Tests ─────────────────────────────────────────────────────────────────

    /**
     * stateful=true propagates to agentDef at the plan level.
     *
     * COUNTERFACTUAL: if the stateful flag is not serialized at all, the plan
     * won't carry it and worker domain isolation won't be configured.
     */
    @Test
    @Order(1)
    @SuppressWarnings("unchecked")
    void test_stateful_true_propagates_to_agentDef() {
        Agent agent = Agent.builder()
            .name("e2e_s12_stateful_true")
            .model(MODEL)
            .instructions("A stateful agent.")
            .stateful(true)
            .tools(List.of(workerTool("e2e_s12_stateful_true_tool")))
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        List<Map<String, Object>> tools = (List<Map<String, Object>>) agentDef.get("tools");
        assertNotNull(tools, "agentDef.tools is null. COUNTERFACTUAL: agent has a tool so tools must not be null.");

        Map<String, Object> tool = tools.stream()
            .filter(t -> "e2e_s12_stateful_true_tool".equals(t.get("name")))
            .findFirst()
            .orElseGet(() -> {
                fail("Tool 'e2e_s12_stateful_true_tool' not found in agentDef.tools: "
                    + tools.stream().map(t -> (String) t.get("name")).collect(Collectors.toList()));
                return null;
            });

        assertEquals(Boolean.TRUE, tool.get("stateful"),
            "tool.stateful should be true when agent is stateful(true) but got: " + tool.get("stateful")
            + ". COUNTERFACTUAL: Agent.stateful(true) must propagate stateful=true to each tool in the plan.");
    }

    /**
     * stateful=false (the default) does NOT set stateful=true on tools.
     *
     * COUNTERFACTUAL: if stateful defaults to true or is always serialized as true,
     * every agent would get domain isolation even when not requested, wasting resources.
     */
    @Test
    @Order(2)
    @SuppressWarnings("unchecked")
    void test_stateful_false_default_does_not_propagate() {
        Agent agent = Agent.builder()
            .name("e2e_s12_stateful_false")
            .model(MODEL)
            .instructions("A non-stateful agent (default).")
            // stateful not set — defaults to false
            .tools(List.of(workerTool("e2e_s12_stateful_false_tool")))
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        List<Map<String, Object>> tools = (List<Map<String, Object>>) agentDef.get("tools");
        assertNotNull(tools, "agentDef.tools is null.");

        Map<String, Object> tool = tools.stream()
            .filter(t -> "e2e_s12_stateful_false_tool".equals(t.get("name")))
            .findFirst()
            .orElseGet(() -> {
                fail("Tool 'e2e_s12_stateful_false_tool' not found.");
                return null;
            });

        // stateful should be absent or false — not true
        Object statefulValue = tool.get("stateful");
        assertNotEquals(Boolean.TRUE, statefulValue,
            "tool.stateful should NOT be true for a non-stateful agent (default) but got: " + statefulValue
            + ". COUNTERFACTUAL: if stateful defaults to true, domain isolation is always on, which is wrong.");
    }

    /**
     * stateful=true agent with a single tool — the tool carries stateful=true in the plan.
     *
     * Adds more coverage on top of Suite 11 test_stateful_field_serialized by using a
     * different tool name and confirming the tool type is still 'worker'.
     *
     * COUNTERFACTUAL: if stateful propagation logic only fires for certain tool names or
     * types, this test would catch it.
     */
    @Test
    @Order(3)
    @SuppressWarnings("unchecked")
    void test_stateful_true_agent_with_tool_inherits_domain() {
        ToolDef tool = workerTool("e2e_s12_domain_inherit_tool");

        Agent agent = Agent.builder()
            .name("e2e_s12_domain_inherit")
            .model(MODEL)
            .instructions("Stateful agent with a tool that must inherit the domain.")
            .stateful(true)
            .tools(List.of(tool))
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        List<Map<String, Object>> planTools = (List<Map<String, Object>>) agentDef.get("tools");
        assertNotNull(planTools, "agentDef.tools is null.");
        assertEquals(1, planTools.size(),
            "Expected 1 tool in plan but got " + planTools.size());

        Map<String, Object> planTool = planTools.get(0);

        assertEquals("e2e_s12_domain_inherit_tool", planTool.get("name"),
            "Tool name mismatch. Got: " + planTool.get("name"));
        assertEquals("worker", planTool.get("toolType"),
            "toolType should remain 'worker' even with stateful=true. Got: " + planTool.get("toolType")
            + ". COUNTERFACTUAL: stateful propagation must not alter toolType.");
        assertEquals(Boolean.TRUE, planTool.get("stateful"),
            "tool.stateful should be true. Got: " + planTool.get("stateful")
            + ". COUNTERFACTUAL: stateful flag must propagate to the tool so the worker domain is isolated.");
    }

    /**
     * stateful swarm — all sub-agents in a SWARM inherit the stateful flag.
     *
     * COUNTERFACTUAL: if stateful propagation only works for single agents and not
     * for sub-agents in a multi-agent orchestration, the swarm workers won't be
     * domain-isolated.
     */
    @Test
    @Order(4)
    @SuppressWarnings("unchecked")
    void test_stateful_swarm_all_subagents_inherit_flag() {
        Agent subAgent1 = Agent.builder()
            .name("e2e_s12_swarm_sub1")
            .model(MODEL)
            .instructions("Swarm sub-agent 1.")
            .stateful(true)
            .tools(List.of(workerTool("e2e_s12_swarm_sub1_tool")))
            .build();

        Agent subAgent2 = Agent.builder()
            .name("e2e_s12_swarm_sub2")
            .model(MODEL)
            .instructions("Swarm sub-agent 2.")
            .stateful(true)
            .tools(List.of(workerTool("e2e_s12_swarm_sub2_tool")))
            .build();

        Agent swarm = Agent.builder()
            .name("e2e_s12_stateful_swarm")
            .model(MODEL)
            .instructions("Stateful swarm coordinator.")
            .agents(subAgent1, subAgent2)
            .strategy(Strategy.SWARM)
            .stateful(true)
            .build();

        Map<String, Object> plan = runtime.plan(swarm);
        Map<String, Object> agentDef = getAgentDef(plan);

        List<Map<String, Object>> subAgents = (List<Map<String, Object>>) agentDef.get("agents");
        assertNotNull(subAgents,
            "agentDef.agents is null. COUNTERFACTUAL: swarm plan must include sub-agents.");
        assertEquals(2, subAgents.size(),
            "Expected 2 sub-agents in swarm plan but got " + subAgents.size());

        // Verify each sub-agent's tool carries stateful=true
        for (Map<String, Object> sub : subAgents) {
            String subName = (String) sub.get("name");
            List<Map<String, Object>> subTools = (List<Map<String, Object>>) sub.get("tools");

            assertNotNull(subTools,
                "Sub-agent '" + subName + "' has no 'tools' in plan. "
                + "COUNTERFACTUAL: stateful sub-agent tools must appear in plan.");
            assertFalse(subTools.isEmpty(),
                "Sub-agent '" + subName + "' has empty tools list.");

            for (Map<String, Object> subTool : subTools) {
                assertEquals(Boolean.TRUE, subTool.get("stateful"),
                    "Sub-agent '" + subName + "' tool '" + subTool.get("name")
                    + "' stateful should be true but got: " + subTool.get("stateful")
                    + ". COUNTERFACTUAL: stateful=true on a swarm sub-agent must propagate to "
                    + "its tools so worker domain isolation works in the swarm.");
            }
        }
    }
}
