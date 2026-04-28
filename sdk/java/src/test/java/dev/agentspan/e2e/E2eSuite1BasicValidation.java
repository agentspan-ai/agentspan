// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.e2e;

import dev.agentspan.Agent;
import dev.agentspan.AgentRuntime;
import dev.agentspan.annotations.Tool;
import dev.agentspan.enums.OnFail;
import dev.agentspan.enums.Position;
import dev.agentspan.enums.Strategy;
import dev.agentspan.internal.ToolRegistry;
import dev.agentspan.model.GuardrailDef;
import dev.agentspan.model.GuardrailResult;
import dev.agentspan.tools.HttpTool;
import org.junit.jupiter.api.*;

import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Suite 1: Basic validation — plan() structural assertions.
 *
 * <p>All tests compile agents via plan() and assert on the Conductor workflow
 * JSON structure. No agent execution. Deterministic — no LLM calls.
 *
 * <p>CRITICAL: Tests are COUNTERFACTUAL — they must fail if there is a bug.
 */
@Tag("e2e")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class E2eSuite1BasicValidation extends E2eBaseTest {

    private static AgentRuntime runtime;

    @BeforeAll
    static void setup() {
        // Note: checkServerHealth() from E2eBaseTest runs before setup().
        // Use BASE_URL (without /api suffix) since AgentConfig + HttpApi
        // already prepend /api to every path.
        runtime = new AgentRuntime(new dev.agentspan.AgentConfig(BASE_URL, null, null, 100, 1));
    }

    @AfterAll
    static void teardown() {
        if (runtime != null) runtime.close();
    }

    // ── Tool classes for tests ────────────────────────────────────────────

    static class MathAndGreetTools {
        @Tool(name = "e2e_add", description = "Add two numbers")
        public int add(int a, int b) {
            return a + b;
        }

        @Tool(name = "e2e_greet", description = "Greet someone by name")
        public String greet(String name) {
            return "Hello, " + name + "!";
        }
    }

    static class CredentialedTools {
        @Tool(name = "e2e_cred_tool", description = "A tool needing credentials")
        public String credTool(String input) {
            return input;
        }
    }

    // ── Helper methods ────────────────────────────────────────────────────

    @SuppressWarnings("unchecked")
    private List<String> getToolNames(Map<String, Object> agentDef) {
        List<Map<String, Object>> tools = (List<Map<String, Object>>) agentDef.get("tools");
        if (tools == null) return List.of();
        return tools.stream()
            .map(t -> (String) t.get("name"))
            .collect(Collectors.toList());
    }

    @SuppressWarnings("unchecked")
    private Map<String, String> getToolTypes(Map<String, Object> agentDef) {
        List<Map<String, Object>> tools = (List<Map<String, Object>>) agentDef.get("tools");
        if (tools == null) return Map.of();
        Map<String, String> result = new HashMap<>();
        for (Map<String, Object> t : tools) {
            result.put((String) t.get("name"), (String) t.get("toolType"));
        }
        return result;
    }

    @SuppressWarnings("unchecked")
    private List<String> getGuardrailNames(Map<String, Object> agentDef) {
        List<Map<String, Object>> guardrails = (List<Map<String, Object>>) agentDef.get("guardrails");
        if (guardrails == null) return List.of();
        return guardrails.stream()
            .map(g -> (String) g.get("name"))
            .collect(Collectors.toList());
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> findGuardrailByName(Map<String, Object> agentDef, String name) {
        List<Map<String, Object>> guardrails = (List<Map<String, Object>>) agentDef.get("guardrails");
        if (guardrails == null) {
            fail("agentDef has no 'guardrails' key");
        }
        for (Map<String, Object> g : guardrails) {
            if (name.equals(g.get("name"))) return g;
        }
        fail("Guardrail '" + name + "' not found. Available: " + getGuardrailNames(agentDef));
        return null; // unreachable
    }

    @SuppressWarnings("unchecked")
    private List<String> getSubAgentNames(Map<String, Object> agentDef) {
        List<Map<String, Object>> agents = (List<Map<String, Object>>) agentDef.get("agents");
        if (agents == null) return List.of();
        return agents.stream()
            .map(a -> (String) a.get("name"))
            .collect(Collectors.toList());
    }

    // ── Tests ─────────────────────────────────────────────────────────────

    /**
     * Smoke test: agent with 2 tools compiles to a valid workflow.
     *
     * COUNTERFACTUAL: if tool serialization breaks, tool names won't be in agentDef.tools.
     */
    @Test
    @Order(1)
    void test_smoke_simple_agent_plan() {
        Agent agent = Agent.builder()
            .name("e2e_java_smoke")
            .model(MODEL)
            .instructions("You are a calculator.")
            .tools(ToolRegistry.fromInstance(new MathAndGreetTools()))
            .build();

        Map<String, Object> plan = runtime.plan(agent);

        assertTrue(plan.containsKey("workflowDef"),
            "plan() result missing 'workflowDef'. Got keys: " + plan.keySet());
        assertTrue(plan.containsKey("requiredWorkers"),
            "plan() result missing 'requiredWorkers'. Got keys: " + plan.keySet());

        Map<String, Object> agentDef = getAgentDef(plan);

        List<String> toolNames = getToolNames(agentDef);
        assertTrue(toolNames.contains("e2e_add"),
            "Tool 'e2e_add' not found in agentDef.tools. Found: " + toolNames);
        assertTrue(toolNames.contains("e2e_greet"),
            "Tool 'e2e_greet' not found in agentDef.tools. Found: " + toolNames);

        Map<String, String> toolTypes = getToolTypes(agentDef);
        assertEquals("worker", toolTypes.get("e2e_add"),
            "Tool 'e2e_add' has toolType='" + toolTypes.get("e2e_add") + "', expected 'worker'");
        assertEquals("worker", toolTypes.get("e2e_greet"),
            "Tool 'e2e_greet' has toolType='" + toolTypes.get("e2e_greet") + "', expected 'worker'");
    }

    /**
     * Guardrails appear in agentDef.guardrails with correct type/position/onFail.
     *
     * COUNTERFACTUAL: if guardrail serialization breaks, guardrails won't appear
     * or will have wrong types — test fails.
     */
    @Test
    @Order(2)
    void test_plan_reflects_guardrails() {
        // Custom (function) guardrail
        GuardrailDef customGuardrail = GuardrailDef.builder()
            .name("e2e_custom_guard")
            .position(Position.INPUT)
            .onFail(OnFail.RAISE)
            .func(content -> GuardrailResult.pass())
            .guardrailType("custom")
            .build();

        // Regex guardrail (using config map for patterns)
        GuardrailDef regexGuardrail = GuardrailDef.builder()
            .name("e2e_regex_guard")
            .position(Position.OUTPUT)
            .onFail(OnFail.RETRY)
            .guardrailType("regex")
            .config(Map.of("patterns", List.of("BLOCKED_PATTERN")))
            .build();

        Agent agent = Agent.builder()
            .name("e2e_java_guardrails")
            .model(MODEL)
            .instructions("You are a test agent.")
            .guardrails(List.of(customGuardrail, regexGuardrail))
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        @SuppressWarnings("unchecked")
        List<Map<String, Object>> guardrails = (List<Map<String, Object>>) agentDef.get("guardrails");
        assertNotNull(guardrails, "agentDef has no 'guardrails' key");
        assertEquals(2, guardrails.size(),
            "Expected 2 guardrails in agentDef.guardrails, got " + guardrails.size()
            + ". Names found: " + getGuardrailNames(agentDef));

        // Assert custom guardrail
        Map<String, Object> custom = findGuardrailByName(agentDef, "e2e_custom_guard");
        assertEquals("custom", custom.get("guardrailType"),
            "Guardrail 'e2e_custom_guard' has guardrailType='" + custom.get("guardrailType")
            + "', expected 'custom'");
        assertEquals("input", custom.get("position"),
            "Guardrail 'e2e_custom_guard' has position='" + custom.get("position")
            + "', expected 'input'");
        assertEquals("raise", custom.get("onFail"),
            "Guardrail 'e2e_custom_guard' has onFail='" + custom.get("onFail")
            + "', expected 'raise'");

        // Assert regex guardrail
        Map<String, Object> regex = findGuardrailByName(agentDef, "e2e_regex_guard");
        assertEquals("regex", regex.get("guardrailType"),
            "Guardrail 'e2e_regex_guard' has guardrailType='" + regex.get("guardrailType")
            + "', expected 'regex'");
        assertEquals("output", regex.get("position"),
            "Guardrail 'e2e_regex_guard' has position='" + regex.get("position")
            + "', expected 'output'");
        assertEquals("retry", regex.get("onFail"),
            "Guardrail 'e2e_regex_guard' has onFail='" + regex.get("onFail")
            + "', expected 'retry'");
    }

    /**
     * Tool credentials appear in agentDef.tools[].config.credentials.
     *
     * COUNTERFACTUAL: if credential serialization breaks, tool won't have credentials
     * at the right path.
     */
    @Test
    @Order(3)
    @SuppressWarnings("unchecked")
    void test_plan_reflects_credentials() {
        // Build tool with credentials using ToolRegistry + credential override via ToolDef
        dev.agentspan.model.ToolDef credTool = dev.agentspan.model.ToolDef.builder()
            .name("e2e_api_cred_tool")
            .description("Tool that needs API credentials")
            .inputSchema(Map.of("type", "object", "properties", Map.of()))
            .toolType("worker")
            .credentials(List.of("E2E_API_KEY"))
            .build();

        Agent agent = Agent.builder()
            .name("e2e_java_creds")
            .model(MODEL)
            .instructions("Use tools.")
            .tools(List.of(credTool))
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        List<Map<String, Object>> tools = (List<Map<String, Object>>) agentDef.get("tools");
        assertNotNull(tools, "agentDef has no 'tools' key");

        Map<String, Object> foundTool = tools.stream()
            .filter(t -> "e2e_api_cred_tool".equals(t.get("name")))
            .findFirst()
            .orElse(null);
        assertNotNull(foundTool,
            "Tool 'e2e_api_cred_tool' not found in agentDef.tools. "
            + "Tool credentials not serialized to agentDef");

        Map<String, Object> config = (Map<String, Object>) foundTool.get("config");
        assertNotNull(config,
            "Tool 'e2e_api_cred_tool' has no 'config' key. "
            + "Tool credentials not serialized to agentDef");

        List<String> creds = (List<String>) config.get("credentials");
        assertNotNull(creds,
            "Tool 'e2e_api_cred_tool'.config has no 'credentials'. "
            + "Tool credentials not serialized to agentDef");
        assertTrue(creds.contains("E2E_API_KEY"),
            "Expected 'E2E_API_KEY' in tool credentials, got: " + creds);
    }

    /**
     * An agent with a sub-agent produces SUB_WORKFLOW tasks.
     *
     * COUNTERFACTUAL: if sub-agent serialization breaks, SUB_WORKFLOW won't appear
     * in workflow tasks.
     */
    @Test
    @Order(4)
    void test_plan_sub_agent_produces_sub_workflow() {
        Agent child = Agent.builder()
            .name("e2e_java_child")
            .model(MODEL)
            .instructions("You are a helper.")
            .build();
        Agent parent = Agent.builder()
            .name("e2e_java_parent")
            .model(MODEL)
            .instructions("Delegate to child.")
            .agents(child)
            .strategy(Strategy.HANDOFF)
            .build();

        Map<String, Object> plan = runtime.plan(parent);
        Map<String, Object> agentDef = getAgentDef(plan);

        List<String> subNames = getSubAgentNames(agentDef);
        assertTrue(subNames.contains("e2e_java_child"),
            "Sub-agent 'e2e_java_child' not in agentDef.agents. Found: " + subNames);

        assertEquals("handoff", agentDef.get("strategy"),
            "agentDef.strategy is '" + agentDef.get("strategy") + "', expected 'handoff'");

        // Assert SUB_WORKFLOW task exists in the compiled workflow
        @SuppressWarnings("unchecked")
        Map<String, Object> workflowDef = (Map<String, Object>) plan.get("workflowDef");
        List<Map<String, Object>> allTasks = allTasksFlat(workflowDef);
        boolean hasSubWorkflow = allTasks.stream()
            .anyMatch(t -> "SUB_WORKFLOW".equals(t.get("type")));
        assertTrue(hasSubWorkflow,
            "No SUB_WORKFLOW task in compiled workflow. "
            + "Task types found: " + allTasks.stream()
                .map(t -> (String) t.get("type")).collect(Collectors.toSet())
            + ". An agent with sub-agents should compile to SUB_WORKFLOW tasks.");
    }

    /**
     * All 8 strategy enum values serialize correctly.
     *
     * COUNTERFACTUAL: if any strategy enum serialization breaks, it won't match
     * the expected lowercase JSON value.
     */
    @Test
    @Order(5)
    @SuppressWarnings("unchecked")
    void test_plan_all_8_strategies() {
        // Create a router agent for the ROUTER strategy
        Agent routerLead = Agent.builder()
            .name("e2e_java_router_lead")
            .model(MODEL)
            .instructions("Route to the correct agent.")
            .build();

        // Build 8 sub-agents with every strategy, each having 2 sub-sub-agents
        Strategy[] strategies = {
            Strategy.HANDOFF, Strategy.SEQUENTIAL, Strategy.PARALLEL,
            Strategy.ROUTER, Strategy.ROUND_ROBIN, Strategy.RANDOM,
            Strategy.SWARM, Strategy.MANUAL
        };
        String[] strategyNames = {
            "handoff", "sequential", "parallel",
            "router", "round_robin", "random",
            "swarm", "manual"
        };

        List<Agent> subAgents = new java.util.ArrayList<>();
        for (int i = 0; i < strategies.length; i++) {
            Strategy strat = strategies[i];
            String stratName = strategyNames[i];
            Agent.Builder b = Agent.builder()
                .name("e2e_java_strat_" + stratName)
                .model(MODEL)
                .instructions("Agent with " + stratName + " strategy.")
                .agents(
                    Agent.builder().name("e2e_java_" + stratName + "_s1").model(MODEL).instructions("Sub1.").build(),
                    Agent.builder().name("e2e_java_" + stratName + "_s2").model(MODEL).instructions("Sub2.").build()
                )
                .strategy(strat);
            if (strat == Strategy.ROUTER) {
                b.router(routerLead);
            }
            subAgents.add(b.build());
        }

        Agent parent = Agent.builder()
            .name("e2e_java_all_strategies")
            .model(MODEL)
            .instructions("Top-level agent with all strategies as sub-agents.")
            .agents(subAgents.toArray(new Agent[0]))
            .strategy(Strategy.HANDOFF)
            .build();

        Map<String, Object> plan = runtime.plan(parent);
        Map<String, Object> agentDef = getAgentDef(plan);

        List<Map<String, Object>> compiledAgents = (List<Map<String, Object>>) agentDef.get("agents");
        assertNotNull(compiledAgents, "agentDef has no 'agents' key");
        Map<String, Map<String, Object>> agentByName = new HashMap<>();
        for (Map<String, Object> a : compiledAgents) {
            agentByName.put((String) a.get("name"), a);
        }

        for (int i = 0; i < strategies.length; i++) {
            String stratName = strategyNames[i];
            String agentName = "e2e_java_strat_" + stratName;
            assertTrue(agentByName.containsKey(agentName),
                "Sub-agent '" + agentName + "' not found in agentDef.agents. "
                + "Found: " + agentByName.keySet());
            Object actualStrategy = agentByName.get(agentName).get("strategy");
            assertEquals(stratName, actualStrategy,
                "Sub-agent '" + agentName + "' has strategy='" + actualStrategy
                + "', expected '" + stratName + "'. "
                + "Strategy enum may not serialize to the correct JSON value.");
        }
    }

    /**
     * HTTP tool appears in agentDef.tools with toolType == "http".
     *
     * COUNTERFACTUAL: if HttpTool serialization breaks, it won't show as "http" type.
     */
    @Test
    @Order(6)
    void test_plan_http_tool() {
        dev.agentspan.model.ToolDef httpTool = HttpTool.builder()
            .name("e2e_java_http_tool")
            .description("Calls a remote HTTP endpoint")
            .url("https://api.example.com/data")
            .method("GET")
            .build();

        Agent agent = Agent.builder()
            .name("e2e_java_http_agent")
            .model(MODEL)
            .instructions("Use the HTTP tool.")
            .tools(List.of(httpTool))
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        List<String> toolNames = getToolNames(agentDef);
        assertTrue(toolNames.contains("e2e_java_http_tool"),
            "HTTP tool 'e2e_java_http_tool' not found in agentDef.tools. Found: " + toolNames);

        Map<String, String> toolTypes = getToolTypes(agentDef);
        assertEquals("http", toolTypes.get("e2e_java_http_tool"),
            "HTTP tool 'e2e_java_http_tool' has toolType='" + toolTypes.get("e2e_java_http_tool")
            + "', expected 'http'. HttpTool should serialize as type 'http'.");
    }

    /**
     * Sequential pipeline compiled via a.then(b) has strategy == "sequential".
     *
     * COUNTERFACTUAL: if .then() sets wrong strategy, assertion fails.
     */
    @Test
    @Order(7)
    void test_sequential_pipeline_plan() {
        Agent a = Agent.builder()
            .name("e2e_java_seq_a")
            .model(MODEL)
            .instructions("First step.")
            .build();
        Agent b = Agent.builder()
            .name("e2e_java_seq_b")
            .model(MODEL)
            .instructions("Second step.")
            .build();

        Agent pipeline = a.then(b);

        Map<String, Object> plan = runtime.plan(pipeline);
        Map<String, Object> agentDef = getAgentDef(plan);

        assertEquals("sequential", agentDef.get("strategy"),
            "Pipeline agentDef.strategy is '" + agentDef.get("strategy")
            + "', expected 'sequential'. Agent.then() should produce SEQUENTIAL strategy.");

        List<String> subNames = getSubAgentNames(agentDef);
        assertTrue(subNames.contains("e2e_java_seq_a"),
            "Agent 'e2e_java_seq_a' not in agentDef.agents. Found: " + subNames);
        assertTrue(subNames.contains("e2e_java_seq_b"),
            "Agent 'e2e_java_seq_b' not in agentDef.agents. Found: " + subNames);
    }
}
