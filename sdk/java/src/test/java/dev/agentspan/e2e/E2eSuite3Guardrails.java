// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.e2e;

import dev.agentspan.Agent;
import dev.agentspan.AgentRuntime;
import dev.agentspan.enums.AgentStatus;
import dev.agentspan.enums.OnFail;
import dev.agentspan.enums.Position;
import dev.agentspan.model.AgentResult;
import dev.agentspan.model.GuardrailDef;
import dev.agentspan.model.GuardrailResult;
import org.junit.jupiter.api.*;

import java.util.List;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Suite 3: Guardrails — runtime behavior tests.
 *
 * <p>Tests verify that guardrails actually fire during execution by checking
 * that the agent fails/terminates when guardrails block it.
 *
 * <p>COUNTERFACTUAL: if the guardrail doesn't fire, the agent completes normally
 * and the assertion for FAILED/TERMINATED status fails.
 *
 * <p>Both tests use a custom function guardrail whose worker always returns
 * passed=false. This is the most reliable counterfactual because:
 * <ul>
 *   <li>If the guardrail worker is never called, the agent completes (assertion fails).</li>
 *   <li>If the guardrail fires, the agent fails/terminates (assertion passes).</li>
 * </ul>
 * Regex guardrails run server-side; their blocking behaviour for INPUT+RAISE is
 * not consistently implemented across server versions, so custom guardrails are
 * used here for deterministic assertions.
 */
@Tag("e2e")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class E2eSuite3Guardrails extends E2eBaseTest {

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
     * Custom OUTPUT guardrail with maxRetries=1 that always fails escalates
     * from RETRY to RAISE and terminates the agent.
     *
     * COUNTERFACTUAL: if the guardrail worker is never called, the agent completes
     * normally (status == COMPLETED) and the assertion fails. If maxRetries
     * escalation doesn't work, the agent would loop forever (timeout) or complete.
     */
    @Test
    @Order(1)
    @Timeout(value = 300, unit = TimeUnit.SECONDS)
    void test_custom_guardrail_retry_escalation() {
        // A guardrail that always fails with RETRY and maxRetries=1.
        // After 1 retry the runtime escalates to RAISE, blocking the agent.
        GuardrailDef escalatingGuardrail = GuardrailDef.builder()
            .name("e2e_escalate_guard")
            .position(Position.OUTPUT)
            .onFail(OnFail.RETRY)
            .maxRetries(1)
            .func(content -> GuardrailResult.fail("always fails for escalation test"))
            .guardrailType("custom")
            .build();

        Agent agent = Agent.builder()
            .name("e2e_java_escalate_guard_agent")
            .model(MODEL)
            .instructions("Say hello.")
            .guardrails(List.of(escalatingGuardrail))
            .maxTurns(3)
            .build();

        AgentResult result = runtime.run(agent, "Say anything.");

        // After maxRetries=1 is exceeded the guardrail escalates to RAISE
        // which should cause the agent to fail or terminate
        assertTrue(
            result.getStatus() == AgentStatus.FAILED || result.getStatus() == AgentStatus.TERMINATED,
            "Expected agent to FAIL or TERMINATE after guardrail maxRetries=1 escalation. "
            + "Got status: " + result.getStatus()
            + ". COUNTERFACTUAL: if the custom guardrail doesn't fire, agent completes normally."
        );
    }

    /**
     * Custom OUTPUT guardrail that always returns passed=false (RAISE) blocks the agent.
     *
     * COUNTERFACTUAL: if the custom guardrail doesn't fire, agent completes
     * normally and the assertion fails.
     */
    @Test
    @Order(2)
    @Timeout(value = 300, unit = TimeUnit.SECONDS)
    void test_custom_guardrail_raise_on_output() {
        // A guardrail that always blocks output
        GuardrailDef alwaysBlockGuardrail = GuardrailDef.builder()
            .name("e2e_always_block_guard")
            .position(Position.OUTPUT)
            .onFail(OnFail.RAISE)
            .func(content -> GuardrailResult.fail("blocked by e2e test guardrail"))
            .guardrailType("custom")
            .build();

        Agent agent = Agent.builder()
            .name("e2e_java_custom_guard_agent")
            .model(MODEL)
            .instructions("Say hello.")
            .guardrails(List.of(alwaysBlockGuardrail))
            .maxTurns(3)
            .build();

        AgentResult result = runtime.run(agent, "Say anything.");

        // The always-blocking guardrail should cause the agent to fail or terminate
        assertTrue(
            result.getStatus() == AgentStatus.FAILED || result.getStatus() == AgentStatus.TERMINATED,
            "Expected agent to FAIL or TERMINATE when custom guardrail always blocks. "
            + "Got status: " + result.getStatus()
            + ". COUNTERFACTUAL: if the custom guardrail doesn't fire, agent completes normally."
        );
    }
}
