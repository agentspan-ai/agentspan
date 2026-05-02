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

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Suite 2: Tool Calling — agent execution with side-effect validation.
 *
 * <p>Tests verify that tools are actually called during execution by checking
 * a side-effect flag set inside the tool function body — not by parsing
 * LLM output text or inspecting workflow task names.
 *
 * <p>CLAUDE.md rule: no LLM for validation unless doing evals.
 * Side-effect assertion: tool function body must have executed.
 *
 * <p>The server names tool-call tasks as {@code call_{llm_call_id}__N}, not
 * by the tool name, so referenceTaskName-based assertions don't work.
 * The AtomicBoolean side-effect is the strongest counterfactual: if tool
 * registration or dispatch is broken the flag stays false.
 */
@Tag("e2e")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class E2eSuite2ToolCalling extends E2eBaseTest {

    private static AgentRuntime runtime;

    /** Set to true inside the add() tool body when the tool is actually invoked. */
    private static final AtomicBoolean toolWasCalled = new AtomicBoolean(false);

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
            // Side-effect: prove the tool function body actually ran.
            toolWasCalled.set(true);
            return a + b;
        }
    }

    // ── Tests ─────────────────────────────────────────────────────────────

    /**
     * Agent calls the 'add' tool and the tool function body executes.
     *
     * COUNTERFACTUAL: if tool registration is broken, the worker is never
     * invoked, toolWasCalled stays false, and the assertion fails.
     * If tool deserialization or dispatch breaks, the LLM either won't call
     * the tool or the worker won't be polled, and the flag stays false.
     */
    @Test
    @Order(1)
    @Timeout(value = 300, unit = TimeUnit.SECONDS)
    void test_agent_calls_worker_tool() {
        toolWasCalled.set(false); // reset before each run

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

        assertTrue(toolWasCalled.get(),
            "The 'add' tool function body was never called. "
            + "COUNTERFACTUAL: if tool registration or the tool dispatch is broken, "
            + "the worker is never invoked and this flag stays false.");
    }
}
