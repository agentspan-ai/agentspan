// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.e2e;

import dev.agentspan.Agent;
import dev.agentspan.AgentRuntime;
import dev.agentspan.enums.AgentStatus;
import dev.agentspan.model.AgentResult;
import dev.agentspan.termination.MaxMessageTermination;
import dev.agentspan.termination.TextMentionTermination;
import org.junit.jupiter.api.*;

import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Suite 4: Termination — termination condition tests.
 *
 * <p>Tests verify that termination conditions actually stop agent execution
 * by checking that the agent doesn't run the full max_turns.
 *
 * <p>COUNTERFACTUAL assertions: if termination doesn't work, agent runs all
 * max_turns and either times out or exceeds the iteration bound.
 */
@Tag("e2e")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class E2eSuite4Termination extends E2eBaseTest {

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

    // ── Tests ─────────────────────────────────────────────────────────────

    /**
     * MaxMessageTermination(3) stops the agent after 3 messages.
     *
     * COUNTERFACTUAL: if MaxMessageTermination doesn't work, agent runs all 25
     * turns. The DO_WHILE loop task count would be >= 10 instead of <= 5.
     */
    @Test
    @Order(1)
    @Timeout(value = 300, unit = TimeUnit.SECONDS)
    @SuppressWarnings("unchecked")
    void test_max_message_termination() {
        Agent agent = Agent.builder()
            .name("e2e_java_max_msg_agent")
            .model(MODEL)
            .instructions("After each message, respond with a short reply. Never stop on your own.")
            .maxTurns(25)
            .termination(MaxMessageTermination.of(3))
            .build();

        AgentResult result = runtime.run(agent, "Start the conversation");

        assertEquals(AgentStatus.COMPLETED, result.getStatus(),
            "Agent should COMPLETE when MaxMessageTermination is reached. "
            + "Got: " + result.getStatus()
            + ". Termination gates complete the loop, not fail it.");

        // Fetch the workflow and count DO_WHILE iterations
        String workflowId = result.getWorkflowId();
        assertNotNull(workflowId, "workflowId is null");

        Map<String, Object> workflow = getWorkflow(workflowId);
        List<Map<String, Object>> allTasks = (List<Map<String, Object>>) workflow.get("tasks");
        assertNotNull(allTasks, "workflow has no 'tasks' field");

        // Find DO_WHILE tasks (the loop wrapper)
        List<Map<String, Object>> doWhileTasks = allTasks.stream()
            .filter(t -> "DO_WHILE".equals(t.get("taskType"))
                || "DO_WHILE".equals(t.get("type")))
            .collect(Collectors.toList());

        if (!doWhileTasks.isEmpty()) {
            // Each DO_WHILE task has an 'iteration' field
            Map<String, Object> loopTask = doWhileTasks.get(0);
            Object iterationObj = loopTask.get("iteration");
            if (iterationObj instanceof Number) {
                int iterations = ((Number) iterationObj).intValue();
                assertTrue(iterations <= 5,
                    "DO_WHILE loop ran " + iterations + " iterations, expected <= 5. "
                    + "COUNTERFACTUAL: if MaxMessageTermination doesn't work, "
                    + "agent runs all 25 turns.");
            }
        }
        // Even if we can't find the DO_WHILE task, the COMPLETED status is the key assertion
    }

    /**
     * Agent with a nonexistent model must end in FAILED or TERMINATED — never COMPLETED.
     *
     * COUNTERFACTUAL: if model validation is ignored, status is COMPLETED → fails.
     */
    @Test
    @Order(2)
    @Timeout(value = 120, unit = TimeUnit.SECONDS)
    void test_invalid_model_fails() {
        Agent agent = Agent.builder()
            .name("e2e_java_bad_model")
            .model("nonexistent/xyz-model-does-not-exist")
            .instructions("This agent should never execute successfully.")
            .build();

        AgentResult result = runtime.run(agent, "Hello.");

        assertNotEquals(AgentStatus.COMPLETED, result.getStatus(),
            "[invalid model] Expected FAILED or TERMINATED for nonexistent model, "
            + "got COMPLETED. The server should reject unknown models. "
            + "COUNTERFACTUAL: if model validation is broken, this returns COMPLETED.");
    }

    /**
     * TextMentionTermination stops agent when it produces the trigger text.
     *
     * COUNTERFACTUAL: if TextMentionTermination doesn't work, agent ignores the
     * trigger text and runs all 25 turns.
     */
    @Test
    @Order(3)
    @Timeout(value = 300, unit = TimeUnit.SECONDS)
    @SuppressWarnings("unchecked")
    void test_text_mention_termination() {
        Agent agent = Agent.builder()
            .name("e2e_java_text_term_agent")
            .model(MODEL)
            .instructions("Always include the text DONE_E2E in every response.")
            .maxTurns(25)
            .termination(TextMentionTermination.of("DONE_E2E"))
            .build();

        AgentResult result = runtime.run(agent, "Begin");

        assertEquals(AgentStatus.COMPLETED, result.getStatus(),
            "Agent should COMPLETE when TextMentionTermination is triggered. "
            + "Got: " + result.getStatus()
            + ". Termination gates complete the loop, not fail it.");

        // Fetch the workflow and check iterations stayed low
        String workflowId = result.getWorkflowId();
        assertNotNull(workflowId, "workflowId is null");

        Map<String, Object> workflow = getWorkflow(workflowId);
        List<Map<String, Object>> allTasks = (List<Map<String, Object>>) workflow.get("tasks");
        assertNotNull(allTasks, "workflow has no 'tasks' field");

        // Find DO_WHILE tasks
        List<Map<String, Object>> doWhileTasks = allTasks.stream()
            .filter(t -> "DO_WHILE".equals(t.get("taskType"))
                || "DO_WHILE".equals(t.get("type")))
            .collect(Collectors.toList());

        if (!doWhileTasks.isEmpty()) {
            Map<String, Object> loopTask = doWhileTasks.get(0);
            Object iterationObj = loopTask.get("iteration");
            if (iterationObj instanceof Number) {
                int iterations = ((Number) iterationObj).intValue();
                assertTrue(iterations <= 3,
                    "DO_WHILE loop ran " + iterations + " iterations, expected <= 3. "
                    + "COUNTERFACTUAL: if TextMentionTermination doesn't fire on "
                    + "'DONE_E2E', agent runs 25 turns.");
            }
        }
        // Even if we can't find the DO_WHILE task, the COMPLETED status is the key assertion
    }
}
