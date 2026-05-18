// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.


import ai.agentspan.Agent;
import ai.agentspan.AgentRuntime;
import ai.agentspan.model.ToolDef;
import ai.agentspan.tools.McpTool;
import org.junit.jupiter.api.*;

import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Suite 14: MCP Tools — structural plan() assertions for {@link McpTool}.
 *
 * <p>Mirrors Python {@code test_suite4_mcp_tools.py}. Server-side MCP tool with
 * {@code toolType="mcp"}. No local function — the server brokers MCP communication.
 *
 * <p>All tests use plan() — no LLM calls. Each assertion has a counterfactual.
 */
@Tag("e2e")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
@Timeout(value = 300, unit = TimeUnit.SECONDS)
class Suite4McpTools extends BaseTest {

    private static AgentRuntime runtime;

    @BeforeAll
    static void setup() {
        runtime = new AgentRuntime(new ai.agentspan.AgentConfig(BASE_URL, null, null, 100, 1));
    }

    @AfterAll
    static void teardown() {
        if (runtime != null) runtime.close();
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    @SuppressWarnings("unchecked")
    private Map<String, Object> findToolByName(Map<String, Object> agentDef, String name) {
        List<Map<String, Object>> tools = (List<Map<String, Object>>) agentDef.get("tools");
        assertNotNull(tools, "agentDef has no 'tools' key");
        return tools.stream()
            .filter(t -> name.equals(t.get("name")))
            .findFirst()
            .orElseGet(() -> {
                fail("Tool '" + name + "' not found. Available: "
                    + tools.stream().map(t -> (String) t.get("name")).collect(Collectors.toList()));
                return null;
            });
    }

    // ── Tests ─────────────────────────────────────────────────────────────────

    /**
     * Pure SDK property test: McpTool.builder() builds a ToolDef with the correct
     * fields (toolType=mcp, name, description, no func).
     *
     * COUNTERFACTUAL: a non-MCP tool built next to it must have a different toolType
     * — proves the test would fail if every ToolDef.toolType were hard-coded to "mcp".
     */
    @Test
    @Order(1)
    void test_mcp_tool_def_basic_properties() {
        ToolDef mcp = McpTool.builder()
            .name("e2e_s14_basic")
            .description("Basic MCP tool")
            .serverUrl("http://localhost:9999/mcp")
            .toolName("math_add")
            .build();

        assertEquals("e2e_s14_basic", mcp.getName(),
            "MCP tool name must round-trip.");
        assertEquals("Basic MCP tool", mcp.getDescription(),
            "MCP tool description must round-trip.");
        assertEquals("mcp", mcp.getToolType(),
            "MCP tool toolType must be 'mcp'. Got: " + mcp.getToolType()
            + ". COUNTERFACTUAL: paired with the contrast assertion below.");
        assertNull(mcp.getFunc(),
            "MCP tool must NOT have a local func — the server handles execution. Got: " + mcp.getFunc());

        // Counterfactual contrast — a worker ToolDef must NOT be classified as mcp.
        ToolDef worker = ToolDef.builder()
            .name("e2e_s14_contrast_worker")
            .description("A worker tool")
            .inputSchema(Map.of("type", "object", "properties", Map.of()))
            .toolType("worker")
            .func(input -> input)
            .build();
        assertEquals("worker", worker.getToolType(),
            "Worker tool must remain toolType='worker'.");
        assertNotEquals(mcp.getToolType(), worker.getToolType(),
            "MCP and worker tools must have distinct toolTypes. COUNTERFACTUAL: if McpTool.builder() doesn't "
            + "override the default 'worker', these would collide.");
    }

    /**
     * McpTool credentials propagate to ToolDef.credentials.
     *
     * COUNTERFACTUAL: a sibling MCP tool with NO credentials must end up with an empty list,
     * proving the credentials setter isn't a no-op that always returns the same value.
     */
    @Test
    @Order(2)
    void test_mcp_tool_credentials_round_trip() {
        ToolDef authed = McpTool.builder()
            .name("e2e_s14_authed")
            .description("MCP tool with auth")
            .serverUrl("http://localhost:9999/mcp")
            .header("Authorization", "Bearer ${MCP_AUTH_KEY}")
            .credentials("MCP_AUTH_KEY")
            .build();

        List<String> creds = authed.getCredentials();
        assertNotNull(creds, "credentials list is null");
        assertEquals(1, creds.size(),
            "Expected exactly 1 credential. Got: " + creds);
        assertEquals("MCP_AUTH_KEY", creds.get(0),
            "Credential should be 'MCP_AUTH_KEY'. Got: " + creds.get(0));

        // Counterfactual: a no-credentials tool must produce an empty list.
        ToolDef unauthed = McpTool.builder()
            .name("e2e_s14_unauthed")
            .description("MCP tool without auth")
            .serverUrl("http://localhost:9999/mcp")
            .build();
        assertTrue(unauthed.getCredentials() == null || unauthed.getCredentials().isEmpty(),
            "Unauthenticated MCP tool must have no credentials. Got: " + unauthed.getCredentials()
            + ". COUNTERFACTUAL: if credentials() always added 'MCP_AUTH_KEY', this would fail.");
    }

    /**
     * Plan compilation: an MCP tool serializes into agentDef.tools with toolType="mcp"
     * and the server URL inside config.
     *
     * COUNTERFACTUAL: the next test asserts a non-MCP agent's plan contains NO mcp tool.
     */
    @Test
    @Order(3)
    @SuppressWarnings("unchecked")
    void test_mcp_tool_serializes_to_plan() {
        ToolDef mcp = McpTool.builder()
            .name("e2e_s14_plan")
            .description("MCP tool in plan")
            .serverUrl("http://localhost:9999/mcp")
            .header("X-Test", "yes")
            .build();

        Agent agent = Agent.builder()
            .name("e2e_s14_agent_with_mcp")
            .model(MODEL)
            .instructions("Use MCP.")
            .tools(List.of(mcp))
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        Map<String, Object> tool = findToolByName(agentDef, "e2e_s14_plan");
        assertEquals("mcp", tool.get("toolType"),
            "Plan toolType should be 'mcp'. Got: " + tool.get("toolType")
            + ". COUNTERFACTUAL: if serializer drops it, server won't treat it as MCP.");

        Map<String, Object> config = (Map<String, Object>) tool.get("config");
        assertNotNull(config,
            "MCP tool plan must carry config (serverUrl, headers). Got null config.");
        assertEquals("http://localhost:9999/mcp", config.get("serverUrl"),
            "config.serverUrl should round-trip. Got: " + config.get("serverUrl"));

        Map<String, Object> headers = (Map<String, Object>) config.get("headers");
        assertNotNull(headers, "config.headers should be present.");
        assertEquals("yes", headers.get("X-Test"),
            "Header 'X-Test' should be 'yes'. Got: " + headers.get("X-Test")
            + ". COUNTERFACTUAL: if headers are lost, MCP auth headers would not reach the server.");
    }

    /**
     * Counterfactual: an agent with NO MCP tool has no toolType=mcp entries in its plan.
     *
     * Without this contrast, the previous test could pass even if every tool's toolType
     * defaulted to "mcp".
     */
    @Test
    @Order(4)
    @SuppressWarnings("unchecked")
    void test_no_mcp_tool_means_no_mcp_in_plan() {
        ToolDef worker = ToolDef.builder()
            .name("e2e_s14_just_worker")
            .description("Plain worker.")
            .inputSchema(Map.of("type", "object", "properties", Map.of()))
            .toolType("worker")
            .func(input -> input)
            .build();

        Agent agent = Agent.builder()
            .name("e2e_s14_no_mcp_agent")
            .model(MODEL)
            .instructions("No MCP here.")
            .tools(List.of(worker))
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        List<Map<String, Object>> tools = (List<Map<String, Object>>) agentDef.get("tools");
        assertNotNull(tools, "agentDef.tools is null");

        boolean anyMcp = tools.stream().anyMatch(t -> "mcp".equals(t.get("toolType")));
        assertFalse(anyMcp,
            "Plan must contain NO toolType='mcp' entries when no MCP tool was added. Got tools: "
            + tools.stream().map(t -> t.get("name") + "[" + t.get("toolType") + "]").collect(Collectors.toList())
            + ". COUNTERFACTUAL: if every tool were serialized as mcp, the server would broker non-MCP tools incorrectly.");
    }

    /**
     * Plan-level: credentials on an MCP tool are nested under config.credentials so the
     * server includes them in the execution token's declared_names.
     *
     * COUNTERFACTUAL: a sibling MCP tool with NO credentials must have no credentials list.
     */
    @Test
    @Order(5)
    @SuppressWarnings("unchecked")
    void test_mcp_credentials_nested_in_plan_config() {
        ToolDef mcp = McpTool.builder()
            .name("e2e_s14_creds_plan")
            .description("MCP with credentials")
            .serverUrl("http://localhost:9999/mcp")
            .header("Authorization", "Bearer ${MCP_AUTH_KEY}")
            .credentials("MCP_AUTH_KEY")
            .build();

        Agent agent = Agent.builder()
            .name("e2e_s14_creds_agent")
            .model(MODEL)
            .instructions("Use authed MCP.")
            .tools(List.of(mcp))
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);
        Map<String, Object> tool = findToolByName(agentDef, "e2e_s14_creds_plan");

        Map<String, Object> config = (Map<String, Object>) tool.get("config");
        assertNotNull(config, "config null on credentialled MCP tool");

        List<String> creds = (List<String>) config.get("credentials");
        assertNotNull(creds,
            "config.credentials should be present. config: " + config
            + ". COUNTERFACTUAL: if credentials aren't nested under config, the server token won't declare them.");
        assertEquals(1, creds.size(),
            "Should have exactly one credential. Got: " + creds);
        assertEquals("MCP_AUTH_KEY", creds.get(0),
            "Credential name should be 'MCP_AUTH_KEY'. Got: " + creds.get(0));

        // Contrast — uncredentialled tool should not have credentials in config
        ToolDef noCred = McpTool.builder()
            .name("e2e_s14_no_creds_plan")
            .description("MCP without credentials")
            .serverUrl("http://localhost:9999/mcp")
            .build();
        Agent agent2 = Agent.builder()
            .name("e2e_s14_no_creds_agent")
            .model(MODEL)
            .instructions("Plain MCP.")
            .tools(List.of(noCred))
            .build();
        Map<String, Object> agentDef2 = getAgentDef(runtime.plan(agent2));
        Map<String, Object> tool2 = findToolByName(agentDef2, "e2e_s14_no_creds_plan");
        Map<String, Object> config2 = (Map<String, Object>) tool2.get("config");
        if (config2 != null) {
            assertNull(config2.get("credentials"),
                "Unauthenticated MCP tool must have NO credentials in config. Got: " + config2.get("credentials")
                + ". COUNTERFACTUAL: if credentials() always emits a list, the contrast fails.");
        }
    }

    /**
     * Multi-tool composition: an agent can carry MCP + worker side-by-side and both
     * survive the plan.
     *
     * COUNTERFACTUAL: if MCP serialization overwrites or de-dupes worker tools, the
     * count check fails.
     */
    @Test
    @Order(6)
    @SuppressWarnings("unchecked")
    void test_mcp_and_worker_tools_coexist() {
        ToolDef mcp = McpTool.builder()
            .name("e2e_s14_compose_mcp")
            .description("MCP")
            .serverUrl("http://localhost:9999/mcp")
            .build();
        ToolDef worker = ToolDef.builder()
            .name("e2e_s14_compose_worker")
            .description("worker")
            .inputSchema(Map.of("type", "object", "properties", Map.of()))
            .toolType("worker")
            .func(input -> input)
            .build();

        Agent agent = Agent.builder()
            .name("e2e_s14_compose_agent")
            .model(MODEL)
            .instructions("Mixed tools.")
            .tools(List.of(mcp, worker))
            .build();

        Map<String, Object> agentDef = getAgentDef(runtime.plan(agent));
        List<Map<String, Object>> tools = (List<Map<String, Object>>) agentDef.get("tools");
        assertNotNull(tools, "tools list is null");

        Map<String, String> typeByName = tools.stream()
            .collect(Collectors.toMap(t -> (String) t.get("name"), t -> (String) t.get("toolType"), (a, b) -> a));

        assertEquals("mcp", typeByName.get("e2e_s14_compose_mcp"),
            "MCP tool must serialize as toolType='mcp'. Got: " + typeByName.get("e2e_s14_compose_mcp"));
        assertEquals("worker", typeByName.get("e2e_s14_compose_worker"),
            "Worker tool must serialize as toolType='worker'. Got: " + typeByName.get("e2e_s14_compose_worker")
            + ". COUNTERFACTUAL: if MCP serialization clobbered every tool, this would be 'mcp'.");
    }
}
