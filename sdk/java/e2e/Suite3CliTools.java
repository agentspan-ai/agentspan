// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

import org.conductoross.conductor.ai.Agent;
import org.conductoross.conductor.ai.AgentConfig;
import org.conductoross.conductor.ai.AgentRuntime;
import org.conductoross.conductor.ai.enums.AgentStatus;
import org.conductoross.conductor.ai.execution.CliConfig;
import org.conductoross.conductor.ai.model.AgentResult;
import org.conductoross.conductor.ai.model.CompileResponse;
import org.junit.jupiter.api.*;

/**
 * Suite 3: CLI Tools — plan-level AND runtime tests for {@link CliConfig}.
 *
 * <p>Mirrors Python {@code test_suite3_cli_tools.py}, TypeScript
 * {@code test_suite3_cli_tools.test.ts} and C# {@code Suite11_CliTools}.
 *
 * <p><b>Plan-level tests</b> assert the SDK serializes a {@code cliConfig} block
 * on the agentDef (allowed commands, timeout, allowShell, enabled) and injects a
 * {@code {name}_run_command} worker tool so the LLM can call it.
 *
 * <p><b>Runtime tests</b> actually run an agent and verify the local
 * {@code run_command} worker executes commands and enforces the whitelist —
 * the command is executed locally by this SDK
 * ({@code org.conductoross.conductor.ai.execution.CliCommandExecutor}), NOT by the server. These
 * are the functional checks whose absence previously let a non-functional CLI
 * feature ship: the LLM drives the agent, but validation is deterministic
 * (literal markers / "not allowed" in the task output), never LLM-judged.
 *
 * <p>Each assertion has a counterfactual: a contrast assertion in the same test,
 * or a companion test that builds an agent WITHOUT the feature.
 */
@Tag("e2e")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
@Timeout(value = 300, unit = TimeUnit.SECONDS)
class Suite3CliTools extends BaseTest {

    private static AgentRuntime runtime;

    @BeforeAll
    static void setup() {
        runtime = new AgentRuntime(new AgentConfig(100, 1));
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

        assertTrue(
                restrictive.isEnabled(),
                "CliConfig.enabled defaults to true. COUNTERFACTUAL: if enabled flips, the CLI tool is silently off.");
        assertEquals(
                List.of("ls", "mktemp", "gh"),
                restrictive.getAllowedCommands(),
                "allowedCommands must round-trip. COUNTERFACTUAL: if the list is dropped, the whitelist is empty.");
        assertEquals(
                45,
                restrictive.getTimeout(),
                "timeout must round-trip. COUNTERFACTUAL: if dropped, default 30 returned.");
        assertFalse(
                restrictive.isAllowShell(),
                "allowShell=false must round-trip. COUNTERFACTUAL: if dropped, allowShell defaults to false anyway, so assert the contrast below.");
        assertEquals(
                "/tmp",
                restrictive.getWorkingDir(),
                "workingDir must round-trip. COUNTERFACTUAL: if dropped, returned null.");

        // Counterfactual contrast — a permissive config differs on each property
        CliConfig permissive = CliConfig.builder()
                .allowedCommands(List.of("anything"))
                .timeout(120)
                .allowShell(true)
                .build();
        assertNotEquals(
                restrictive.getAllowedCommands(),
                permissive.getAllowedCommands(),
                "Two builders must produce distinct allowedCommands.");
        assertNotEquals(
                restrictive.getTimeout(), permissive.getTimeout(), "Two builders must produce distinct timeouts.");
        assertNotEquals(
                restrictive.isAllowShell(),
                permissive.isAllowShell(),
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

        CompileResponse plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        Map<String, Object> cliMap = (Map<String, Object>) agentDef.get("cliConfig");
        assertNotNull(
                cliMap,
                "agentDef.cliConfig is null. COUNTERFACTUAL: setting cliConfig on the Agent must serialize "
                        + "to agentDef.cliConfig. agentDef keys: " + agentDef.keySet());

        assertEquals(
                Boolean.TRUE, cliMap.get("enabled"), "cliConfig.enabled should be true. Got: " + cliMap.get("enabled"));

        List<String> serializedCmds = (List<String>) cliMap.get("allowedCommands");
        assertNotNull(serializedCmds, "cliConfig.allowedCommands is null.");
        assertEquals(
                allowed.size(),
                serializedCmds.size(),
                "allowedCommands size mismatch. Expected " + allowed.size() + " but got " + serializedCmds.size());
        assertTrue(
                serializedCmds.containsAll(allowed),
                "allowedCommands must contain all of " + allowed + " but got " + serializedCmds
                        + ". COUNTERFACTUAL: if a command is dropped, the whitelist diverges.");

        Object timeoutObj = cliMap.get("timeout");
        assertNotNull(timeoutObj, "cliConfig.timeout is null");
        assertEquals(60, ((Number) timeoutObj).intValue(), "cliConfig.timeout should be 60. Got: " + timeoutObj);

        assertEquals(
                Boolean.FALSE,
                cliMap.get("allowShell"),
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

        CompileResponse plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        assertFalse(
                agentDef.containsKey("cliConfig"),
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

        CompileResponse plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        Map<String, Object> cliMap = (Map<String, Object>) agentDef.get("cliConfig");
        assertNotNull(cliMap, "agentDef.cliConfig is null.");

        assertEquals(
                Boolean.TRUE,
                cliMap.get("allowShell"),
                "cliConfig.allowShell should be true. Got: " + cliMap.get("allowShell")
                        + ". COUNTERFACTUAL: paired with the false-case in test_cli_config_serializes_to_agentDef.");
        Object timeoutObj = cliMap.get("timeout");
        assertEquals(
                15,
                ((Number) timeoutObj).intValue(),
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

        CompileResponse planA = runtime.plan(agentA);
        CompileResponse planB = runtime.plan(agentB);

        Map<String, Object> cliA = (Map<String, Object>) getAgentDef(planA).get("cliConfig");
        Map<String, Object> cliB = (Map<String, Object>) getAgentDef(planB).get("cliConfig");

        assertNotNull(cliA, "agentA cliConfig missing.");
        assertNotNull(cliB, "agentB cliConfig missing.");

        List<String> cmdsA = (List<String>) cliA.get("allowedCommands");
        List<String> cmdsB = (List<String>) cliB.get("allowedCommands");

        assertTrue(
                cmdsA.contains("ls") && !cmdsA.contains("gh"),
                "agentA should have 'ls' only. Got: " + cmdsA
                        + ". COUNTERFACTUAL: if state leaks, agentA would also have 'gh' from agentB.");
        assertTrue(
                cmdsB.contains("gh") && !cmdsB.contains("ls"),
                "agentB should have 'gh' but not 'ls'. Got: " + cmdsB
                        + ". COUNTERFACTUAL: if state leaks, agentB would have 'ls' from agentA.");

        int timeoutA = ((Number) cliA.get("timeout")).intValue();
        int timeoutB = ((Number) cliB.get("timeout")).intValue();
        assertNotEquals(
                timeoutA,
                timeoutB,
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

        CompileResponse plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        List<Map<String, Object>> tools = (List<Map<String, Object>>) agentDef.get("tools");
        List<String> toolNames = tools == null
                ? List.of()
                : tools.stream().map(t -> (String) t.get("name")).collect(Collectors.toList());

        assertFalse(
                toolNames.contains("ls"),
                "agentDef.tools must NOT contain a tool literally named 'ls' — that would be a leak from "
                        + "cliConfig.allowedCommands into the user tools list. Tools: " + toolNames
                        + ". COUNTERFACTUAL: this fails if the serializer mistakenly registers each allowed command as a tool.");
        assertFalse(
                toolNames.contains("mktemp"),
                "agentDef.tools must NOT contain a tool literally named 'mktemp'. Tools: " + toolNames);
    }

    // ── Runtime tests ─────────────────────────────────────────────────────────

    /** Find workflow tasks belonging to the run_command worker. */
    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> findRunCommandTasks(String executionId) {
        Map<String, Object> workflow = getWorkflow(executionId);
        List<Map<String, Object>> allTasks = (List<Map<String, Object>>) workflow.get("tasks");
        if (allTasks == null) return List.of();
        return allTasks.stream()
                .filter(t -> {
                    String ref = (String) t.getOrDefault("referenceTaskName", "");
                    String defName = (String) t.getOrDefault("taskDefName", "");
                    String taskType = (String) t.getOrDefault("taskType", "");
                    return ref.contains("run_command")
                            || defName.contains("run_command")
                            || taskType.contains("run_command");
                })
                .collect(Collectors.toList());
    }

    private String taskOutputStr(Map<String, Object> task) {
        return String.valueOf(task.getOrDefault("outputData", ""));
    }

    /**
     * Runtime: the local run_command worker actually executes a command and the
     * output flows back into the run_command task. This is the functional check
     * that proves the CLI feature is wired end-to-end (tool injected → SIMPLE task
     * created → SDK worker polls → command executed locally → output captured).
     *
     * <p>Runs {@code echo cli_marker_3066}; the literal marker must appear in a
     * run_command task's output. The marker is unique so it can only come from the
     * command actually running — not from the prompt being echoed by the LLM.
     *
     * COUNTERFACTUAL: if no run_command worker is registered (the previous state of
     * the Java SDK), no run_command task produces output containing the marker.
     */
    @Test
    @Order(7)
    @Timeout(value = 300, unit = TimeUnit.SECONDS)
    void test_local_cli_execution() {
        Agent agent = Agent.builder()
                .name("e2e_s3_cli_exec")
                .model(MODEL)
                .instructions("You run shell commands with the run_command tool. "
                        + "When asked to run a command, you MUST call run_command with the exact "
                        + "command given. Never fabricate output — always call the tool.")
                .cliConfig(CliConfig.builder()
                        .allowedCommands(List.of("echo"))
                        .timeout(30)
                        .build())
                .maxTurns(5)
                .build();

        AgentResult result = runtime.run(agent, "Run this exact command using run_command: echo cli_marker_3066");

        assertEquals(
                AgentStatus.COMPLETED,
                result.getStatus(),
                "Agent with CLI execution should complete. Status: " + result.getStatus() + ". Error: "
                        + result.getError());

        String executionId = result.getExecutionId();
        assertNotNull(executionId, "executionId is null");

        List<Map<String, Object>> tasks = findRunCommandTasks(executionId);
        assertFalse(
                tasks.isEmpty(),
                "No run_command task found in workflow. COUNTERFACTUAL: if the run_command "
                        + "tool is not injected or no worker is registered to execute it, no such task appears.");

        boolean foundMarker = tasks.stream().anyMatch(t -> taskOutputStr(t).contains("cli_marker_3066"));
        assertTrue(
                foundMarker,
                "Expected 'cli_marker_3066' in a run_command task output — proves the local "
                        + "worker actually executed `echo`. Outputs: "
                        + tasks.stream()
                                .map(t -> taskOutputStr(t)
                                        .substring(
                                                0,
                                                Math.min(200, taskOutputStr(t).length())))
                                .collect(Collectors.toList())
                        + ". COUNTERFACTUAL: a non-functional executor produces no marker.");
    }

    /**
     * Runtime: the local worker enforces the whitelist. An agent allowed only
     * {@code echo} that is asked to run {@code ls} must have its run_command task
     * report the command as not allowed — proving validation runs in the worker,
     * not just in the prompt.
     *
     * COUNTERFACTUAL: if the worker skipped validation, {@code ls} would execute
     * (directory listing in stdout) and "not allowed" would be absent.
     */
    @Test
    @Order(8)
    @Timeout(value = 300, unit = TimeUnit.SECONDS)
    void test_cli_whitelist_blocks_disallowed_command() {
        Agent agent = Agent.builder()
                .name("e2e_s3_cli_whitelist")
                .model(MODEL)
                .instructions("You run shell commands with the run_command tool. "
                        + "When asked to run a command, call run_command with that exact command, "
                        + "even if you suspect it may be rejected. Report what the tool returns.")
                .cliConfig(CliConfig.builder()
                        .allowedCommands(List.of("echo")) // ls is NOT allowed
                        .timeout(30)
                        .build())
                .maxTurns(5)
                .build();

        AgentResult result = runtime.run(agent, "Use run_command to run exactly: ls -la /");

        // Terminal status either way — the worker returns an error result, it does
        // not fail the task; the LLM may then complete gracefully.
        assertTrue(
                result.getStatus() == AgentStatus.COMPLETED
                        || result.getStatus() == AgentStatus.FAILED
                        || result.getStatus() == AgentStatus.TERMINATED,
                "Expected a terminal status. Got: " + result.getStatus());

        String executionId = result.getExecutionId();
        assertNotNull(executionId, "executionId is null");

        List<Map<String, Object>> tasks = findRunCommandTasks(executionId);
        assertFalse(
                tasks.isEmpty(), "No run_command task found — the LLM should have attempted the disallowed command.");

        boolean blocked =
                tasks.stream().anyMatch(t -> taskOutputStr(t).toLowerCase().contains("is not allowed"));
        assertTrue(
                blocked,
                "Expected a run_command task to report 'is not allowed' for `ls`. Outputs: "
                        + tasks.stream()
                                .map(t -> taskOutputStr(t)
                                        .substring(
                                                0,
                                                Math.min(200, taskOutputStr(t).length())))
                                .collect(Collectors.toList())
                        + ". COUNTERFACTUAL: if the worker skipped whitelist validation, `ls` would run "
                        + "and there would be no 'not allowed' message.");
    }
}
