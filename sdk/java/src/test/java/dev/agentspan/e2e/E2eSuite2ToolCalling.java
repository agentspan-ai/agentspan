// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.e2e;

import dev.agentspan.Agent;
import dev.agentspan.AgentRuntime;
import dev.agentspan.annotations.Tool;
import dev.agentspan.enums.AgentStatus;
import dev.agentspan.internal.ToolRegistry;
import dev.agentspan.model.AgentResult;
import org.junit.jupiter.api.*;

import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Suite 2: Tool Calling — agent execution with structural validation.
 *
 * <p>Tests verify that tools are actually called during execution by inspecting
 * the workflow task data — not by parsing LLM output text.
 *
 * <p>CLAUDE.md rule: no LLM for validation unless doing evals.
 * Structural assertions only: task status, task presence in workflow.
 */
@Tag("e2e")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class E2eSuite2ToolCalling extends E2eBaseTest {

    private static AgentRuntime runtime;

    @BeforeAll
    static void setup() {
        // Use BASE_URL (without /api suffix) since AgentConfig + HttpApi
        // already prepend /api to every path.
        runtime = new AgentRuntime(new dev.agentspan.AgentConfig(BASE_URL, null, null, 100, 1));
    }

    @AfterAll
    static void teardown() {
        if (runtime != null) runtime.close();
    }

    // ── Tool class ────────────────────────────────────────────────────────

    static class MathTools {
        @Tool(name = "add", description = "Add two integers and return the result")
        public int add(int a, int b) {
            return a + b;
        }
    }

    // ── Tests ─────────────────────────────────────────────────────────────

    /**
     * Agent calls the 'add' tool and the tool task completes successfully.
     *
     * COUNTERFACTUAL: if tool registration or serialization breaks, the tool task
     * won't appear in the workflow OR won't have status COMPLETED.
     *
     * Structural assertion: find the task whose referenceTaskName contains "add"
     * and assert its status == "COMPLETED".
     */
    @Test
    @Order(1)
    @Timeout(value = 300, unit = TimeUnit.SECONDS)
    @SuppressWarnings("unchecked")
    void test_agent_calls_worker_tool() {
        Agent agent = Agent.builder()
            .name("e2e_java_math_agent")
            .model(MODEL)
            .instructions("You MUST call the add tool with arguments a=7, b=8. Report the result.")
            .tools(ToolRegistry.fromInstance(new MathTools()))
            .maxTurns(3)
            .build();

        AgentResult result = runtime.run(agent, "What is 7 + 8?");

        assertEquals(AgentStatus.COMPLETED, result.getStatus(),
            "Agent did not complete. Status: " + result.getStatus()
            + ". Error: " + result.getError());

        String workflowId = result.getWorkflowId();
        assertNotNull(workflowId, "workflowId is null");
        assertFalse(workflowId.isEmpty(), "workflowId is empty");

        Map<String, Object> workflow = getWorkflow(workflowId);

        // Find all tasks in the workflow that relate to the 'add' tool
        List<Map<String, Object>> allWorkflowTasks = (List<Map<String, Object>>) workflow.get("tasks");
        assertNotNull(allWorkflowTasks, "workflow has no 'tasks' field");

        List<Map<String, Object>> addTasks = allWorkflowTasks.stream()
            .filter(t -> {
                String ref = (String) t.get("referenceTaskName");
                return ref != null && ref.contains("add");
            })
            .collect(Collectors.toList());

        assertFalse(addTasks.isEmpty(),
            "No task with referenceTaskName containing 'add' found in workflow. "
            + "Task names: " + allWorkflowTasks.stream()
                .map(t -> (String) t.get("referenceTaskName"))
                .collect(Collectors.toList())
            + ". COUNTERFACTUAL: if tool is never called, this task won't appear.");

        // Verify the tool task completed
        Map<String, Object> addTask = addTasks.get(0);
        String addTaskStatus = (String) addTask.get("status");
        assertEquals("COMPLETED", addTaskStatus,
            "Add tool task status is '" + addTaskStatus + "', expected 'COMPLETED'. "
            + "COUNTERFACTUAL: if the tool call fails, task won't be COMPLETED.");

        // Structural check: verify output contains the result of 7+8=15
        Object outputDataObj = addTask.get("outputData");
        if (outputDataObj instanceof Map) {
            Map<String, Object> outputData = (Map<String, Object>) outputDataObj;
            String outputStr = outputData.toString();
            assertTrue(outputStr.contains("15"),
                "Add tool output does not contain '15' (expected 7+8=15). "
                + "Output data: " + outputData
                + ". COUNTERFACTUAL: if the tool computation is wrong, 15 won't appear.");
        }
    }
}
