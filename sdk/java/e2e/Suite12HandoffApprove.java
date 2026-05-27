// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

import ai.agentspan.Agent;
import ai.agentspan.AgentRuntime;
import ai.agentspan.annotations.Tool;
import ai.agentspan.enums.AgentStatus;
import ai.agentspan.enums.EventType;
import ai.agentspan.enums.Strategy;
import ai.agentspan.internal.ToolRegistry;
import ai.agentspan.model.AgentEvent;
import ai.agentspan.model.AgentResult;
import ai.agentspan.model.AgentStream;
import ai.agentspan.model.ToolDef;
import org.junit.jupiter.api.*;

import java.util.List;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Suite 12: Handoff + Human-in-the-Loop.
 *
 * <p>Under {@link Strategy#HANDOFF} an approval-required tool may live on a
 * sub-agent, in which case the HUMAN task is created inside the sub-execution
 * — not the orchestrator's top-level execution. The {@code WAITING} event
 * carries the owning sub-execution id, and the targeted
 * {@link AgentStream#approve(AgentEvent)} overload posts to that id.
 */
@Tag("e2e")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
@Timeout(value = 300, unit = TimeUnit.SECONDS)
class Suite12HandoffApprove extends BaseTest {

    private static AgentRuntime runtime;

    @BeforeAll
    static void setup() {
        runtime = new AgentRuntime(new ai.agentspan.AgentConfig(BASE_URL, null, null, 100, 1));
    }

    @AfterAll
    static void teardown() {
        if (runtime != null) runtime.close();
    }

    /** Approval-required tool that lives on the sub-agent. */
    public static class ApprovalTools {
        @Tool(
            name = "submit_change",
            description = "Submit a configuration change after human approval",
            approvalRequired = true
        )
        public String submitChange(String change) {
            return "Change submitted: " + change;
        }
    }

    private Agent buildHandoffAgent(String name) {
        List<ToolDef> approvalTools = ToolRegistry.fromInstance(new ApprovalTools());

        Agent reviewer = Agent.builder()
            .name(name + "_reviewer")
            .model(MODEL)
            .instructions("You submit configuration changes. Always call submit_change with the requested change.")
            .tools(approvalTools)
            .maxTurns(2)
            .build();

        // maxTurns(1) on the parent bounds the orchestrator's DO_WHILE: one
        // LLM call routes the handoff and the loop exits. Without this,
        // gpt-4o-mini sometimes decides to route a second time after the
        // sub-agent replies, queueing another HUMAN approval that the test
        // never sees — the workflow hangs until the JUnit timeout fires.
        return Agent.builder()
            .name(name)
            .model(MODEL)
            .instructions("Route every configuration change request to the reviewer sub-agent ONCE, then you are done. Do not answer directly.")
            .agents(reviewer)
            .strategy(Strategy.HANDOFF)
            .maxTurns(1)
            .build();
    }

    /**
     * A {@code WAITING} event emitted from a sub-agent must identify the
     * sub-execution that owns the HUMAN task — not the top-level orchestrator.
     */
    @Test
    @Order(1)
    @Timeout(value = 300, unit = TimeUnit.SECONDS)
    void test_waiting_event_carries_sub_execution_id() {
        Agent support = buildHandoffAgent("e2e_java_handoff_waiting_id");

        try (AgentStream stream = runtime.stream(support,
                "Please submit this configuration change: enable feature flag java_e2e_hitl.")) {

            String topExecutionId = stream.getExecutionId();
            assertNotNull(topExecutionId);
            assertFalse(topExecutionId.isEmpty());

            AgentEvent waiting = null;
            int approvals = 0;
            for (AgentEvent event : stream) {
                if (event.getType() == EventType.WAITING) {
                    if (waiting == null) waiting = event;
                    stream.approve(event); // let the run terminate so we don't leak server state
                    approvals++;
                    assertTrue(approvals <= 5, "too many approval prompts; handoff did not settle");
                }
            }

            assertNotNull(waiting, "expected a WAITING event from the sub-agent's approval-required tool");

            String waitingExecId = waiting.getExecutionId();
            assertNotNull(waitingExecId, "WAITING event must carry an execution id");
            assertFalse(waitingExecId.isEmpty(), "WAITING event execution id must not be empty");
            assertNotEquals(topExecutionId, waitingExecId,
                "under HANDOFF the HUMAN task lives in the sub-execution, "
                + "so the WAITING event id must differ from the top-level execution id");
        }
    }

    /**
     * Approving a {@code WAITING} event from a sub-agent must resume the
     * sub-execution and let the workflow run to completion.
     *
     * <p>After approve, the resumed sub-execution emits its
     * {@code TOOL_RESULT}/{@code DONE} events on a separate SSE channel from
     * the one this test is subscribed to, so the original stream's blocking
     * {@code getResult()} would wait until the HttpClient's 10-minute request
     * timeout fired — which (a) eats the whole 900s test budget on a single
     * attempt and (b) the retry loop never actually got a chance to run.
     * The fix mirrors the TS Suite16 {@code test_hitl_approve_path} pattern:
     * poll the workflow status via REST after approving.
     */
    @Test
    @Order(2)
    @Timeout(value = 600, unit = TimeUnit.SECONDS)
    void test_approve_with_event_completes_handoff_hitl() throws Exception {
        Throwable lastErr = null;
        final int maxAttempts = 3;
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                runApproveWithEventOnce();
                return; // pass
            } catch (RuntimeException | org.opentest4j.AssertionFailedError e) {
                lastErr = e;
                if (attempt < maxAttempts) {
                    System.err.println("[Suite12 HITL] attempt " + attempt + " failed ("
                        + e.getClass().getSimpleName() + "): " + e.getMessage() + " — retrying.");
                }
            }
        }
        if (lastErr instanceof Exception ex) throw ex;
        if (lastErr instanceof Error err) throw err;
    }

    private void runApproveWithEventOnce() throws Exception {
        Agent support = buildHandoffAgent("e2e_java_handoff_approve_event");

        try (AgentStream stream = runtime.stream(support,
                "Please submit this configuration change: enable feature flag java_e2e_hitl.")) {

            int approvals = 0;
            for (AgentEvent event : stream) {
                if (event.getType() == EventType.WAITING) {
                    stream.approve(event);
                    approvals++;
                    assertTrue(approvals <= 5, "too many approval prompts; handoff did not settle");
                }
            }
            assertTrue(approvals > 0, "expected a WAITING event from the sub-agent's approval-required tool");

            // Poll the server-side workflow status instead of waiting on the
            // original SSE stream, which won't see the post-approve resume.
            AgentResult result = stream.waitForResult(180_000, 1_000);
            assertEquals(AgentStatus.COMPLETED, result.getStatus(),
                "workflow did not complete after approve(event). status=" + result.getStatus()
                + " error=" + result.getError());
        }
    }

    /**
     * {@link AgentStream#approve(AgentEvent)} must fail loud — not silently
     * fall back to the top-level execution — when handed an event that carries
     * no execution id.
     */
    @Test
    @Order(3)
    void test_approve_with_event_rejects_empty_execution_id() {
        Agent solo = Agent.builder()
            .name("e2e_java_handoff_guard")
            .model(MODEL)
            .instructions("Say hello.")
            .maxTurns(1)
            .build();

        try (AgentStream stream = runtime.stream(solo, "hi")) {
            for (AgentEvent ignored : stream) {
                // drain so the underlying workflow finishes cleanly
            }

            AgentEvent eventWithNoId = new AgentEvent(
                EventType.WAITING,
                /*content*/ null,
                /*toolName*/ "submit_change",
                /*args*/ null,
                /*result*/ null,
                /*output*/ null,
                /*executionId*/ "",
                /*guardrailName*/ null,
                /*target*/ null
            );

            IllegalArgumentException thrown = assertThrows(
                IllegalArgumentException.class,
                () -> stream.approve(eventWithNoId));

            assertNotNull(thrown.getMessage());
            assertTrue(thrown.getMessage().contains("execution id"),
                "exception should mention the missing execution id, got: " + thrown.getMessage());
        }
    }
}
