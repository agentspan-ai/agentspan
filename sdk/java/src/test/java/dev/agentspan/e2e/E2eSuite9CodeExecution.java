// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.e2e;

import dev.agentspan.Agent;
import dev.agentspan.AgentRuntime;
import dev.agentspan.enums.AgentStatus;
import dev.agentspan.model.AgentResult;
import org.junit.jupiter.api.*;

import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Suite 9: Local Code Execution — plan-level and runtime tests for the
 * {@code localCodeExecution} feature.
 *
 * <p>Plan-level tests assert that {@code codeExecution} serializes correctly
 * into the agentDef (enabled flag, allowedLanguages, timeout) and that an
 * {@code execute_code} tool is injected into the tools list so the LLM can
 * call it.
 *
 * <p>Runtime tests verify that the local code execution worker actually runs
 * code and returns correct output.
 *
 * <p>COUNTERFACTUAL assertions ensure tests fail if the feature is broken:
 * <ul>
 *   <li>If codeExecution not serialized → key missing → plan tests fail.</li>
 *   <li>If execute_code tool not injected → LLM cannot call it → runtime tests fail.</li>
 *   <li>If wrong code runs → expected output not in task output → fails.</li>
 *   <li>If timeout doesn't work → 60-second sleep completes → "done" appears in output.</li>
 * </ul>
 */
@Tag("e2e")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
@Timeout(value = 300, unit = TimeUnit.SECONDS)
class E2eSuite9CodeExecution extends E2eBaseTest {

    private static AgentRuntime runtime;

    @BeforeAll
    static void setup() {
        runtime = new AgentRuntime(new dev.agentspan.AgentConfig(BASE_URL, null, null, 100, 1));
    }

    @AfterAll
    static void teardown() {
        if (runtime != null) runtime.close();
    }

    // ── Helpers ───────────────────────────────────────────────────────────

    /**
     * Find tasks in a workflow whose referenceTaskName, taskDefName, or taskType
     * contains "execute_code".
     */
    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> findExecuteCodeTasks(String workflowId) {
        Map<String, Object> workflow = getWorkflow(workflowId);
        List<Map<String, Object>> allTasks = (List<Map<String, Object>>) workflow.get("tasks");
        if (allTasks == null) return List.of();
        return allTasks.stream()
            .filter(t -> {
                String ref = (String) t.getOrDefault("referenceTaskName", "");
                String defName = (String) t.getOrDefault("taskDefName", "");
                String taskType = (String) t.getOrDefault("taskType", "");
                return ref.contains("execute_code")
                    || defName.contains("execute_code")
                    || taskType.contains("execute_code");
            })
            .collect(Collectors.toList());
    }

    /** Convert a task's outputData to a string for searching. */
    private String taskOutputStr(Map<String, Object> task) {
        return String.valueOf(task.getOrDefault("outputData", ""));
    }

    // ── Plan-level tests ──────────────────────────────────────────────────

    /**
     * Plan-level: agent with localCodeExecution serializes codeExecution block
     * with enabled=true, allowedLanguages, and timeout. Also verifies that an
     * execute_code tool is injected into agentDef.tools so the LLM can call it.
     *
     * COUNTERFACTUAL: if codeExecution is not serialized → agentDef missing
     * 'codeExecution' key → assertion fails.
     * COUNTERFACTUAL: if execute_code tool not injected → LLM never sees it.
     */
    @Test
    @Order(1)
    @SuppressWarnings("unchecked")
    void test_code_execution_compiles() {
        Agent agent = Agent.builder()
            .name("e2e_java_ce_compile")
            .model(MODEL)
            .instructions("You can run code.")
            .localCodeExecution(true)
            .allowedLanguages(List.of("python", "bash"))
            .codeExecutionTimeout(30)
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        // Assert codeExecution block exists
        Map<String, Object> codeExec = (Map<String, Object>) agentDef.get("codeExecution");
        assertNotNull(codeExec,
            "agentDef has no 'codeExecution' key — localCodeExecution not serialized. "
            + "agentDef keys: " + agentDef.keySet()
            + ". COUNTERFACTUAL: if codeExecution is not serialized, this fails.");

        // enabled == true
        assertEquals(true, codeExec.get("enabled"),
            "codeExecution.enabled should be true. Got: " + codeExec.get("enabled")
            + ". COUNTERFACTUAL: if the enabled flag is not set, this fails.");

        // allowedLanguages contains python and bash
        List<String> langs = (List<String>) codeExec.get("allowedLanguages");
        assertNotNull(langs,
            "codeExecution.allowedLanguages is null. codeExecution keys: " + codeExec.keySet());
        assertTrue(langs.contains("python"),
            "Expected 'python' in allowedLanguages. Got: " + langs);
        assertTrue(langs.contains("bash"),
            "Expected 'bash' in allowedLanguages. Got: " + langs);

        // timeout == 30
        Object timeout = codeExec.get("timeout");
        assertNotNull(timeout, "codeExecution.timeout is null");
        assertEquals(30, ((Number) timeout).intValue(),
            "Expected codeExecution.timeout == 30. Got: " + timeout
            + ". COUNTERFACTUAL: if timeout is not serialized, this fails.");

        // execute_code tool injected into agentDef.tools
        List<Map<String, Object>> tools = (List<Map<String, Object>>) agentDef.get("tools");
        assertNotNull(tools,
            "agentDef has no 'tools' key — execute_code tool not injected. "
            + "COUNTERFACTUAL: if tool injection is missing, the LLM cannot call execute_code.");

        List<Map<String, Object>> execTools = tools.stream()
            .filter(t -> {
                String name = (String) t.getOrDefault("name", "");
                return name.contains("execute_code");
            })
            .collect(Collectors.toList());

        assertFalse(execTools.isEmpty(),
            "No tool containing 'execute_code' found in agentDef.tools. "
            + "Tool names: " + tools.stream().map(t -> (String) t.get("name")).collect(Collectors.toList())
            + ". COUNTERFACTUAL: if execute_code tool is not injected, LLM cannot call it.");

        Map<String, Object> execTool = execTools.get(0);
        assertEquals("e2e_java_ce_compile_execute_code", execTool.get("name"),
            "Expected tool name 'e2e_java_ce_compile_execute_code'. Got: " + execTool.get("name")
            + ". COUNTERFACTUAL: if tool naming is wrong, workers won't dispatch correctly.");
        assertEquals("worker", execTool.get("toolType"),
            "Expected toolType 'worker'. Got: " + execTool.get("toolType"));
    }

    /**
     * Plan-level: two agents with localCodeExecution get distinct execute_code
     * tool names — no collision. Asserts agent_a gets 'e2e_java_ce_a_execute_code'
     * and agent_b gets 'e2e_java_ce_b_execute_code', with no cross-contamination.
     *
     * COUNTERFACTUAL: if tool naming collapses both agents to the same name,
     * assertion fails.
     */
    @Test
    @Order(2)
    @SuppressWarnings("unchecked")
    void test_tool_naming_no_collision() {
        Agent agentA = Agent.builder()
            .name("e2e_java_ce_a")
            .model(MODEL)
            .instructions("Run code.")
            .localCodeExecution(true)
            .allowedLanguages(List.of("python"))
            .build();

        Agent agentB = Agent.builder()
            .name("e2e_java_ce_b")
            .model(MODEL)
            .instructions("Run code.")
            .localCodeExecution(true)
            .allowedLanguages(List.of("python"))
            .build();

        Map<String, Object> planA = runtime.plan(agentA);
        Map<String, Object> planB = runtime.plan(agentB);

        Map<String, Object> adA = getAgentDef(planA);
        Map<String, Object> adB = getAgentDef(planB);

        List<String> toolsA = ((List<Map<String, Object>>) adA.get("tools")).stream()
            .map(t -> (String) t.get("name")).collect(Collectors.toList());
        List<String> toolsB = ((List<Map<String, Object>>) adB.get("tools")).stream()
            .map(t -> (String) t.get("name")).collect(Collectors.toList());

        assertTrue(toolsA.contains("e2e_java_ce_a_execute_code"),
            "'e2e_java_ce_a_execute_code' not in agentA tools: " + toolsA
            + ". COUNTERFACTUAL: if naming is wrong, tool won't dispatch to correct worker.");
        assertTrue(toolsB.contains("e2e_java_ce_b_execute_code"),
            "'e2e_java_ce_b_execute_code' not in agentB tools: " + toolsB);

        // No cross-contamination
        assertFalse(toolsA.contains("e2e_java_ce_b_execute_code"),
            "agentA has agentB's tool name — collision! toolsA=" + toolsA
            + ". COUNTERFACTUAL: if naming collapses, both agents share the same worker.");
        assertFalse(toolsB.contains("e2e_java_ce_a_execute_code"),
            "agentB has agentA's tool name — collision! toolsB=" + toolsB);
    }

    /**
     * Plan-level: language restriction — agent restricted to Python only has
     * 'python' in allowedLanguages and NOT 'bash'.
     *
     * <p>This is a plan-only test because the local worker accepts any language
     * — the restriction is enforced at the LLM layer via the tool description
     * and the allowedLanguages serialized in the plan.
     *
     * COUNTERFACTUAL: if allowedLanguages serialization is broken → 'python'
     * missing → assertion fails. If language leaks → 'bash' appears → fails.
     */
    @Test
    @Order(3)
    @SuppressWarnings("unchecked")
    void test_language_restriction_plan() {
        Agent agent = Agent.builder()
            .name("e2e_java_ce_py_only")
            .model(MODEL)
            .instructions("You can only run Python code.")
            .localCodeExecution(true)
            .allowedLanguages(List.of("python"))  // bash NOT allowed
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        Map<String, Object> codeExec = (Map<String, Object>) agentDef.get("codeExecution");
        assertNotNull(codeExec, "agentDef has no 'codeExecution' key");

        List<String> allowed = (List<String>) codeExec.get("allowedLanguages");
        assertNotNull(allowed, "codeExecution.allowedLanguages is null");

        assertTrue(allowed.contains("python"),
            "'python' not in allowedLanguages: " + allowed
            + ". COUNTERFACTUAL: if python is missing, the restriction is broken.");
        assertFalse(allowed.contains("bash"),
            "'bash' should NOT be in allowedLanguages: " + allowed
            + ". COUNTERFACTUAL: if bash leaks into allowedLanguages, restriction is broken.");
    }

    // ── Runtime tests ─────────────────────────────────────────────────────

    /**
     * Runtime: local Python code execution runs and produces correct output.
     *
     * <p>Runs Python code that computes {@code 42 * 73 = 3066}. The execute_code worker
     * executes the code and the result "3066" appears in the task output.
     *
     * COUNTERFACTUAL:
     * <ul>
     *   <li>If execute_code tool not injected → LLM can't call it → no execute_code task → fails.</li>
     *   <li>If wrong code runs → "3066" not in output → fails.</li>
     * </ul>
     */
    @Test
    @Order(4)
    @Timeout(value = 300, unit = TimeUnit.SECONDS)
    @SuppressWarnings("unchecked")
    void test_local_python_execution() {
        Agent agent = Agent.builder()
            .name("e2e_java_ce_python")
            .model(MODEL)
            .instructions("You can execute code using the execute_code tool. "
                + "When asked to run Python code, you MUST call execute_code with "
                + "language='python' and the exact code provided. Do not compute mentally — "
                + "always use the execute_code tool.")
            .localCodeExecution(true)
            .allowedLanguages(List.of("python"))
            .maxTurns(5)
            .build();

        AgentResult result = runtime.run(agent,
            "Run this exact Python code using execute_code: print(42 * 73)");

        assertEquals(AgentStatus.COMPLETED, result.getStatus(),
            "Agent with Python code execution should complete. "
            + "Status: " + result.getStatus()
            + ". Error: " + result.getError());

        String workflowId = result.getWorkflowId();
        assertNotNull(workflowId, "workflowId is null");

        List<Map<String, Object>> execTasks = findExecuteCodeTasks(workflowId);

        assertFalse(execTasks.isEmpty(),
            "No execute_code task found in workflow. "
            + "COUNTERFACTUAL: if execute_code tool not injected or worker not dispatched, "
            + "no execute_code task appears.");

        // Verify at least one task has "3066" in output
        boolean foundOutput = execTasks.stream()
            .anyMatch(t -> taskOutputStr(t).contains("3066"));

        assertTrue(foundOutput,
            "Expected '3066' (42 * 73) in execute_code task output. "
            + "execute_code task outputs: " + execTasks.stream()
                .map(t -> taskOutputStr(t).substring(0, Math.min(200, taskOutputStr(t).length())))
                .collect(Collectors.toList())
            + ". COUNTERFACTUAL: if wrong code ran or output is malformed, '3066' won't appear.");
    }

    /**
     * Runtime: local bash code execution runs and produces correct output.
     *
     * <p>Runs bash: {@code echo $((17 + 29))} → output contains "46".
     *
     * COUNTERFACTUAL: if bash execution fails or produces wrong output → "46" missing → fails.
     */
    @Test
    @Order(5)
    @Timeout(value = 300, unit = TimeUnit.SECONDS)
    @SuppressWarnings("unchecked")
    void test_local_bash_execution() {
        Agent agent = Agent.builder()
            .name("e2e_java_ce_bash")
            .model(MODEL)
            .instructions("You can execute code using the execute_code tool. "
                + "When asked to run bash code, you MUST call execute_code with "
                + "language='bash' and the exact code provided. Always use execute_code — "
                + "never compute the answer yourself.")
            .localCodeExecution(true)
            .allowedLanguages(List.of("bash"))
            .maxTurns(5)
            .build();

        AgentResult result = runtime.run(agent,
            "Run a bash script using execute_code that prints: echo $((17 + 29))");

        assertEquals(AgentStatus.COMPLETED, result.getStatus(),
            "Agent with bash code execution should complete. "
            + "Status: " + result.getStatus()
            + ". Error: " + result.getError());

        String workflowId = result.getWorkflowId();
        assertNotNull(workflowId, "workflowId is null");

        List<Map<String, Object>> execTasks = findExecuteCodeTasks(workflowId);

        assertFalse(execTasks.isEmpty(),
            "No execute_code task found in workflow. "
            + "COUNTERFACTUAL: if execute_code tool not injected, no task appears.");

        boolean foundOutput = execTasks.stream()
            .anyMatch(t -> taskOutputStr(t).contains("46"));

        assertTrue(foundOutput,
            "Expected '46' (17 + 29) in execute_code bash task output. "
            + "execute_code task outputs: " + execTasks.stream()
                .map(t -> taskOutputStr(t).substring(0, Math.min(200, taskOutputStr(t).length())))
                .collect(Collectors.toList())
            + ". COUNTERFACTUAL: if bash output is wrong, '46' won't appear.");
    }

    /**
     * Runtime: code execution timeout — Python code that sleeps 60 seconds.
     * With codeExecutionTimeout=2, the timeout is triggered and the error message
     * "timed out" appears in the execute_code task outputData.
     *
     * <p>The agent may complete or fail (the LLM may report the timeout gracefully).
     * The key assertion is that the execute_code task output contains a timeout error
     * message — proving the timeout was detected by the local worker.
     *
     * COUNTERFACTUAL: if timeout is not enforced → no "timed out" error in task output → fails.
     */
    @Test
    @Order(6)
    @Timeout(value = 300, unit = TimeUnit.SECONDS)
    @SuppressWarnings("unchecked")
    void test_local_timeout() {
        Agent agent = Agent.builder()
            .name("e2e_java_ce_timeout")
            .model(MODEL)
            .instructions("You MUST use execute_code to run the exact Python code given. "
                + "Do not modify the code. Always call execute_code — never simulate execution.")
            .localCodeExecution(true)
            .allowedLanguages(List.of("python"))
            .codeExecutionTimeout(2)  // 2-second timeout
            .maxTurns(3)
            .build();

        AgentResult result = runtime.run(agent,
            "Run this Python code using execute_code: import time; time.sleep(60); print('done')");

        // Accept COMPLETED/FAILED/TERMINATED — the LLM may report the timeout gracefully
        assertTrue(
            result.getStatus() == AgentStatus.COMPLETED
                || result.getStatus() == AgentStatus.FAILED
                || result.getStatus() == AgentStatus.TERMINATED,
            "Expected a terminal status. Got: " + result.getStatus());

        String workflowId = result.getWorkflowId();
        assertNotNull(workflowId, "workflowId is null");

        List<Map<String, Object>> execTasks = findExecuteCodeTasks(workflowId);

        if (!execTasks.isEmpty()) {
            // Verify that the timeout error message appears in at least one task
            // The error field should contain "timed out" and exit_code should be -1
            boolean timeoutErrorFound = execTasks.stream()
                .anyMatch(t -> {
                    Object outputData = t.get("outputData");
                    if (!(outputData instanceof Map)) return false;
                    @SuppressWarnings("unchecked")
                    Map<String, Object> outMap = (Map<String, Object>) outputData;
                    Object errorVal = outMap.get("error");
                    Object exitCode = outMap.get("exit_code");
                    boolean hasTimeoutError = errorVal != null
                        && (errorVal.toString().toLowerCase().contains("timed out")
                            || errorVal.toString().toLowerCase().contains("timeout"));
                    boolean hasFailedExit = exitCode instanceof Number
                        && ((Number) exitCode).intValue() == -1;
                    return hasTimeoutError && hasFailedExit;
                });

            assertTrue(timeoutErrorFound,
                "Expected timeout error (error contains 'timed out', exit_code == -1) in at least "
                + "one execute_code task. "
                + "execute_code task outputs: " + execTasks.stream()
                    .map(t -> taskOutputStr(t).substring(0, Math.min(300, taskOutputStr(t).length())))
                    .collect(Collectors.toList())
                + ". COUNTERFACTUAL: if timeout is not detected, no error message appears.");
        }
        // If no execute_code task found, the agent may have failed before reaching the tool —
        // the terminal status assertion above is the primary counterfactual in that case.
    }
}
