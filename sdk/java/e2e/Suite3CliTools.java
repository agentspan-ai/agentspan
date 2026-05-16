// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.


import ai.agentspan.Agent;
import ai.agentspan.AgentRuntime;
import ai.agentspan.execution.CliConfig;
import org.junit.jupiter.api.*;

import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Suite 13: CLI Tools — structural plan() assertions for {@link CliConfig}.
 *
 * <p>Mirrors Python {@code test_suite3_cli_tools.py}. When an agent is built with
 * {@link CliConfig}, the SDK serializes a {@code cliConfig} block on the agentDef
 * containing the allowed commands, timeout, allowShell and enabled flags. Server-side
 * the agent receives an auto-injected {@code run_command} tool (server contract — not
 * asserted client-side).
 *
 * <p>All tests use plan() — no LLM calls. Each assertion has a counterfactual:
 * either a contrast assertion in the same test, or a dedicated companion test that
 * builds an agent WITHOUT the feature and verifies the field is absent.
 */
@Tag("e2e")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
@Timeout(value = 300, unit = TimeUnit.SECONDS)
class Suite3CliTools extends BaseTest {

    private static AgentRuntime runtime;

    @BeforeAll
    static void setup() {
        runtime = new AgentRuntime(new ai.agentspan.AgentConfig(BASE_URL, null, null, 100, 1));
    }

    @AfterAll
    static void teardown() {
        if (runtime != null) runtime.close();
    }

    // ── Tests ─────────────────────────────────────────────────────────────────

    /**
     * Pure SDK property test: CliConfig.builder() captures fields verbatim.
     *
     * COUNTERFACTUAL: if any setter drops its value, the assertion for that field fails.
     * Two contrasting builds prove the test would fail if defaults were hard-coded.
     */
    @Test
    @Order(1)
    void test_cli_config_builder_properties() {
        CliConfig restrictive = CliConfig.builder()
            .allowedCommands(List.of("ls", "mktemp", "gh"))
            .timeout(45)
            .allowShell(false)
            .workingDir("/tmp")
            .build();

        assertTrue(restrictive.isEnabled(),
            "CliConfig.enabled defaults to true. COUNTERFACTUAL: if enabled flips, the CLI tool is silently off.");
        assertEquals(List.of("ls", "mktemp", "gh"), restrictive.getAllowedCommands(),
            "allowedCommands must round-trip. COUNTERFACTUAL: if the list is dropped, the whitelist is empty.");
        assertEquals(45, restrictive.getTimeout(),
            "timeout must round-trip. COUNTERFACTUAL: if dropped, default 30 returned.");
        assertFalse(restrictive.isAllowShell(),
            "allowShell=false must round-trip. COUNTERFACTUAL: if dropped, allowShell defaults to false anyway, so assert the contrast below.");
        assertEquals("/tmp", restrictive.getWorkingDir(),
            "workingDir must round-trip. COUNTERFACTUAL: if dropped, returned null.");

        // Counterfactual contrast — a permissive config differs on each property
        CliConfig permissive = CliConfig.builder()
            .allowedCommands(List.of("anything"))
            .timeout(120)
            .allowShell(true)
            .build();
        assertNotEquals(restrictive.getAllowedCommands(), permissive.getAllowedCommands(),
            "Two builders must produce distinct allowedCommands.");
        assertNotEquals(restrictive.getTimeout(), permissive.getTimeout(),
            "Two builders must produce distinct timeouts.");
        assertNotEquals(restrictive.isAllowShell(), permissive.isAllowShell(),
            "Two builders must produce distinct allowShell flags. COUNTERFACTUAL: if allowShell setter is no-op both would be false.");
    }

    /**
     * Plan compilation: an agent with cliConfig serializes a cliConfig block on agentDef
     * containing allowedCommands, timeout, enabled, allowShell.
     *
     * COUNTERFACTUAL: a sibling test below builds an agent WITHOUT cliConfig and
     * confirms the block is absent — if cliConfig were always emitted, both tests fail.
     */
    @Test
    @Order(2)
    @SuppressWarnings("unchecked")
    void test_cli_config_serializes_to_agentDef() {
        List<String> allowed = List.of("ls", "mktemp", "gh");
        Agent agent = Agent.builder()
            .name("e2e_s13_cli_serialized")
            .model(MODEL)
            .instructions("Run CLI commands.")
            .cliConfig(CliConfig.builder()
                .allowedCommands(allowed)
                .timeout(60)
                .allowShell(false)
                .build())
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        Map<String, Object> cliMap = (Map<String, Object>) agentDef.get("cliConfig");
        assertNotNull(cliMap,
            "agentDef.cliConfig is null. COUNTERFACTUAL: setting cliConfig on the Agent must serialize "
            + "to agentDef.cliConfig. agentDef keys: " + agentDef.keySet());

        assertEquals(Boolean.TRUE, cliMap.get("enabled"),
            "cliConfig.enabled should be true. Got: " + cliMap.get("enabled"));

        List<String> serializedCmds = (List<String>) cliMap.get("allowedCommands");
        assertNotNull(serializedCmds, "cliConfig.allowedCommands is null.");
        assertEquals(allowed.size(), serializedCmds.size(),
            "allowedCommands size mismatch. Expected " + allowed.size() + " but got " + serializedCmds.size());
        assertTrue(serializedCmds.containsAll(allowed),
            "allowedCommands must contain all of " + allowed + " but got " + serializedCmds
            + ". COUNTERFACTUAL: if a command is dropped, the whitelist diverges.");

        Object timeoutObj = cliMap.get("timeout");
        assertNotNull(timeoutObj, "cliConfig.timeout is null");
        assertEquals(60, ((Number) timeoutObj).intValue(),
            "cliConfig.timeout should be 60. Got: " + timeoutObj);

        assertEquals(Boolean.FALSE, cliMap.get("allowShell"),
            "cliConfig.allowShell should be false. Got: " + cliMap.get("allowShell"));
    }

    /**
     * Counterfactual: an agent without cliConfig has NO cliConfig block in its agentDef.
     *
     * Without this contrast test, the previous test could pass even if cliConfig were
     * ALWAYS emitted (e.g. as an empty map).
     */
    @Test
    @Order(3)
    void test_no_cli_config_means_no_block() {
        Agent agent = Agent.builder()
            .name("e2e_s13_no_cli")
            .model(MODEL)
            .instructions("No CLI here.")
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        assertFalse(agentDef.containsKey("cliConfig"),
            "agentDef.cliConfig should be ABSENT for an agent without cliConfig. Got: "
            + agentDef.get("cliConfig")
            + ". COUNTERFACTUAL: if cliConfig is always emitted, agents that didn't ask "
            + "for CLI would still get the run_command tool injected server-side.");
    }

    /**
     * allowShell=true round-trips through plan() with a distinct timeout.
     *
     * <p>Note: {@code workingDir} is intentionally not asserted on the plan output —
     * the server-side CliConfig DTO doesn't carry that field, so it doesn't survive
     * the roundtrip. The SDK-property assertion in
     * {@link #test_cli_config_builder_properties()} covers workingDir round-trip
     * in the CliConfig object.
     *
     * COUNTERFACTUAL: paired with the previous test that asserts allowShell=false
     * to prove the setter isn't a no-op.
     */
    @Test
    @Order(4)
    @SuppressWarnings("unchecked")
    void test_cli_allow_shell_true_round_trip() {
        Agent agent = Agent.builder()
            .name("e2e_s13_allow_shell")
            .model(MODEL)
            .instructions("Use shell features.")
            .cliConfig(CliConfig.builder()
                .allowedCommands(List.of("bash"))
                .allowShell(true)
                .timeout(15)
                .build())
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        Map<String, Object> cliMap = (Map<String, Object>) agentDef.get("cliConfig");
        assertNotNull(cliMap, "agentDef.cliConfig is null.");

        assertEquals(Boolean.TRUE, cliMap.get("allowShell"),
            "cliConfig.allowShell should be true. Got: " + cliMap.get("allowShell")
            + ". COUNTERFACTUAL: paired with the false-case in test_cli_config_serializes_to_agentDef.");
        Object timeoutObj = cliMap.get("timeout");
        assertEquals(15, ((Number) timeoutObj).intValue(),
            "cliConfig.timeout should be 15. Got: " + timeoutObj
            + ". COUNTERFACTUAL: different timeout from test_cli_config_serializes_to_agentDef so a stuck value would be caught.");
    }

    /**
     * Cross-agent isolation: two distinct cliConfigs produce distinct cliConfig blocks.
     *
     * COUNTERFACTUAL: if the serializer leaks state between agents, both plans would
     * have identical cliConfig blocks.
     */
    @Test
    @Order(5)
    @SuppressWarnings("unchecked")
    void test_two_agents_have_distinct_cli_configs() {
        Agent agentA = Agent.builder()
            .name("e2e_s13_agent_a")
            .model(MODEL)
            .instructions("A.")
            .cliConfig(CliConfig.builder()
                .allowedCommands(List.of("ls"))
                .timeout(10)
                .build())
            .build();
        Agent agentB = Agent.builder()
            .name("e2e_s13_agent_b")
            .model(MODEL)
            .instructions("B.")
            .cliConfig(CliConfig.builder()
                .allowedCommands(List.of("gh", "git"))
                .timeout(90)
                .build())
            .build();

        Map<String, Object> planA = runtime.plan(agentA);
        Map<String, Object> planB = runtime.plan(agentB);

        Map<String, Object> cliA = (Map<String, Object>) getAgentDef(planA).get("cliConfig");
        Map<String, Object> cliB = (Map<String, Object>) getAgentDef(planB).get("cliConfig");

        assertNotNull(cliA, "agentA cliConfig missing.");
        assertNotNull(cliB, "agentB cliConfig missing.");

        List<String> cmdsA = (List<String>) cliA.get("allowedCommands");
        List<String> cmdsB = (List<String>) cliB.get("allowedCommands");

        assertTrue(cmdsA.contains("ls") && !cmdsA.contains("gh"),
            "agentA should have 'ls' only. Got: " + cmdsA
            + ". COUNTERFACTUAL: if state leaks, agentA would also have 'gh' from agentB.");
        assertTrue(cmdsB.contains("gh") && !cmdsB.contains("ls"),
            "agentB should have 'gh' but not 'ls'. Got: " + cmdsB
            + ". COUNTERFACTUAL: if state leaks, agentB would have 'ls' from agentA.");

        int timeoutA = ((Number) cliA.get("timeout")).intValue();
        int timeoutB = ((Number) cliB.get("timeout")).intValue();
        assertNotEquals(timeoutA, timeoutB,
            "Timeouts must differ between agents (10 vs 90). Got: " + timeoutA + " vs " + timeoutB
            + ". COUNTERFACTUAL: if shared, the two agents collapse onto one config.");
    }

    /**
     * Plan-level validation that the CLI config does NOT leak into agentDef.tools as a
     * spurious user-supplied tool. The plan should still allow other user worker tools
     * to coexist.
     *
     * COUNTERFACTUAL: if cliConfig were misinterpreted as a worker tool definition, the
     * tools list would have an extra entry whose name comes from cliConfig.allowedCommands.
     */
    @Test
    @Order(6)
    @SuppressWarnings("unchecked")
    void test_cli_does_not_inject_user_tool() {
        Agent agent = Agent.builder()
            .name("e2e_s13_no_user_tool_injection")
            .model(MODEL)
            .instructions("Use CLI.")
            .cliConfig(CliConfig.builder()
                .allowedCommands(List.of("ls", "mktemp"))
                .build())
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        List<Map<String, Object>> tools = (List<Map<String, Object>>) agentDef.get("tools");
        List<String> toolNames = tools == null ? List.of()
            : tools.stream().map(t -> (String) t.get("name")).collect(Collectors.toList());

        assertFalse(toolNames.contains("ls"),
            "agentDef.tools must NOT contain a tool literally named 'ls' — that would be a leak from "
            + "cliConfig.allowedCommands into the user tools list. Tools: " + toolNames
            + ". COUNTERFACTUAL: this fails if the serializer mistakenly registers each allowed command as a tool.");
        assertFalse(toolNames.contains("mktemp"),
            "agentDef.tools must NOT contain a tool literally named 'mktemp'. Tools: " + toolNames);
    }
}
