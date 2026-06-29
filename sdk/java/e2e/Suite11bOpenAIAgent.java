// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.stream.Collectors;

import org.conductoross.conductor.ai.Agent;
import org.conductoross.conductor.ai.AgentConfig;
import org.conductoross.conductor.ai.AgentRuntime;
import org.conductoross.conductor.ai.enums.AgentStatus;
import org.conductoross.conductor.ai.frameworks.OpenAIAgent;
import org.conductoross.conductor.ai.model.AgentResult;
import org.conductoross.conductor.ai.model.CompileResponse;
import org.conductoross.conductor.ai.model.ToolDef;
import org.junit.jupiter.api.*;

/**
 * Suite 11b: OpenAI Agents SDK framework integration.
 *
 * <p>Mirrors {@code Suite11LangChain4j} for the {@link OpenAIAgent} bridge, the
 * way Python's framework e2e (e.g. {@code test_suite11_langgraph}) exercises a
 * foreign-framework agent: detection/tagging, tool extraction, server
 * compilation, and runtime execution. The server routes {@code framework="openai"}
 * through its {@code OpenAINormalizer}.
 * <ol>
 *   <li>Framework tagging — {@link OpenAIAgent} builds an Agent with framework="openai"</li>
 *   <li>Tool extraction — correct names, descriptions, and JSON Schema</li>
 *   <li>Server compilation — agent compiles cleanly via {@code plan()}</li>
 *   <li>Runtime execution — tool function body actually runs end-to-end</li>
 * </ol>
 *
 * <p>All validation is deterministic (no LLM output parsing for assertion).
 */
@Tag("e2e")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
@Timeout(value = 300, unit = TimeUnit.SECONDS)
class Suite11bOpenAIAgent extends BaseTest {

    private static AgentRuntime runtime;

    /** Set to {@code true} inside the {@code oai_add} tool body when it is actually invoked. */
    static final AtomicBoolean toolCalled = new AtomicBoolean(false);

    @BeforeAll
    static void setup() {
        runtime = new AgentRuntime(new AgentConfig(100, 1));
    }

    @AfterAll
    static void teardown() {
        if (runtime != null) runtime.close();
    }

    // ── Tool class (@Tool-annotated POJO; OpenAIAgent accepts the LangChain4j annotation) ──

    static class CalculatorTools {
        @dev.langchain4j.agent.tool.Tool(name = "oai_add", value = "Add two integers")
        public int add(@dev.langchain4j.agent.tool.P("a") int a, @dev.langchain4j.agent.tool.P("b") int b) {
            // Side-effect: proves tool function body actually ran
            toolCalled.set(true);
            return a + b;
        }

        @dev.langchain4j.agent.tool.Tool(name = "oai_greet", value = "Greet a person by name")
        public String greet(@dev.langchain4j.agent.tool.P("name") String name) {
            return "Hello, " + name + "!";
        }
    }

    // ── Tests ─────────────────────────────────────────────────────────────

    /**
     * OpenAIAgent.builder().build() tags the agent with framework="openai" and extracts
     * the @Tool methods. This is the OpenAI analogue of LangChain4j's detection test.
     *
     * COUNTERFACTUAL: if the bridge forgets to set framework, getFramework() != "openai";
     * if tool extraction is broken, the tool list is empty.
     */
    @Test
    @Order(1)
    void test_framework_tagging_and_tool_extraction() {
        Agent agent = OpenAIAgent.builder()
                .name("oai_extraction_test")
                .model(MODEL)
                .instructions("You are a test agent.")
                .tools(new CalculatorTools())
                .build();

        assertEquals(
                "openai",
                agent.getFramework(),
                "OpenAIAgent must tag the agent with framework='openai'. Got: " + agent.getFramework()
                        + ". COUNTERFACTUAL: if the bridge omits .framework(\"openai\"), the server routes it "
                        + "through the wrong (or no) normalizer.");

        List<ToolDef> tools = agent.getTools();
        assertEquals(
                2,
                tools.size(),
                "Expected 2 tools from CalculatorTools, got " + tools.size()
                        + ". COUNTERFACTUAL: if extractTools misses a @Tool method, count < 2.");

        List<String> names = tools.stream().map(ToolDef::getName).collect(Collectors.toList());
        assertTrue(
                names.contains("oai_add"),
                "Tool 'oai_add' not found. Got: " + names
                        + ". COUNTERFACTUAL: if @Tool(name=...) is ignored, name would be the Java method name.");
        assertTrue(names.contains("oai_greet"), "Tool 'oai_greet' not found. Got: " + names);

        // Valid JSON Schema with parameter names from @P
        ToolDef add = tools.stream()
                .filter(t -> "oai_add".equals(t.getName()))
                .findFirst()
                .orElseThrow();
        assertNotNull(add.getDescription());
        assertFalse(
                add.getDescription().isEmpty(),
                "oai_add description empty. COUNTERFACTUAL: if @Tool(value=...) is ignored, description is empty.");
        Map<String, Object> schema = add.getInputSchema();
        assertEquals("object", schema.get("type"), "oai_add inputSchema.type != 'object'. Got: " + schema.get("type"));
        @SuppressWarnings("unchecked")
        Map<String, Object> props = (Map<String, Object>) schema.get("properties");
        assertTrue(
                props.containsKey("a") && props.containsKey("b"),
                "oai_add schema missing properties a/b. Got: " + props.keySet()
                        + ". COUNTERFACTUAL: if @P is ignored and -parameters is off, names would be arg0/arg1.");
    }

    /**
     * Agent from OpenAIAgent compiles via plan() (the server normalizes the
     * framework="openai" agent into a native agentDef) and the normalized agentDef
     * carries both tools as toolType="worker".
     *
     * NOTE: the compiled agentDef does NOT carry framework="openai" — compilation
     * runs OpenAINormalizer, which consumes the framework tag and emits a native
     * config. Framework tagging is asserted pre-compile in test_framework_tagging.
     *
     * COUNTERFACTUAL: if tool serialization/normalization breaks, the tools are absent.
     */
    @Test
    @Order(2)
    @SuppressWarnings("unchecked")
    void test_compiles_via_server() {
        Agent agent = OpenAIAgent.builder()
                .name("oai_compile_test")
                .model(MODEL)
                .instructions("You are a test agent.")
                .tools(new CalculatorTools())
                .build();

        CompileResponse plan = runtime.plan(agent);
        assertTrue(
                plan.getWorkflowDef() != null && !plan.getWorkflowDef().isEmpty(),
                "plan() result missing 'workflowDef'. Got keys: " + "[workflowDef, requiredWorkers]"
                        + ". COUNTERFACTUAL: if framework-agent serialization is broken, the server rejects compile.");

        Map<String, Object> agentDef = getAgentDef(plan);

        List<Map<String, Object>> tools = (List<Map<String, Object>>) agentDef.get("tools");
        assertNotNull(tools, "agentDef has no 'tools' key.");
        assertEquals(
                2,
                tools.size(),
                "Expected 2 tools in agentDef.tools, got " + tools.size()
                        + ". COUNTERFACTUAL: if a tool is dropped during openai normalization, count < 2.");

        // The OpenAINormalizer emits worker-backed tools keyed by `_worker_ref`
        // (its presence is what marks the tool as a local worker; there is no
        // separate `name`/`toolType` field in the normalized form).
        List<String> toolRefs =
                tools.stream().map(t -> (String) t.get("_worker_ref")).collect(Collectors.toList());
        assertTrue(
                toolRefs.contains("oai_add") && toolRefs.contains("oai_greet"),
                "Compiled agentDef tools missing oai_add/oai_greet (_worker_ref). Got: " + toolRefs
                        + ". COUNTERFACTUAL: if normalization drops the worker binding, the refs are absent/renamed.");
    }

    /**
     * Running the agent end-to-end causes the oai_add tool function body to execute,
     * proving the server normalizes framework="openai" and dispatches the worker tool.
     *
     * COUNTERFACTUAL: if the openai normalizer drops tools or worker dispatch breaks,
     * toolCalled stays false; if compilation/execution fails, status != COMPLETED.
     */
    @Test
    @Order(3)
    @Timeout(value = 300, unit = TimeUnit.SECONDS)
    void test_runtime_tool_invocation() {
        toolCalled.set(false);

        Agent agent = OpenAIAgent.builder()
                .name("oai_runtime_test")
                .model(MODEL)
                .instructions("You MUST call the oai_add tool with a=7, b=8. Report the result.")
                .tools(new CalculatorTools())
                .build();

        AgentResult result = runtime.run(agent, "What is 7 + 8?");

        assertEquals(
                AgentStatus.COMPLETED,
                result.getStatus(),
                "Agent did not complete. Status: " + result.getStatus() + ". Error: " + result.getError()
                        + ". COUNTERFACTUAL: if openai-framework compilation or execution fails, status != COMPLETED.");
        assertTrue(
                toolCalled.get(),
                "The 'oai_add' tool function body was never called. "
                        + "COUNTERFACTUAL: if the openai normalizer drops the worker tool or worker dispatch is "
                        + "broken (wrong function wrapped, wrong worker name, not registered), the flag stays false.");
    }
}
