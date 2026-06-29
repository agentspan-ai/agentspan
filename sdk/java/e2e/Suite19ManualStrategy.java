// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

import static org.junit.jupiter.api.Assertions.*;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

import org.conductoross.conductor.ai.Agent;
import org.conductoross.conductor.ai.AgentConfig;
import org.conductoross.conductor.ai.AgentRuntime;
import org.conductoross.conductor.ai.enums.AgentStatus;
import org.conductoross.conductor.ai.enums.EventType;
import org.conductoross.conductor.ai.enums.Strategy;
import org.conductoross.conductor.ai.model.AgentEvent;
import org.conductoross.conductor.ai.model.AgentResult;
import org.conductoross.conductor.ai.model.AgentStream;
import org.junit.jupiter.api.*;

/**
 * Suite 19: MANUAL strategy — functional test for the human-gated agent picker.
 *
 * <p>MANUAL was previously serialized + enumerated in plan-only tests but NEVER
 * run end-to-end in any SDK. Its {@code {name}_process_selection} worker (which
 * maps the human-selected agent NAME → its positional INDEX so the server's
 * SWITCH can route) had zero functional coverage — the same blind spot that hid
 * the dead CLI feature. This suite drives the full path:
 *
 * <ol>
 *   <li>run a MANUAL coordinator with two distinguishable sub-agents</li>
 *   <li>the workflow pauses at the {@code pick_agent} HUMAN task</li>
 *   <li>we respond {@code {"selected": "<beta>"}} — the SECOND agent, so a
 *       broken name→index mapping (which would default to index 0 = alpha) is
 *       caught</li>
 *   <li>assert the SELECTED sub-agent's sub-workflow ran and the other did not</li>
 * </ol>
 *
 * <p>No LLM judging: the pick is deterministic human input and validation is on
 * the workflow's SUB_WORKFLOW task names.
 *
 * COUNTERFACTUAL: if the process_selection worker is not registered, that SIMPLE
 * task never completes → the workflow never finishes → the status assertion
 * fails. If the name→index mapping is wrong, alpha runs instead of beta → the
 * routing assertion fails.
 */
@Tag("e2e")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
@Timeout(value = 300, unit = TimeUnit.SECONDS)
class Suite19ManualStrategy extends BaseTest {

    private static AgentRuntime runtime;

    private static final HttpClient HTTP =
            HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).build();

    @BeforeAll
    static void setup() {
        runtime = new AgentRuntime(new AgentConfig(100, 1));
    }

    @AfterAll
    static void teardown() {
        if (runtime != null) runtime.close();
    }

    /** POST {"selected": "<agentName>"} to complete the pending pick_agent HUMAN task. */
    private void selectAgent(String executionId, String agentName) {
        try {
            String body = "{\"selected\":\"" + agentName + "\"}";
            HttpRequest req = HttpRequest.newBuilder()
                    .uri(URI.create(BASE_URL + "/api/agent/" + executionId + "/respond"))
                    .timeout(Duration.ofSeconds(10))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(body))
                    .build();
            HttpResponse<String> resp = HTTP.send(req, HttpResponse.BodyHandlers.ofString());
            assertTrue(
                    resp.statusCode() < 400, "respond POST failed: HTTP " + resp.statusCode() + " body=" + resp.body());
        } catch (Exception e) {
            fail("Failed to POST selection for " + executionId + ": " + e.getMessage());
        }
    }

    @Test
    @Order(1)
    @Timeout(value = 300, unit = TimeUnit.SECONDS)
    @SuppressWarnings("unchecked")
    void test_manual_selection_routes_to_chosen_agent() {
        Agent alpha = Agent.builder()
                .name("e2e_s19_alpha")
                .model(MODEL)
                .instructions("You are ALPHA. Always reply with exactly: ALPHA_REPLIED")
                .maxTurns(1)
                .build();
        Agent beta = Agent.builder()
                .name("e2e_s19_beta")
                .model(MODEL)
                .instructions("You are BETA. Always reply with exactly: BETA_REPLIED")
                .maxTurns(1)
                .build();

        Agent coordinator = Agent.builder()
                .name("e2e_s19_manual")
                .model(MODEL)
                .instructions("A human picks which agent answers.")
                .agents(alpha, beta)
                .strategy(Strategy.MANUAL)
                .maxTurns(1)
                .build();

        String executionId;
        try (AgentStream stream = runtime.stream(coordinator, "Who should answer this?")) {
            executionId = stream.getExecutionId();
            assertNotNull(executionId, "stream has no executionId");

            int picks = 0;
            for (AgentEvent event : stream) {
                if (event.getType() == EventType.WAITING) {
                    // Pick BETA (the second agent) — exercises name→index != 0.
                    String target = event.getExecutionId() != null
                                    && !event.getExecutionId().isEmpty()
                            ? event.getExecutionId()
                            : executionId;
                    selectAgent(target, "e2e_s19_beta");
                    picks++;
                    assertTrue(picks <= 5, "too many pick prompts; MANUAL loop did not settle");
                }
            }

            assertTrue(
                    picks > 0,
                    "Expected a WAITING event for the pick_agent HUMAN task. "
                            + "COUNTERFACTUAL: if MANUAL doesn't reach the human picker, no WAITING event fires.");

            AgentResult result = stream.waitForResult(180_000, 1_000);
            assertEquals(
                    AgentStatus.COMPLETED,
                    result.getStatus(),
                    "MANUAL workflow did not complete after selection. status=" + result.getStatus()
                            + " error=" + result.getError()
                            + ". COUNTERFACTUAL: if the process_selection worker is unregistered, that "
                            + "SIMPLE task hangs and the workflow never completes.");
        }

        // Assert the SELECTED sub-agent (beta) ran and the other (alpha) did not.
        Map<String, Object> workflow = getWorkflow(executionId);
        List<Map<String, Object>> tasks = (List<Map<String, Object>>) workflow.get("tasks");
        assertNotNull(tasks, "workflow has no 'tasks'");

        List<String> subWorkflowRefs = tasks.stream()
                .filter(t -> "SUB_WORKFLOW".equals(t.getOrDefault("taskType", "")))
                .map(t -> String.valueOf(t.getOrDefault("referenceTaskName", "")))
                .collect(Collectors.toList());

        boolean betaRan = subWorkflowRefs.stream().anyMatch(r -> r.contains("beta"));
        boolean alphaRan = subWorkflowRefs.stream().anyMatch(r -> r.contains("alpha"));

        assertTrue(
                betaRan,
                "Expected a SUB_WORKFLOW for the selected agent 'beta'. SUB_WORKFLOW refs: "
                        + subWorkflowRefs
                        + ". COUNTERFACTUAL: if process_selection mapped the name to the wrong index, "
                        + "beta's sub-workflow would never be routed to.");
        assertFalse(
                alphaRan,
                "Did NOT expect a SUB_WORKFLOW for the unselected agent 'alpha'. SUB_WORKFLOW refs: "
                        + subWorkflowRefs
                        + ". COUNTERFACTUAL: a name→index mapping that defaults to 0 would route to alpha.");
    }
}
