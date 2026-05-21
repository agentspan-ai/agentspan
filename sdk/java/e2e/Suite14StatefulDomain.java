// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.


import ai.agentspan.Agent;
import ai.agentspan.AgentRuntime;
import ai.agentspan.enums.Strategy;
import ai.agentspan.model.AgentResult;
import ai.agentspan.model.ToolDef;
import ai.agentspan.AgentConfig;
import org.junit.jupiter.api.*;

import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
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

    /** Build a minimal worker ToolDef marked stateful=true. */
    private static ToolDef statefulWorkerTool(String name) {
        return ToolDef.builder()
            .name(name)
            .description("A stateful test worker tool.")
            .inputSchema(Map.of("type", "object", "properties", Map.of()))
            .toolType("worker")
            .func(input -> input)
            .stateful(true)
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

    /**
     * Runtime: two concurrent stateful executions must get DISJOINT domain UUIDs.
     *
     * Ports Python {@code test_concurrent_stateful_isolation} (suite14). Each
     * run uses its own {@link AgentRuntime}; the SDK generates a fresh
     * per-execution {@code runId} UUID, sends it on {@code /api/agent/start},
     * and the server uses it as {@code taskToDomain} for every worker task in
     * the run. Workers register under the same domain. Validates:
     *   - both runs COMPLETED
     *   - different workflow IDs
     *   - both have non-empty taskToDomain
     *   - the set of domain values in run 1 is disjoint from run 2
     *
     * COUNTERFACTUAL: if {@code runId} were not threaded through, both runs
     * would share the default queue and the assertion would fail. The SDK fix
     * that introduces this test also generates and forwards {@code runId} on
     * stateful start (see AgentRuntime.startAsync).
     */
    @Test
    @Order(5)
    @SuppressWarnings("unchecked")
    void test_concurrent_stateful_isolation() {
        Agent agent1 = Agent.builder()
            .name("e2e_s12_concurrent_a")
            .model(MODEL)
            .stateful(true)
            .maxTurns(3)
            .instructions("Call e2e_s12_concurrent_a_tool with input='concurrent_test'. "
                + "Respond with the tool result.")
            .tools(List.of(workerTool("e2e_s12_concurrent_a_tool")))
            .build();
        Agent agent2 = Agent.builder()
            .name("e2e_s12_concurrent_b")
            .model(MODEL)
            .stateful(true)
            .maxTurns(3)
            .instructions("Call e2e_s12_concurrent_b_tool with input='concurrent_test'. "
                + "Respond with the tool result.")
            .tools(List.of(workerTool("e2e_s12_concurrent_b_tool")))
            .build();

        AgentResult r1;
        AgentResult r2;
        try (AgentRuntime rt1 = new AgentRuntime(new AgentConfig(BASE_URL, null, null, 100, 1))) {
            r1 = rt1.run(agent1, "Run 1: call the tool");
        }
        try (AgentRuntime rt2 = new AgentRuntime(new AgentConfig(BASE_URL, null, null, 100, 1))) {
            r2 = rt2.run(agent2, "Run 2: call the tool");
        }

        assertTrue(r1.isSuccess(),
            "Run 1 must succeed; status=" + r1.getStatus() + " error=" + r1.getError());
        assertTrue(r2.isSuccess(),
            "Run 2 must succeed; status=" + r2.getStatus() + " error=" + r2.getError());
        assertNotEquals(r1.getExecutionId(), r2.getExecutionId(),
            "Concurrent runs must have distinct execution IDs.");

        Map<String, Object> ttd1 = (Map<String, Object>)
            getWorkflow(r1.getExecutionId()).getOrDefault("taskToDomain", Map.of());
        Map<String, Object> ttd2 = (Map<String, Object>)
            getWorkflow(r2.getExecutionId()).getOrDefault("taskToDomain", Map.of());

        assertFalse(ttd1.isEmpty(),
            "Run 1 taskToDomain is empty — stateful agent must have a domain "
            + "assignment. wfId=" + r1.getExecutionId()
            + ". COUNTERFACTUAL: missing runId on start would produce an empty map.");
        assertFalse(ttd2.isEmpty(),
            "Run 2 taskToDomain is empty — stateful agent must have a domain "
            + "assignment. wfId=" + r2.getExecutionId());

        Set<String> domains1 = new HashSet<>();
        for (Object v : ttd1.values()) if (v != null) domains1.add(v.toString());
        Set<String> domains2 = new HashSet<>();
        for (Object v : ttd2.values()) if (v != null) domains2.add(v.toString());

        Set<String> intersection = new HashSet<>(domains1);
        intersection.retainAll(domains2);
        assertTrue(intersection.isEmpty(),
            "Concurrent stateful runs must have DISJOINT domain UUIDs but overlap=" + intersection
            + ". Run 1=" + domains1 + ", Run 2=" + domains2
            + ". COUNTERFACTUAL: shared domains would cause cross-execution interference.");
    }

    /**
     * Per-tool stateful: Agent.stateful=false, but a ToolDef marked
     * stateful=true must still emit stateful=true in the plan's tool entry.
     *
     * Plan-level only (no LLM). Mirrors Python {@code @tool(stateful=True)}.
     *
     * COUNTERFACTUAL: a sibling non-stateful tool on the SAME agent must NOT
     * carry stateful=true — proves the flag isn't blanket-set.
     */
    @Test
    @Order(6)
    @SuppressWarnings("unchecked")
    void test_per_tool_stateful_propagates_in_plan() {
        ToolDef statefulTool = statefulWorkerTool("e2e_s12_per_tool_stateful");
        ToolDef plainTool = workerTool("e2e_s12_per_tool_plain");

        Agent agent = Agent.builder()
            .name("e2e_s12_per_tool_agent")
            .model(MODEL)
            // stateful NOT set on the agent — must default to false
            .tools(List.of(statefulTool, plainTool))
            .build();

        assertFalse(agent.isStateful(),
            "Agent.stateful must default to false for this test to be meaningful.");

        Map<String, Object> agentDef = getAgentDef(runtime.plan(agent));
        List<Map<String, Object>> tools = (List<Map<String, Object>>) agentDef.get("tools");
        assertNotNull(tools);

        Map<String, Object> statefulInPlan = tools.stream()
            .filter(t -> "e2e_s12_per_tool_stateful".equals(t.get("name")))
            .findFirst().orElseThrow();
        Map<String, Object> plainInPlan = tools.stream()
            .filter(t -> "e2e_s12_per_tool_plain".equals(t.get("name")))
            .findFirst().orElseThrow();

        assertEquals(Boolean.TRUE, statefulInPlan.get("stateful"),
            "Per-tool stateful=true MUST serialize as stateful=true even when the agent is non-stateful. "
            + "Got: " + statefulInPlan.get("stateful")
            + ". COUNTERFACTUAL: dropping per-tool stateful would force users to mark the whole agent stateful.");
        assertNotEquals(Boolean.TRUE, plainInPlan.get("stateful"),
            "Sibling non-stateful tool must NOT have stateful=true. Got: " + plainInPlan.get("stateful")
            + ". COUNTERFACTUAL: blanket-setting stateful on all tools would cause unnecessary domain routing.");
    }

    /**
     * Per-tool stateful: with Agent.stateful=false but a ToolDef marked
     * stateful=true, two concurrent runs must still get DISJOINT
     * taskToDomain UUIDs — proving the per-tool flag triggers the same
     * runId generation path as Agent.stateful=true.
     *
     * COUNTERFACTUAL: if the per-tool flag were ignored by hasStatefulTools,
     * no runId would be sent and taskToDomain would be empty (the test would
     * fail at the assertFalse(ttd.isEmpty()) check).
     */
    @Test
    @Order(7)
    @SuppressWarnings("unchecked")
    void test_per_tool_stateful_triggers_domain_isolation() {
        Agent agent1 = Agent.builder()
            .name("e2e_s12_per_tool_concurrent_a")
            .model(MODEL)
            .maxTurns(3)
            // agent NOT stateful — only the tool is
            .instructions("Call e2e_s12_per_tool_concurrent_a_tool with input='x'. "
                + "Respond with the tool result.")
            .tools(List.of(statefulWorkerTool("e2e_s12_per_tool_concurrent_a_tool")))
            .build();
        Agent agent2 = Agent.builder()
            .name("e2e_s12_per_tool_concurrent_b")
            .model(MODEL)
            .maxTurns(3)
            .instructions("Call e2e_s12_per_tool_concurrent_b_tool with input='x'. "
                + "Respond with the tool result.")
            .tools(List.of(statefulWorkerTool("e2e_s12_per_tool_concurrent_b_tool")))
            .build();

        assertFalse(agent1.isStateful(),
            "Pre-flight: agent1 must NOT be agent-level stateful, only the tool is.");
        assertFalse(agent2.isStateful(),
            "Pre-flight: agent2 must NOT be agent-level stateful, only the tool is.");

        AgentResult r1;
        AgentResult r2;
        try (AgentRuntime rt1 = new AgentRuntime(new AgentConfig(BASE_URL, null, null, 100, 1))) {
            r1 = rt1.run(agent1, "Run 1: call the tool");
        }
        try (AgentRuntime rt2 = new AgentRuntime(new AgentConfig(BASE_URL, null, null, 100, 1))) {
            r2 = rt2.run(agent2, "Run 2: call the tool");
        }

        assertTrue(r1.isSuccess(), "Run 1: " + r1.getStatus() + " " + r1.getError());
        assertTrue(r2.isSuccess(), "Run 2: " + r2.getStatus() + " " + r2.getError());
        assertNotEquals(r1.getExecutionId(), r2.getExecutionId());

        Map<String, Object> ttd1 = (Map<String, Object>)
            getWorkflow(r1.getExecutionId()).getOrDefault("taskToDomain", Map.of());
        Map<String, Object> ttd2 = (Map<String, Object>)
            getWorkflow(r2.getExecutionId()).getOrDefault("taskToDomain", Map.of());

        assertFalse(ttd1.isEmpty(),
            "Per-tool stateful MUST cause a non-empty taskToDomain even when "
            + "agent.stateful=false. Empty means the SDK ignored the per-tool flag.");
        assertFalse(ttd2.isEmpty(),
            "Per-tool stateful MUST cause a non-empty taskToDomain for run 2 as well.");

        Set<String> d1 = new HashSet<>();
        for (Object v : ttd1.values()) if (v != null) d1.add(v.toString());
        Set<String> d2 = new HashSet<>();
        for (Object v : ttd2.values()) if (v != null) d2.add(v.toString());
        Set<String> overlap = new HashSet<>(d1);
        overlap.retainAll(d2);
        assertTrue(overlap.isEmpty(),
            "Concurrent per-tool-stateful runs must have disjoint domains. Overlap=" + overlap);
    }
}
