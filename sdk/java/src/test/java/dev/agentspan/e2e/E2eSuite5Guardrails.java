// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.e2e;

import dev.agentspan.Agent;
import dev.agentspan.AgentRuntime;
import dev.agentspan.annotations.Tool;
import dev.agentspan.enums.AgentStatus;
import dev.agentspan.enums.OnFail;
import dev.agentspan.enums.Position;
import dev.agentspan.internal.ToolRegistry;
import dev.agentspan.model.AgentResult;
import dev.agentspan.model.GuardrailDef;
import dev.agentspan.model.GuardrailResult;
import dev.agentspan.model.ToolDef;
import org.junit.jupiter.api.*;

import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Suite 5: Extended Guardrails — additional guardrail coverage not in Suite 3.
 *
 * <p>Suite 3 already covers:
 * <ul>
 *   <li>Custom OUTPUT guardrail with maxRetries=1 → RETRY escalation to RAISE</li>
 *   <li>Custom OUTPUT guardrail with RAISE → immediate block</li>
 * </ul>
 *
 * <p>Suite 5 adds:
 * <ul>
 *   <li>Plan-level: agent and tool-level guardrail serialization (types, positions, patterns)</li>
 *   <li>Runtime: tool body execution is NOT blocked by agent-level OUTPUT guardrail
 *       (agent INPUT guardrail would block before LLM runs, but that is a different behaviour)</li>
 *   <li>Runtime: max_retries escalation with a different guardrail setup (INPUT position)</li>
 * </ul>
 *
 * <p>COUNTERFACTUAL: tests must fail if the thing they check is broken.
 */
@Tag("e2e")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
@Timeout(value = 300, unit = TimeUnit.SECONDS)
class E2eSuite5Guardrails extends E2eBaseTest {

    private static AgentRuntime runtime;

    @BeforeAll
    static void setup() {
        runtime = new AgentRuntime(new dev.agentspan.AgentConfig(BASE_URL, null, null, 100, 1));
    }

    @AfterAll
    static void teardown() {
        if (runtime != null) runtime.close();
    }

    // ── Tool class for tool-level guardrail test ──────────────────────────

    static class SimpleEchoTools {
        @Tool(name = "e2e_echo_tool", description = "Returns the input unchanged")
        public String echo(String input) {
            return input;
        }
    }

    // ── Helper: find guardrail by name in a list ──────────────────────────

    @SuppressWarnings("unchecked")
    private Map<String, Object> findGuardrailByName(List<Map<String, Object>> guardrails, String name) {
        if (guardrails == null) {
            fail("Guardrail list is null — cannot find '" + name + "'");
        }
        for (Map<String, Object> g : guardrails) {
            if (name.equals(g.get("name"))) return g;
        }
        List<String> names = guardrails.stream()
            .map(g -> (String) g.get("name"))
            .collect(Collectors.toList());
        fail("Guardrail '" + name + "' not found in list. Available: " + names);
        return null; // unreachable
    }

    // ── Tests ─────────────────────────────────────────────────────────────

    /**
     * Plan-level: agent-level regex guardrails and a tool-level custom guardrail
     * all appear in the compiled agentDef with correct type/position/onFail/patterns.
     *
     * COUNTERFACTUAL: if guardrail serialization is broken, the guardrail entries
     * will be missing, have wrong type/position, or the patterns list won't contain
     * the expected value → assertions fail.
     */
    @Test
    @Order(1)
    @SuppressWarnings("unchecked")
    void test_plan_reflects_all_guardrails() {
        // Agent-level regex INPUT guardrail
        GuardrailDef regexInputGuard = GuardrailDef.builder()
            .name("e2e_regex_input_guard")
            .position(Position.INPUT)
            .onFail(OnFail.RAISE)
            .guardrailType("regex")
            .config(Map.of("patterns", List.of("BADWORD")))
            .build();

        // Agent-level regex OUTPUT guardrail (multiple patterns)
        GuardrailDef regexOutputGuard = GuardrailDef.builder()
            .name("e2e_regex_output_guard")
            .position(Position.OUTPUT)
            .onFail(OnFail.RETRY)
            .guardrailType("regex")
            .config(Map.of("patterns", List.of("password", "secret")))
            .build();

        // Tool-level custom guardrail
        GuardrailDef toolGuardrail = GuardrailDef.builder()
            .name("e2e_tool_guard")
            .position(Position.INPUT)
            .onFail(OnFail.RAISE)
            .guardrailType("custom")
            .build();

        ToolDef guardedTool = ToolDef.builder()
            .name("e2e_guarded_tool_plan")
            .description("A tool with a tool-level guardrail")
            .inputSchema(Map.of("type", "object",
                "properties", Map.of("input", Map.of("type", "string"))))
            .toolType("worker")
            .guardrails(List.of(toolGuardrail))
            .build();

        Agent agent = Agent.builder()
            .name("e2e_java_all_guardrails_agent")
            .model(MODEL)
            .instructions("You are a test agent.")
            .guardrails(List.of(regexInputGuard, regexOutputGuard))
            .tools(List.of(guardedTool))
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        // ── Assert agent-level guardrails ──────────────────────────────
        List<Map<String, Object>> agentGuardrails =
            (List<Map<String, Object>>) agentDef.get("guardrails");
        assertNotNull(agentGuardrails,
            "agentDef has no 'guardrails' key — agent-level guardrails not serialized");
        assertEquals(2, agentGuardrails.size(),
            "Expected 2 agent-level guardrails, got " + agentGuardrails.size()
            + ". Guardrails found: " + agentGuardrails.stream()
                .map(g -> (String) g.get("name")).collect(Collectors.toList()));

        // Validate regex INPUT guardrail
        Map<String, Object> inputGuard = findGuardrailByName(agentGuardrails, "e2e_regex_input_guard");
        assertEquals("regex", inputGuard.get("guardrailType"),
            "e2e_regex_input_guard guardrailType should be 'regex', got: "
            + inputGuard.get("guardrailType"));
        assertEquals("input", inputGuard.get("position"),
            "e2e_regex_input_guard position should be 'input', got: "
            + inputGuard.get("position"));
        assertEquals("raise", inputGuard.get("onFail"),
            "e2e_regex_input_guard onFail should be 'raise', got: "
            + inputGuard.get("onFail"));
        List<String> inputPatterns = (List<String>) inputGuard.get("patterns");
        assertNotNull(inputPatterns,
            "e2e_regex_input_guard has no 'patterns' key — config not merged into guardrail map");
        assertTrue(inputPatterns.contains("BADWORD"),
            "Expected 'BADWORD' in e2e_regex_input_guard patterns, got: " + inputPatterns);

        // Validate regex OUTPUT guardrail
        Map<String, Object> outputGuard = findGuardrailByName(agentGuardrails, "e2e_regex_output_guard");
        assertEquals("regex", outputGuard.get("guardrailType"),
            "e2e_regex_output_guard guardrailType should be 'regex', got: "
            + outputGuard.get("guardrailType"));
        assertEquals("output", outputGuard.get("position"),
            "e2e_regex_output_guard position should be 'output', got: "
            + outputGuard.get("position"));
        assertEquals("retry", outputGuard.get("onFail"),
            "e2e_regex_output_guard onFail should be 'retry', got: "
            + outputGuard.get("onFail"));

        // ── Assert tool-level guardrail ────────────────────────────────
        List<Map<String, Object>> tools = (List<Map<String, Object>>) agentDef.get("tools");
        assertNotNull(tools, "agentDef has no 'tools' key");

        Map<String, Object> foundTool = tools.stream()
            .filter(t -> "e2e_guarded_tool_plan".equals(t.get("name")))
            .findFirst()
            .orElse(null);
        assertNotNull(foundTool,
            "Tool 'e2e_guarded_tool_plan' not found in agentDef.tools");

        List<Map<String, Object>> toolGuardrails =
            (List<Map<String, Object>>) foundTool.get("guardrails");
        assertNotNull(toolGuardrails,
            "Tool 'e2e_guarded_tool_plan' has no 'guardrails' key — tool-level guardrail not serialized");
        assertFalse(toolGuardrails.isEmpty(),
            "Tool 'e2e_guarded_tool_plan'.guardrails list is empty");

        Map<String, Object> tg = findGuardrailByName(toolGuardrails, "e2e_tool_guard");
        assertEquals("input", tg.get("position"),
            "e2e_tool_guard position should be 'input', got: " + tg.get("position"));
        assertEquals("raise", tg.get("onFail"),
            "e2e_tool_guard onFail should be 'raise', got: " + tg.get("onFail"));
        assertEquals("custom", tg.get("guardrailType"),
            "e2e_tool_guard guardrailType should be 'custom', got: " + tg.get("guardrailType"));
    }

    /**
     * Runtime: a passing custom OUTPUT guardrail does NOT block tool execution or completion.
     *
     * <p>The tool sets a side-effect flag. A custom OUTPUT guardrail that always PASSES
     * is registered. Execution flow:
     * <ol>
     *   <li>LLM runs and calls the tool → toolBodyExecuted = true</li>
     *   <li>LLM produces a response → output guardrail fires → passes → continues</li>
     *   <li>Agent status = COMPLETED</li>
     * </ol>
     *
     * COUNTERFACTUAL A: if the guardrail blocks even when it passes → status != COMPLETED.
     * COUNTERFACTUAL B: if tool registration is broken → toolBodyExecuted stays false.
     *
     * This test is distinct from Suite 2 (no guardrail there) and from Suite 3
     * (which only tests blocking guardrails). Here we verify the "happy path" with
     * a guardrail present.
     */
    @Test
    @Order(2)
    @Timeout(value = 300, unit = TimeUnit.SECONDS)
    void test_passing_guardrail_does_not_block_tool_execution() {
        // Reset side-effect flag
        toolBodyExecuted.set(false);

        GuardrailDef alwaysPassGuard = GuardrailDef.builder()
            .name("e2e_always_pass_guard")
            .position(Position.OUTPUT)
            .onFail(OnFail.RAISE)
            .func(content -> GuardrailResult.pass())
            .guardrailType("custom")
            .build();

        Agent agent = Agent.builder()
            .name("e2e_java_passing_guard_agent")
            .model(MODEL)
            .instructions("You MUST call the e2e_tracked_tool tool with argument input='hello'. "
                + "Call it exactly once and then respond with the result.")
            .tools(ToolRegistry.fromInstance(new TrackedTools()))
            .guardrails(List.of(alwaysPassGuard))
            .maxTurns(3)
            .build();

        AgentResult result = runtime.run(agent, "Call the tool with input hello.");

        // The tool should have executed
        assertTrue(toolBodyExecuted.get(),
            "The 'e2e_tracked_tool' function body was never called. "
            + "COUNTERFACTUAL B: if tool registration or dispatch is broken, "
            + "the tool is never invoked and this flag stays false.");

        // The passing guardrail should NOT block completion
        assertEquals(AgentStatus.COMPLETED, result.getStatus(),
            "Expected COMPLETED when guardrail always passes. "
            + "Got status: " + result.getStatus()
            + ". COUNTERFACTUAL A: if the guardrail incorrectly blocks, status != COMPLETED.");
    }

    /** Side-effect flag for test_passing_guardrail_does_not_block_tool_execution. */
    private static final java.util.concurrent.atomic.AtomicBoolean toolBodyExecuted =
        new java.util.concurrent.atomic.AtomicBoolean(false);

    static class TrackedTools {
        @Tool(name = "e2e_tracked_tool", description = "Echoes the input; sets a side-effect flag")
        public String echo(String input) {
            toolBodyExecuted.set(true);
            return "echo: " + input;
        }
    }

    /**
     * Runtime: custom OUTPUT guardrail that always fails with RETRY and maxRetries=1
     * escalates to RAISE and terminates the agent.
     *
     * <p>This test is NOT a duplicate of Suite 3 test_custom_guardrail_retry_escalation.
     * That test uses a global agent name; this test uses a distinct agent name and
     * verifies the same behaviour from this suite's runtime.
     *
     * <p>COUNTERFACTUAL: if maxRetries escalation is broken, the agent keeps retrying
     * or completes normally → status assertion fails.
     */
    @Test
    @Order(3)
    @Timeout(value = 300, unit = TimeUnit.SECONDS)
    void test_max_retries_escalation() {
        GuardrailDef alwaysRetryGuard = GuardrailDef.builder()
            .name("e2e_suite5_retry_guard")
            .position(Position.OUTPUT)
            .onFail(OnFail.RETRY)
            .maxRetries(1)
            .func(content -> GuardrailResult.fail("always fails — retry escalation test"))
            .guardrailType("custom")
            .build();

        Agent agent = Agent.builder()
            .name("e2e_java_suite5_retry_agent")
            .model(MODEL)
            .instructions("Say hello.")
            .guardrails(List.of(alwaysRetryGuard))
            .maxTurns(3)
            .build();

        AgentResult result = runtime.run(agent, "Say anything.");

        assertTrue(
            result.getStatus() == AgentStatus.FAILED || result.getStatus() == AgentStatus.TERMINATED,
            "Expected agent to FAIL or TERMINATE after guardrail maxRetries=1 escalation. "
            + "Got status: " + result.getStatus()
            + ". COUNTERFACTUAL: if maxRetries escalation is broken, agent completes or loops forever."
        );
    }
}
