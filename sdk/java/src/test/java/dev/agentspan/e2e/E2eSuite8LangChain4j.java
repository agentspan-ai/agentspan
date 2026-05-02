// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.e2e;

import dev.agentspan.Agent;
import dev.agentspan.AgentRuntime;
import dev.agentspan.enums.AgentStatus;
import dev.agentspan.frameworks.LangChain4jAgent;
import dev.agentspan.model.AgentResult;
import dev.agentspan.model.ToolDef;
import org.junit.jupiter.api.*;

import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Suite 8: LangChain4j framework integration.
 *
 * <p>Validates that {@link LangChain4jAgent} correctly bridges LangChain4j
 * {@code @Tool}-annotated POJOs to Agentspan agents:
 * <ol>
 *   <li>Framework detection — {@link LangChain4jAgent#isLangChain4jTools} works</li>
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
class E2eSuite8LangChain4j extends E2eBaseTest {

    private static AgentRuntime runtime;

    /** Set to {@code true} inside the {@code lc4j_add} tool body when it is actually invoked. */
    static final AtomicBoolean toolCalled = new AtomicBoolean(false);

    @BeforeAll
    static void setup() {
        runtime = new AgentRuntime(new dev.agentspan.AgentConfig(BASE_URL, null, null, 100, 1));
    }

    @AfterAll
    static void teardown() {
        if (runtime != null) runtime.close();
    }

    // ── Tool class (LangChain4j @Tool annotations) ────────────────────────

    static class CalculatorTools {
        @dev.langchain4j.agent.tool.Tool(name = "lc4j_add", value = "Add two integers")
        public int add(
                @dev.langchain4j.agent.tool.P("a") int a,
                @dev.langchain4j.agent.tool.P("b") int b) {
            // Side-effect: proves tool function body actually ran
            toolCalled.set(true);
            return a + b;
        }

        @dev.langchain4j.agent.tool.Tool(name = "lc4j_greet", value = "Greet a person by name")
        public String greet(@dev.langchain4j.agent.tool.P("name") String name) {
            return "Hello, " + name + "!";
        }
    }

    // ── Tests ─────────────────────────────────────────────────────────────

    /**
     * isLangChain4jTools correctly identifies objects with @Tool methods.
     *
     * COUNTERFACTUAL: if annotation detection is broken, isLangChain4jTools returns
     * false for CalculatorTools → assertion fails.
     */
    @Test
    @Order(1)
    void test_framework_detection() {
        assertTrue(
            LangChain4jAgent.isLangChain4jTools(new CalculatorTools()),
            "isLangChain4jTools should return true for CalculatorTools (has @dev.langchain4j.agent.tool.Tool methods). "
            + "COUNTERFACTUAL: if annotation detection is broken, this returns false.");

        assertFalse(
            LangChain4jAgent.isLangChain4jTools(new Object()),
            "isLangChain4jTools should return false for plain Object (no @Tool methods). "
            + "COUNTERFACTUAL: if detection always returns true, this assertion fails.");

        assertFalse(
            LangChain4jAgent.isLangChain4jTools(null),
            "isLangChain4jTools should return false for null.");
    }

    /**
     * LangChain4jAgent.from() correctly extracts 2 tools with expected names, non-empty
     * descriptions, and valid JSON Schema (type=object, properties present).
     *
     * COUNTERFACTUAL: if extraction misses a tool → count assertion fails;
     * if name is wrong → name assertion fails;
     * if schema is not JSON Schema → type/properties assertion fails.
     */
    @Test
    @Order(2)
    @SuppressWarnings("unchecked")
    void test_tool_extraction() {
        Agent agent = LangChain4jAgent.from(
                "lc4j_extraction_test",
                MODEL,
                "You are a test agent.",
                new CalculatorTools());

        List<ToolDef> tools = agent.getTools();

        // Correct count
        assertEquals(2, tools.size(),
            "Expected 2 tools from CalculatorTools, got " + tools.size() + ". "
            + "COUNTERFACTUAL: if extractTools misses a @Tool method, count < 2.");

        // Extract by name
        List<String> names = tools.stream().map(ToolDef::getName).collect(Collectors.toList());
        assertTrue(names.contains("lc4j_add"),
            "Tool 'lc4j_add' not found. Got: " + names + ". "
            + "COUNTERFACTUAL: if @Tool(name=...) is not read, name would be Java method name.");
        assertTrue(names.contains("lc4j_greet"),
            "Tool 'lc4j_greet' not found. Got: " + names + ". "
            + "COUNTERFACTUAL: same as above.");

        // Non-empty descriptions
        for (ToolDef tool : tools) {
            assertNotNull(tool.getDescription(),
                "Tool '" + tool.getName() + "' has null description.");
            assertFalse(tool.getDescription().isEmpty(),
                "Tool '" + tool.getName() + "' has empty description. "
                + "COUNTERFACTUAL: if @Tool(value=...) is not read, description would be empty.");
        }

        // Valid JSON Schema
        for (ToolDef tool : tools) {
            Map<String, Object> schema = tool.getInputSchema();
            assertNotNull(schema,
                "Tool '" + tool.getName() + "' has null inputSchema.");
            assertEquals("object", schema.get("type"),
                "Tool '" + tool.getName() + "' inputSchema.type != 'object'. "
                + "Got: " + schema.get("type") + ". "
                + "COUNTERFACTUAL: if schema generation is broken, type would be missing or wrong.");
            assertTrue(schema.containsKey("properties"),
                "Tool '" + tool.getName() + "' inputSchema missing 'properties' key. "
                + "Got keys: " + schema.keySet() + ". "
                + "COUNTERFACTUAL: if schema generation is broken, properties would be absent.");
        }

        // lc4j_add should have properties 'a' and 'b'
        ToolDef addTool = tools.stream()
                .filter(t -> "lc4j_add".equals(t.getName()))
                .findFirst()
                .orElseThrow(() -> new AssertionError("lc4j_add not found"));
        Map<String, Object> addSchema = addTool.getInputSchema();
        Map<String, Object> addProps = (Map<String, Object>) addSchema.get("properties");
        assertTrue(addProps.containsKey("a"),
            "lc4j_add schema missing property 'a'. Got: " + addProps.keySet() + ". "
            + "COUNTERFACTUAL: if @P annotation not read and -parameters not set, property name would be 'arg0'.");
        assertTrue(addProps.containsKey("b"),
            "lc4j_add schema missing property 'b'. Got: " + addProps.keySet() + ". "
            + "COUNTERFACTUAL: same as above.");

        // lc4j_greet should have property 'name'
        ToolDef greetTool = tools.stream()
                .filter(t -> "lc4j_greet".equals(t.getName()))
                .findFirst()
                .orElseThrow(() -> new AssertionError("lc4j_greet not found"));
        Map<String, Object> greetProps = (Map<String, Object>) greetTool.getInputSchema().get("properties");
        assertTrue(greetProps.containsKey("name"),
            "lc4j_greet schema missing property 'name'. Got: " + greetProps.keySet());
    }

    /**
     * Agent from LangChain4jAgent.from() compiles via plan() and produces correct
     * agentDef with both tools having toolType="worker".
     *
     * COUNTERFACTUAL: if ToolDef serialization breaks, tools would be absent from
     * agentDef → list assertion fails.
     */
    @Test
    @Order(3)
    @SuppressWarnings("unchecked")
    void test_compiles_via_server() {
        Agent agent = LangChain4jAgent.from(
                "lc4j_compile_test",
                MODEL,
                "You are a test agent.",
                new CalculatorTools());

        Map<String, Object> plan = runtime.plan(agent);

        assertTrue(plan.containsKey("workflowDef"),
            "plan() result missing 'workflowDef'. Got keys: " + plan.keySet() + ". "
            + "COUNTERFACTUAL: if agent serialization is completely broken, plan() fails.");

        Map<String, Object> agentDef = getAgentDef(plan);

        List<Map<String, Object>> tools = (List<Map<String, Object>>) agentDef.get("tools");
        assertNotNull(tools,
            "agentDef has no 'tools' key. "
            + "COUNTERFACTUAL: if tool list serialization breaks, key is absent.");
        assertEquals(2, tools.size(),
            "Expected 2 tools in agentDef.tools, got " + tools.size() + ". "
            + "COUNTERFACTUAL: if tool extraction is incomplete, fewer tools appear.");

        List<String> toolNames = tools.stream()
                .map(t -> (String) t.get("name"))
                .collect(Collectors.toList());
        assertTrue(toolNames.contains("lc4j_add"),
            "Tool 'lc4j_add' not found in compiled agentDef. Got: " + toolNames);
        assertTrue(toolNames.contains("lc4j_greet"),
            "Tool 'lc4j_greet' not found in compiled agentDef. Got: " + toolNames);

        // Both must have toolType="worker"
        for (Map<String, Object> tool : tools) {
            assertEquals("worker", tool.get("toolType"),
                "Tool '" + tool.get("name") + "' has toolType='" + tool.get("toolType")
                + "', expected 'worker'. "
                + "COUNTERFACTUAL: if toolType is not set, server may reject the agent.");
        }
    }

    /**
     * Running the agent end-to-end causes the lc4j_add tool function body to execute.
     *
     * COUNTERFACTUAL: if worker dispatch or tool registration breaks, toolCalled stays
     * false → assertion fails. Also asserts COMPLETED status so we detect server-side
     * failures (e.g., schema mismatch that causes FAILED).
     */
    @Test
    @Order(4)
    @Timeout(value = 300, unit = TimeUnit.SECONDS)
    void test_runtime_tool_invocation() {
        toolCalled.set(false); // reset before the run

        Agent agent = LangChain4jAgent.from(
                "lc4j_runtime_test",
                MODEL,
                "You MUST call the lc4j_add tool with a=7, b=8. Report the result.",
                new CalculatorTools());

        AgentResult result = runtime.run(agent, "What is 7 + 8?");

        assertEquals(AgentStatus.COMPLETED, result.getStatus(),
            "Agent did not complete. Status: " + result.getStatus()
            + ". Error: " + result.getError() + ". "
            + "COUNTERFACTUAL: if agent compilation or execution fails, status is not COMPLETED.");

        assertTrue(toolCalled.get(),
            "The 'lc4j_add' tool function body was never called. "
            + "COUNTERFACTUAL: if LangChain4j worker dispatch is broken (wrong function wrapped, "
            + "wrong worker name, or worker not registered), the flag stays false.");
    }
}
