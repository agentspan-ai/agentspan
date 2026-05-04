// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.e2e;

import ai.agentspan.Agent;
import ai.agentspan.AgentRuntime;
import ai.agentspan.CallbackHandler;
import ai.agentspan.enums.AgentStatus;
import ai.agentspan.model.AgentResult;
import org.junit.jupiter.api.*;

import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Suite 7: Callbacks — CallbackHandler lifecycle hook tests.
 *
 * <p>Callback positions are serialized into agentDef.callbacks and handled by
 * the server at runtime. Tests verify:
 * <ol>
 *   <li>Serialization: callback positions appear in the compiled agentDef.</li>
 *   <li>Non-interference: registering callbacks does not break agent execution.</li>
 *   <li>Multiple handlers: combining callbacks from several handler instances works.</li>
 * </ol>
 *
 * <p>COUNTERFACTUAL:
 * <ul>
 *   <li>Compile tests fail if serialization breaks (wrong/missing positions).</li>
 *   <li>Runtime tests fail if callbacks block execution (status != COMPLETED).</li>
 * </ul>
 */
@Tag("e2e")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
@Timeout(value = 300, unit = TimeUnit.SECONDS)
class E2eSuite7Callbacks extends E2eBaseTest {

    private static AgentRuntime runtime;

    @BeforeAll
    static void setup() {
        runtime = new AgentRuntime(new ai.agentspan.AgentConfig(BASE_URL, null, null, 100, 1));
    }

    @AfterAll
    static void teardown() {
        if (runtime != null) runtime.close();
    }

    // ── Callback handler implementations ─────────────────────────────────

    /** Overrides onAgentStart and onAgentEnd only. */
    static class AgentLifecycleHandler extends CallbackHandler {
        @Override
        public Map<String, Object> onAgentStart(Map<String, Object> kwargs) {
            return null;
        }

        @Override
        public Map<String, Object> onAgentEnd(Map<String, Object> kwargs) {
            return null;
        }
    }

    /** Overrides onModelStart and onModelEnd only. */
    static class ModelLifecycleHandler extends CallbackHandler {
        @Override
        public Map<String, Object> onModelStart(Map<String, Object> kwargs) {
            return null;
        }

        @Override
        public Map<String, Object> onModelEnd(Map<String, Object> kwargs) {
            return null;
        }
    }

    /** Overrides onToolStart and onToolEnd only. */
    static class ToolLifecycleHandler extends CallbackHandler {
        @Override
        public Map<String, Object> onToolStart(Map<String, Object> kwargs) {
            return null;
        }

        @Override
        public Map<String, Object> onToolEnd(Map<String, Object> kwargs) {
            return null;
        }
    }

    /** Overrides all 6 lifecycle methods. */
    static class AllHooksHandler extends CallbackHandler {
        @Override
        public Map<String, Object> onAgentStart(Map<String, Object> kwargs) { return null; }
        @Override
        public Map<String, Object> onAgentEnd(Map<String, Object> kwargs) { return null; }
        @Override
        public Map<String, Object> onModelStart(Map<String, Object> kwargs) { return null; }
        @Override
        public Map<String, Object> onModelEnd(Map<String, Object> kwargs) { return null; }
        @Override
        public Map<String, Object> onToolStart(Map<String, Object> kwargs) { return null; }
        @Override
        public Map<String, Object> onToolEnd(Map<String, Object> kwargs) { return null; }
    }

    // ── Tests ─────────────────────────────────────────────────────────────

    /**
     * Plan-level: callback positions for overridden methods appear in agentDef.callbacks.
     *
     * <p>AgentLifecycleHandler overrides onAgentStart and onAgentEnd.
     * The serializer emits before_agent and after_agent positions.
     *
     * COUNTERFACTUAL: if CallbackHandler reflection-based serialization is broken,
     * the 'callbacks' key will be absent or empty → assertion fails.
     */
    @Test
    @Order(1)
    @SuppressWarnings("unchecked")
    void test_agent_callbacks_compile() {
        Agent agent = Agent.builder()
            .name("e2e_java_agent_cb_compile")
            .model(MODEL)
            .instructions("You are a test agent.")
            .callbacks(new AgentLifecycleHandler())
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        List<Map<String, Object>> callbacks = (List<Map<String, Object>>) agentDef.get("callbacks");
        assertNotNull(callbacks,
            "agentDef has no 'callbacks' key — CallbackHandler serialization is broken. "
            + "agentDef keys: " + agentDef.keySet());
        assertFalse(callbacks.isEmpty(),
            "agentDef.callbacks is empty — no callback positions serialized");

        List<String> positions = callbacks.stream()
            .map(c -> (String) c.get("position"))
            .collect(Collectors.toList());

        assertTrue(positions.contains("before_agent"),
            "Expected 'before_agent' in agentDef.callbacks positions. Found: " + positions
            + ". COUNTERFACTUAL: if onAgentStart is not detected as an override, "
            + "'before_agent' won't be serialized.");
        assertTrue(positions.contains("after_agent"),
            "Expected 'after_agent' in agentDef.callbacks positions. Found: " + positions
            + ". COUNTERFACTUAL: if onAgentEnd is not detected as an override, "
            + "'after_agent' won't be serialized.");

        // Verify taskName pattern: {agentName}_{position}
        Map<String, String> positionToTask = new java.util.HashMap<>();
        for (Map<String, Object> cb : callbacks) {
            positionToTask.put((String) cb.get("position"), (String) cb.get("taskName"));
        }
        assertEquals("e2e_java_agent_cb_compile_before_agent",
            positionToTask.get("before_agent"),
            "Expected taskName 'e2e_java_agent_cb_compile_before_agent'. "
            + "Got: " + positionToTask.get("before_agent"));
        assertEquals("e2e_java_agent_cb_compile_after_agent",
            positionToTask.get("after_agent"),
            "Expected taskName 'e2e_java_agent_cb_compile_after_agent'. "
            + "Got: " + positionToTask.get("after_agent"));
    }

    /**
     * Plan-level: model-lifecycle callback positions appear in agentDef.callbacks.
     *
     * COUNTERFACTUAL: if before_model/after_model serialization is broken → assertion fails.
     */
    @Test
    @Order(2)
    @SuppressWarnings("unchecked")
    void test_model_callbacks_compile() {
        Agent agent = Agent.builder()
            .name("e2e_java_model_cb_compile")
            .model(MODEL)
            .instructions("You are a test agent.")
            .callbacks(new ModelLifecycleHandler())
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        List<Map<String, Object>> callbacks = (List<Map<String, Object>>) agentDef.get("callbacks");
        assertNotNull(callbacks,
            "agentDef has no 'callbacks' key — ModelLifecycleHandler serialization broken");
        assertFalse(callbacks.isEmpty(),
            "agentDef.callbacks is empty — no model callbacks serialized");

        List<String> positions = callbacks.stream()
            .map(c -> (String) c.get("position"))
            .collect(Collectors.toList());

        assertTrue(positions.contains("before_model"),
            "Expected 'before_model' in agentDef.callbacks positions. Found: " + positions
            + ". COUNTERFACTUAL: onModelStart not detected as override.");
        assertTrue(positions.contains("after_model"),
            "Expected 'after_model' in agentDef.callbacks positions. Found: " + positions
            + ". COUNTERFACTUAL: onModelEnd not detected as override.");
    }

    /**
     * Plan-level: all 6 callback positions appear in agentDef.callbacks when all
     * hooks are overridden.
     *
     * COUNTERFACTUAL: if any position is missing → assertion fails.
     */
    @Test
    @Order(3)
    @SuppressWarnings("unchecked")
    void test_all_hooks_compile() {
        Agent agent = Agent.builder()
            .name("e2e_java_all_hooks_compile")
            .model(MODEL)
            .instructions("You are a test agent.")
            .callbacks(new AllHooksHandler())
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        List<Map<String, Object>> callbacks = (List<Map<String, Object>>) agentDef.get("callbacks");
        assertNotNull(callbacks,
            "agentDef has no 'callbacks' key — AllHooksHandler serialization broken");

        List<String> positions = callbacks.stream()
            .map(c -> (String) c.get("position"))
            .collect(Collectors.toList());

        for (String expected : List.of("before_agent", "after_agent",
                                       "before_model", "after_model",
                                       "before_tool",  "after_tool")) {
            assertTrue(positions.contains(expected),
                "Expected '" + expected + "' in agentDef.callbacks positions. Found: " + positions
                + ". COUNTERFACTUAL: if the override detection fails for this hook, "
                + "the position won't appear.");
        }
        assertEquals(6, positions.size(),
            "Expected exactly 6 callback positions, got " + positions.size()
            + ". Positions: " + positions
            + ". COUNTERFACTUAL: if duplicate positions are emitted or some are missing, count != 6.");
    }

    /**
     * Runtime: registering agent-lifecycle callbacks (before_agent, after_agent) does
     * not block or break agent execution.
     *
     * COUNTERFACTUAL: if any callback incorrectly raises an exception or blocks the
     * workflow, the agent will not COMPLETE → status assertion fails.
     */
    @Test
    @Order(4)
    @Timeout(value = 300, unit = TimeUnit.SECONDS)
    void test_agent_callbacks_dont_block_execution() {
        Agent agent = Agent.builder()
            .name("e2e_java_agent_cb_runtime")
            .model(MODEL)
            .instructions("Say hello in one sentence.")
            .callbacks(new AgentLifecycleHandler())
            .maxTurns(2)
            .build();

        AgentResult result = runtime.run(agent, "Say hello.");

        assertEquals(AgentStatus.COMPLETED, result.getStatus(),
            "Agent with agent-lifecycle callbacks should complete normally. "
            + "Status: " + result.getStatus()
            + ". Error: " + result.getError()
            + ". COUNTERFACTUAL: if callbacks block execution, status != COMPLETED.");
    }

    /**
     * Runtime: registering model-lifecycle callbacks (before_model, after_model) does
     * not block or break agent execution.
     *
     * COUNTERFACTUAL: if any callback incorrectly raises an exception or blocks the
     * workflow, the agent will not COMPLETE → status assertion fails.
     */
    @Test
    @Order(5)
    @Timeout(value = 300, unit = TimeUnit.SECONDS)
    void test_model_callbacks_dont_block_execution() {
        Agent agent = Agent.builder()
            .name("e2e_java_model_cb_runtime")
            .model(MODEL)
            .instructions("Say hello in one sentence.")
            .callbacks(new ModelLifecycleHandler())
            .maxTurns(2)
            .build();

        AgentResult result = runtime.run(agent, "Say hello.");

        assertEquals(AgentStatus.COMPLETED, result.getStatus(),
            "Agent with model-lifecycle callbacks should complete normally. "
            + "Status: " + result.getStatus()
            + ". Error: " + result.getError()
            + ". COUNTERFACTUAL: if callbacks block execution, status != COMPLETED.");
    }

    /**
     * Runtime: all 6 callback hooks registered simultaneously do not block execution.
     *
     * COUNTERFACTUAL: if any combination of callbacks causes interference or
     * serialization conflict, the agent will fail → status assertion fails.
     */
    @Test
    @Order(6)
    @Timeout(value = 300, unit = TimeUnit.SECONDS)
    void test_all_callbacks_dont_block_execution() {
        Agent agent = Agent.builder()
            .name("e2e_java_all_cb_runtime")
            .model(MODEL)
            .instructions("Say hello in one sentence.")
            .callbacks(new AllHooksHandler())
            .maxTurns(2)
            .build();

        AgentResult result = runtime.run(agent, "Say hello.");

        assertEquals(AgentStatus.COMPLETED, result.getStatus(),
            "Agent with all 6 callback hooks registered should complete normally. "
            + "Status: " + result.getStatus()
            + ". Error: " + result.getError()
            + ". COUNTERFACTUAL: if any callback hook combination blocks, status != COMPLETED.");
    }
}
