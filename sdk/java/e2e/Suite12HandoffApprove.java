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
    public static class DatabaseTools {
        @Tool(
            name = "execute_sql",
            description = "Execute a SQL statement that modifies the database",
            approvalRequired = true
        )
        public String executeSql(String statement) {
            return "Statement executed.";
        }
    }

    private Agent buildHandoffAgent(String name) {
        List<ToolDef> dbTools = ToolRegistry.fromInstance(new DatabaseTools());

        Agent dba = Agent.builder()
            .name(name + "_dba")
            .model(MODEL)
            .instructions("You run database statements. Use execute_sql when asked.")
            .tools(dbTools)
            .build();

        return Agent.builder()
            .name(name)
            .model(MODEL)
            .instructions("Route any database task to the dba sub-agent.")
            .agents(dba)
            .strategy(Strategy.HANDOFF)
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
                "Please run: UPDATE users SET active = true WHERE id = 1")) {

            String topExecutionId = stream.getExecutionId();
            assertNotNull(topExecutionId);
            assertFalse(topExecutionId.isEmpty());

            AgentEvent waiting = null;
            for (AgentEvent event : stream) {
                if (event.getType() == EventType.WAITING) {
                    waiting = event;
                    stream.approve(event); // let the run terminate so we don't leak server state
                    break;
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
     */
    @Test
    @Order(2)
    @Timeout(value = 300, unit = TimeUnit.SECONDS)
    void test_approve_with_event_completes_handoff_hitl() {
        Agent support = buildHandoffAgent("e2e_java_handoff_approve_event");

        try (AgentStream stream = runtime.stream(support,
                "Please run: UPDATE users SET active = true WHERE id = 1")) {

            boolean approved = false;
            for (AgentEvent event : stream) {
                if (event.getType() == EventType.WAITING) {
                    stream.approve(event);
                    approved = true;
                    break;
                }
            }
            assertTrue(approved, "expected a WAITING event from the sub-agent's approval-required tool");

            AgentResult result = stream.getResult();
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
                /*toolName*/ "execute_sql",
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
