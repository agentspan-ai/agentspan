// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

import ai.agentspan.Agent;
import ai.agentspan.AgentRuntime;
import ai.agentspan.model.ToolDef;
import ai.agentspan.tools.PdfTool;
import org.junit.jupiter.api.*;

import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Suite 6: PDF Tools — structural plan() assertions for {@link PdfTool}.
 *
 * <p>Mirrors Python {@code test_suite6_pdf_tools.py}. Server-side PDF tool with
 * {@code toolType="generate_pdf"} — the Conductor server converts markdown to PDF.
 * No local function.
 *
 * <p>All tests use plan() — no LLM calls. Each assertion has a counterfactual.
 */
@Tag("e2e")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
@Timeout(value = 300, unit = TimeUnit.SECONDS)
class Suite6PdfTools extends BaseTest {

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
     * Pure SDK property test: PdfTool.create() builds a ToolDef with the correct
     * fields (toolType=generate_pdf, default name, no func).
     *
     * COUNTERFACTUAL: build a worker ToolDef next to it and confirm a distinct toolType
     * — proves the test would fail if every ToolDef.toolType defaulted to "generate_pdf".
     */
    @Test
    @Order(1)
    void test_pdf_tool_def_basic_properties() {
        ToolDef pdf = PdfTool.create();

        assertEquals("generate_pdf", pdf.getName(),
            "Default PDF tool name should be 'generate_pdf'. Got: " + pdf.getName());
        assertEquals("generate_pdf", pdf.getToolType(),
            "PDF tool toolType must be 'generate_pdf'. Got: " + pdf.getToolType()
            + ". COUNTERFACTUAL: paired with the contrast assertion below.");
        assertNull(pdf.getFunc(),
            "PDF tool must NOT have a local func — the server runs GENERATE_PDF. Got: " + pdf.getFunc());
        assertNotNull(pdf.getDescription(),
            "PDF tool description must be non-null.");
        assertTrue(pdf.getDescription().toLowerCase().contains("pdf"),
            "PDF tool description should mention 'pdf'. Got: " + pdf.getDescription());

        // Counterfactual contrast — a worker ToolDef must NOT be classified as generate_pdf.
        ToolDef worker = ToolDef.builder()
            .name("e2e_s6_contrast_worker")
            .description("A worker tool")
            .inputSchema(Map.of("type", "object", "properties", Map.of()))
            .toolType("worker")
            .func(input -> input)
            .build();
        assertEquals("worker", worker.getToolType(),
            "Worker tool must remain toolType='worker'.");
        assertNotEquals(pdf.getToolType(), worker.getToolType(),
            "PDF and worker tools must have distinct toolTypes. COUNTERFACTUAL: if PdfTool.create() doesn't "
            + "override the default 'worker', these would collide.");
    }

    /**
     * PdfTool.create(name, description) accepts custom name and description that round-trip.
     *
     * COUNTERFACTUAL: a sibling PDF tool with a different name must produce a different
     * ToolDef.name, proving the name parameter isn't ignored.
     */
    @Test
    @Order(2)
    void test_pdf_tool_custom_name_and_description() {
        ToolDef custom = PdfTool.create("write_report", "Render a report into PDF.");

        assertEquals("write_report", custom.getName(),
            "Custom PDF tool name must round-trip. Got: " + custom.getName());
        assertEquals("Render a report into PDF.", custom.getDescription(),
            "Custom PDF tool description must round-trip. Got: " + custom.getDescription());
        assertEquals("generate_pdf", custom.getToolType(),
            "Custom name must NOT change toolType. Got: " + custom.getToolType());

        // Counterfactual: a second PDF tool with a different name produces a distinct ToolDef.
        ToolDef other = PdfTool.create("export_pdf", "Export.");
        assertNotEquals(custom.getName(), other.getName(),
            "Two PDF tools with different names must have distinct ToolDef.name. "
            + "COUNTERFACTUAL: if the name parameter were ignored, both would share the same name.");
    }

    /**
     * The default PDF input schema contains the {@code markdown} property and lists it
     * as required.
     *
     * COUNTERFACTUAL: when a custom inputSchema is provided, the default {@code markdown}
     * property must NOT be re-injected (proves we honor the override).
     */
    @Test
    @Order(3)
    @SuppressWarnings("unchecked")
    void test_pdf_tool_default_input_schema() {
        ToolDef pdf = PdfTool.create();

        Map<String, Object> schema = pdf.getInputSchema();
        assertNotNull(schema, "Default PDF input schema must not be null.");
        assertEquals("object", schema.get("type"),
            "Default PDF schema must be a JSON object schema. Got type=" + schema.get("type"));

        Map<String, Object> props = (Map<String, Object>) schema.get("properties");
        assertNotNull(props, "Default PDF schema must have 'properties'.");
        assertTrue(props.containsKey("markdown"),
            "Default PDF schema MUST expose a 'markdown' property. Got keys: " + props.keySet()
            + ". COUNTERFACTUAL: without this, the LLM cannot pass markdown content.");

        List<String> required = (List<String>) schema.get("required");
        assertNotNull(required, "Default PDF schema must declare a 'required' list.");
        assertTrue(required.contains("markdown"),
            "Default PDF schema must require 'markdown'. Got required=" + required
            + ". COUNTERFACTUAL: if markdown were optional, calls with empty input would silently produce blank PDFs.");

        // Counterfactual contrast — a custom inputSchema must REPLACE the default,
        // not be merged with it. Build with a schema that lacks 'markdown'.
        Map<String, Object> customSchema = Map.of(
            "type", "object",
            "properties", Map.of("title", Map.of("type", "string")),
            "required", List.of("title")
        );
        ToolDef customSchemaPdf = PdfTool.create("titled_pdf", "Title-only PDF.", customSchema);
        Map<String, Object> customProps = (Map<String, Object>) customSchemaPdf.getInputSchema().get("properties");
        assertFalse(customProps.containsKey("markdown"),
            "Custom inputSchema must REPLACE the default — 'markdown' should be absent. "
            + "Got props=" + customProps.keySet()
            + ". COUNTERFACTUAL: if the default were always merged in, this would fail.");
        assertTrue(customProps.containsKey("title"),
            "Custom schema's properties must be preserved. Got: " + customProps.keySet());
    }

    /**
     * Plan compilation: a PDF tool serializes into agentDef.tools with
     * toolType="generate_pdf" and config.taskType="GENERATE_PDF".
     *
     * COUNTERFACTUAL: the next test asserts an agent with NO PDF tool has no
     * toolType=generate_pdf entries in its plan.
     */
    @Test
    @Order(4)
    @SuppressWarnings("unchecked")
    void test_pdf_tool_serializes_to_plan() {
        ToolDef pdf = PdfTool.create();

        Agent agent = Agent.builder()
            .name("e2e_s6_agent_with_pdf")
            .model(MODEL)
            .instructions("Generate PDFs.")
            .tools(List.of(pdf))
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        Map<String, Object> tool = findToolByName(agentDef, "generate_pdf");
        assertEquals("generate_pdf", tool.get("toolType"),
            "Plan toolType should be 'generate_pdf'. Got: " + tool.get("toolType")
            + ". COUNTERFACTUAL: if serializer drops it, server won't dispatch to GENERATE_PDF task.");

        Map<String, Object> config = (Map<String, Object>) tool.get("config");
        assertNotNull(config,
            "PDF tool plan must carry a config (taskType). Got null config.");
        assertEquals("GENERATE_PDF", config.get("taskType"),
            "config.taskType should be 'GENERATE_PDF'. Got: " + config.get("taskType")
            + ". COUNTERFACTUAL: without this, server can't route the tool call to the right system task.");
    }

    /**
     * Counterfactual: an agent with NO PDF tool has no toolType=generate_pdf entries in its plan.
     *
     * Without this contrast, the previous test could pass even if every tool's toolType
     * defaulted to "generate_pdf".
     */
    @Test
    @Order(5)
    @SuppressWarnings("unchecked")
    void test_no_pdf_tool_means_no_pdf_in_plan() {
        ToolDef worker = ToolDef.builder()
            .name("e2e_s6_just_worker")
            .description("Plain worker.")
            .inputSchema(Map.of("type", "object", "properties", Map.of()))
            .toolType("worker")
            .func(input -> input)
            .build();

        Agent agent = Agent.builder()
            .name("e2e_s6_no_pdf_agent")
            .model(MODEL)
            .instructions("No PDF here.")
            .tools(List.of(worker))
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        List<Map<String, Object>> tools = (List<Map<String, Object>>) agentDef.get("tools");
        assertNotNull(tools, "agentDef.tools is null");

        boolean anyPdf = tools.stream().anyMatch(t -> "generate_pdf".equals(t.get("toolType")));
        assertFalse(anyPdf,
            "Plan must contain NO toolType='generate_pdf' entries when no PDF tool was added. Got tools: "
            + tools.stream().map(t -> t.get("name") + "[" + t.get("toolType") + "]").collect(Collectors.toList())
            + ". COUNTERFACTUAL: if every tool were serialized as generate_pdf, the server would dispatch them all to GENERATE_PDF.");
    }

    /**
     * Static defaults baked into the PDF tool (pageSize, theme) appear in config alongside taskType.
     *
     * COUNTERFACTUAL: a PDF tool built WITHOUT defaults must NOT have pageSize/theme in its config.
     */
    @Test
    @Order(6)
    @SuppressWarnings("unchecked")
    void test_pdf_tool_defaults_propagate_to_plan_config() {
        ToolDef pdfWithDefaults = PdfTool.create(
            "fancy_pdf",
            "PDF with baked-in defaults.",
            null,
            Map.of("pageSize", "LETTER", "theme", "compact")
        );

        Agent agent = Agent.builder()
            .name("e2e_s6_defaults_agent")
            .model(MODEL)
            .instructions("Render with defaults.")
            .tools(List.of(pdfWithDefaults))
            .build();

        Map<String, Object> agentDef = getAgentDef(runtime.plan(agent));
        Map<String, Object> tool = findToolByName(agentDef, "fancy_pdf");
        Map<String, Object> config = (Map<String, Object>) tool.get("config");

        assertNotNull(config, "Config null on PDF tool with defaults.");
        assertEquals("GENERATE_PDF", config.get("taskType"),
            "config.taskType should remain 'GENERATE_PDF'. Got: " + config.get("taskType"));
        assertEquals("LETTER", config.get("pageSize"),
            "config.pageSize should be 'LETTER'. Got: " + config.get("pageSize")
            + ". COUNTERFACTUAL: if defaults were dropped, server-side rendering wouldn't honor them.");
        assertEquals("compact", config.get("theme"),
            "config.theme should be 'compact'. Got: " + config.get("theme"));

        // Contrast: PDF tool with NO defaults must NOT have pageSize/theme.
        ToolDef plain = PdfTool.create("plain_pdf", "No defaults.");
        Agent agent2 = Agent.builder()
            .name("e2e_s6_plain_agent")
            .model(MODEL)
            .instructions("Plain PDF.")
            .tools(List.of(plain))
            .build();
        Map<String, Object> agentDef2 = getAgentDef(runtime.plan(agent2));
        Map<String, Object> tool2 = findToolByName(agentDef2, "plain_pdf");
        Map<String, Object> config2 = (Map<String, Object>) tool2.get("config");
        assertNull(config2.get("pageSize"),
            "Plain PDF tool must have NO pageSize. Got: " + config2.get("pageSize")
            + ". COUNTERFACTUAL: if defaults were always emitted, this would fail.");
        assertNull(config2.get("theme"),
            "Plain PDF tool must have NO theme. Got: " + config2.get("theme"));
    }
}
