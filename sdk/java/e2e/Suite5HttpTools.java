// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.


import ai.agentspan.Agent;
import ai.agentspan.AgentRuntime;
import ai.agentspan.model.ToolDef;
import ai.agentspan.tools.HttpTool;
import org.junit.jupiter.api.*;

import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Suite 15: HTTP Tools — structural plan() assertions for {@link HttpTool}.
 *
 * <p>Mirrors Python {@code test_suite5_http_tools.py}. Server-side HTTP tool with
 * {@code toolType="http"} — the server makes the HTTP call. No local function.
 *
 * <p>All tests use plan() — no LLM calls. Each assertion has a counterfactual.
 */
@Tag("e2e")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
@Timeout(value = 300, unit = TimeUnit.SECONDS)
class Suite5HttpTools extends BaseTest {

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
     * Pure SDK property test: HttpTool.builder() produces a ToolDef with the correct
     * properties (toolType=http, no func).
     *
     * COUNTERFACTUAL: build a worker ToolDef next to it and confirm a distinct toolType.
     */
    @Test
    @Order(1)
    void test_http_tool_def_basic_properties() {
        ToolDef http = HttpTool.builder()
            .name("e2e_s15_basic")
            .description("Basic HTTP tool")
            .url("http://localhost:9999/api/math/add")
            .method("GET")
            .build();

        assertEquals("e2e_s15_basic", http.getName(),
            "HTTP tool name must round-trip.");
        assertEquals("http", http.getToolType(),
            "HTTP tool toolType must be 'http'. Got: " + http.getToolType()
            + ". COUNTERFACTUAL: paired with the contrast below.");
        assertNull(http.getFunc(),
            "HTTP tool must NOT carry a local func — the server makes the request. Got: " + http.getFunc());

        ToolDef worker = ToolDef.builder()
            .name("e2e_s15_contrast_worker")
            .description("worker")
            .inputSchema(Map.of("type", "object", "properties", Map.of()))
            .toolType("worker")
            .func(input -> input)
            .build();
        assertNotEquals(http.getToolType(), worker.getToolType(),
            "HTTP and worker tools must have distinct toolTypes. COUNTERFACTUAL: if HttpTool.build() "
            + "doesn't override the default 'worker' toolType, both would be 'worker'.");
    }

    /**
     * HttpTool.builder() validates required fields — missing URL must throw.
     *
     * COUNTERFACTUAL: a valid build must succeed; if the validator never threw, both
     * branches would succeed which the assertion below prevents.
     */
    @Test
    @Order(2)
    void test_http_tool_requires_url() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
            () -> HttpTool.builder().name("e2e_s15_no_url").build(),
            "HttpTool.builder() with no URL should throw IllegalArgumentException. "
            + "COUNTERFACTUAL: if the validator is missing, build() would succeed and "
            + "the server would receive a tool with a null URL.");
        assertTrue(ex.getMessage().toLowerCase().contains("url"),
            "Error message should mention 'url'. Got: " + ex.getMessage());

        // Counterfactual contrast: providing a URL allows build to succeed.
        ToolDef ok = HttpTool.builder()
            .name("e2e_s15_with_url")
            .url("http://example.com")
            .build();
        assertNotNull(ok, "Build with URL should succeed.");
    }

    /**
     * Plan compilation: HTTP tool serializes into agentDef.tools with toolType="http"
     * and method/url inside config.
     *
     * COUNTERFACTUAL: an HTTP tool with method=GET vs POST must differ in plan.
     */
    @Test
    @Order(3)
    @SuppressWarnings("unchecked")
    void test_http_tool_serializes_to_plan() {
        ToolDef http = HttpTool.builder()
            .name("e2e_s15_plan")
            .description("API call")
            .url("https://api.example.com/v1/widgets")
            .method("POST")
            .header("Content-Type", "application/json")
            .build();

        Agent agent = Agent.builder()
            .name("e2e_s15_agent_with_http")
            .model(MODEL)
            .instructions("Use HTTP.")
            .tools(List.of(http))
            .build();

        Map<String, Object> agentDef = getAgentDef(runtime.plan(agent));
        Map<String, Object> tool = findToolByName(agentDef, "e2e_s15_plan");

        assertEquals("http", tool.get("toolType"),
            "Plan toolType should be 'http'. Got: " + tool.get("toolType"));

        Map<String, Object> config = (Map<String, Object>) tool.get("config");
        assertNotNull(config, "HTTP tool plan must include config (url, method, headers).");
        assertEquals("https://api.example.com/v1/widgets", config.get("url"),
            "config.url should round-trip. Got: " + config.get("url")
            + ". COUNTERFACTUAL: if the URL is dropped, the server has nothing to call.");
        assertEquals("POST", config.get("method"),
            "config.method should be 'POST'. Got: " + config.get("method")
            + ". COUNTERFACTUAL: paired with the GET-method check below.");

        Map<String, Object> headers = (Map<String, Object>) config.get("headers");
        assertNotNull(headers, "config.headers must be present.");
        assertEquals("application/json", headers.get("Content-Type"),
            "Content-Type header should round-trip. Got: " + headers.get("Content-Type"));
    }

    /**
     * Method contrast — GET vs POST produce distinct plan tool configs.
     *
     * COUNTERFACTUAL: if method() were a no-op, both plans would have identical methods.
     */
    @Test
    @Order(4)
    @SuppressWarnings("unchecked")
    void test_http_method_distinct_in_plan() {
        ToolDef getTool = HttpTool.builder()
            .name("e2e_s15_get")
            .url("https://api.example.com/get")
            .method("GET")
            .build();
        ToolDef postTool = HttpTool.builder()
            .name("e2e_s15_post")
            .url("https://api.example.com/post")
            .method("POST")
            .build();

        Agent agent = Agent.builder()
            .name("e2e_s15_method_agent")
            .model(MODEL)
            .instructions("Two HTTPs.")
            .tools(List.of(getTool, postTool))
            .build();

        Map<String, Object> agentDef = getAgentDef(runtime.plan(agent));
        Map<String, Object> g = findToolByName(agentDef, "e2e_s15_get");
        Map<String, Object> p = findToolByName(agentDef, "e2e_s15_post");

        String getMethod = (String) ((Map<String, Object>) g.get("config")).get("method");
        String postMethod = (String) ((Map<String, Object>) p.get("config")).get("method");

        assertEquals("GET", getMethod, "GET tool method should be 'GET'. Got: " + getMethod);
        assertEquals("POST", postMethod, "POST tool method should be 'POST'. Got: " + postMethod);
        assertNotEquals(getMethod, postMethod,
            "GET and POST tools must have distinct serialized methods. "
            + "COUNTERFACTUAL: if method() always set the same value, this would fail.");
    }

    /**
     * Credentials on an HTTP tool nest under config.credentials.
     *
     * COUNTERFACTUAL: an HTTP tool without credentials must have no credentials key in config.
     */
    @Test
    @Order(5)
    @SuppressWarnings("unchecked")
    void test_http_credentials_nested_in_plan_config() {
        ToolDef http = HttpTool.builder()
            .name("e2e_s15_authed")
            .url("https://api.example.com/secure")
            .method("GET")
            .header("Authorization", "Bearer ${HTTP_AUTH_KEY}")
            .credentials("HTTP_AUTH_KEY")
            .build();

        Agent agent = Agent.builder()
            .name("e2e_s15_authed_agent")
            .model(MODEL)
            .instructions("Authed HTTP.")
            .tools(List.of(http))
            .build();

        Map<String, Object> agentDef = getAgentDef(runtime.plan(agent));
        Map<String, Object> tool = findToolByName(agentDef, "e2e_s15_authed");
        Map<String, Object> config = (Map<String, Object>) tool.get("config");

        List<String> creds = (List<String>) config.get("credentials");
        assertNotNull(creds,
            "config.credentials missing on credentialled HTTP tool. config: " + config
            + ". COUNTERFACTUAL: if credentials aren't nested, server token won't declare them.");
        assertEquals(1, creds.size(),
            "Expected 1 credential. Got: " + creds);
        assertEquals("HTTP_AUTH_KEY", creds.get(0),
            "Credential should be 'HTTP_AUTH_KEY'. Got: " + creds.get(0));

        // Contrast: unauthenticated tool has no credentials in config
        ToolDef noAuth = HttpTool.builder()
            .name("e2e_s15_unauthed")
            .url("https://api.example.com/public")
            .method("GET")
            .build();
        Agent agent2 = Agent.builder()
            .name("e2e_s15_unauthed_agent")
            .model(MODEL)
            .instructions("Public HTTP.")
            .tools(List.of(noAuth))
            .build();
        Map<String, Object> agentDef2 = getAgentDef(runtime.plan(agent2));
        Map<String, Object> tool2 = findToolByName(agentDef2, "e2e_s15_unauthed");
        Map<String, Object> config2 = (Map<String, Object>) tool2.get("config");
        if (config2 != null) {
            assertNull(config2.get("credentials"),
                "Unauthenticated HTTP tool must have NO credentials in config. Got: " + config2.get("credentials")
                + ". COUNTERFACTUAL: if credentials() always added a value, the contrast fails.");
        }
    }

    /**
     * accept and contentType propagate into config.
     *
     * COUNTERFACTUAL: an HTTP tool that doesn't set these must have them absent in the plan.
     */
    @Test
    @Order(6)
    @SuppressWarnings("unchecked")
    void test_http_accept_and_content_type_in_plan() {
        ToolDef http = HttpTool.builder()
            .name("e2e_s15_negotiated")
            .url("https://api.example.com/data")
            .method("POST")
            .accept("application/json", "application/xml")
            .contentType("application/json")
            .build();

        Agent agent = Agent.builder()
            .name("e2e_s15_negotiated_agent")
            .model(MODEL)
            .instructions("Content-negotiated HTTP.")
            .tools(List.of(http))
            .build();

        Map<String, Object> agentDef = getAgentDef(runtime.plan(agent));
        Map<String, Object> tool = findToolByName(agentDef, "e2e_s15_negotiated");
        Map<String, Object> config = (Map<String, Object>) tool.get("config");
        assertNotNull(config, "config null");

        List<String> accept = (List<String>) config.get("accept");
        assertNotNull(accept, "config.accept missing. config: " + config);
        assertTrue(accept.contains("application/json") && accept.contains("application/xml"),
            "accept should contain both 'application/json' and 'application/xml'. Got: " + accept);

        assertEquals("application/json", config.get("contentType"),
            "config.contentType should be 'application/json'. Got: " + config.get("contentType")
            + ". COUNTERFACTUAL: contrast below verifies absence when not set.");

        // Contrast: a basic HTTP tool with NO accept/contentType
        ToolDef plain = HttpTool.builder()
            .name("e2e_s15_plain")
            .url("https://api.example.com/plain")
            .method("GET")
            .build();
        Agent agent2 = Agent.builder()
            .name("e2e_s15_plain_agent")
            .model(MODEL)
            .instructions("Plain HTTP.")
            .tools(List.of(plain))
            .build();
        Map<String, Object> tool2 = findToolByName(getAgentDef(runtime.plan(agent2)), "e2e_s15_plain");
        Map<String, Object> config2 = (Map<String, Object>) tool2.get("config");
        assertNull(config2.get("accept"),
            "config.accept must be absent when not configured. Got: " + config2.get("accept")
            + ". COUNTERFACTUAL: if accept() were always emitted, this would fail.");
        assertNull(config2.get("contentType"),
            "config.contentType must be absent when not configured. Got: " + config2.get("contentType"));
    }
}
