// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.


import ai.agentspan.Agent;
import ai.agentspan.AgentRuntime;
import ai.agentspan.model.ToolDef;
import ai.agentspan.tools.MediaTools;
import org.junit.jupiter.api.*;

import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Suite 16: Media Tools — structural plan() assertions for {@link MediaTools}.
 *
 * <p>Mirrors Python {@code test_suite7_media_tools.py}. Media generation tools
 * (image, audio, video, pdf) run entirely server-side. Each carries an
 * {@code llmProvider} / {@code model} in config and a {@code taskType} for the
 * Conductor task name.
 *
 * <p>All tests use plan() — no LLM calls. Each assertion has a counterfactual.
 */
@Tag("e2e")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
@Timeout(value = 300, unit = TimeUnit.SECONDS)
class Suite7MediaTools extends BaseTest {

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
     * Pure SDK property test: imageTool factory produces a ToolDef with toolType=generate_image
     * and llmProvider/model in config.
     *
     * COUNTERFACTUAL: an audioTool built next to it must have a DIFFERENT toolType — proves
     * the test would fail if every MediaTools.* call were a stub returning the same toolType.
     */
    @Test
    @Order(1)
    @SuppressWarnings("unchecked")
    void test_image_tool_basic_properties() {
        ToolDef img = MediaTools.imageTool(
            "e2e_s16_image",
            "Generate an image.",
            "openai",
            "dall-e-3");

        assertEquals("e2e_s16_image", img.getName(), "image tool name must round-trip.");
        assertEquals("generate_image", img.getToolType(),
            "image tool toolType should be 'generate_image'. Got: " + img.getToolType());

        Map<String, Object> config = img.getConfig();
        assertNotNull(config, "image tool config null");
        assertEquals("openai", config.get("llmProvider"),
            "config.llmProvider should be 'openai'. Got: " + config.get("llmProvider"));
        assertEquals("dall-e-3", config.get("model"),
            "config.model should be 'dall-e-3'. Got: " + config.get("model"));
        assertEquals("GENERATE_IMAGE", config.get("taskType"),
            "config.taskType should be 'GENERATE_IMAGE'. Got: " + config.get("taskType"));

        // Counterfactual contrast — an audioTool must produce a distinct toolType.
        ToolDef aud = MediaTools.audioTool(
            "e2e_s16_image_contrast_audio",
            "Generate audio.",
            "openai",
            "tts-1");
        assertNotEquals(img.getToolType(), aud.getToolType(),
            "imageTool and audioTool must have DIFFERENT toolTypes. Got both='" + img.getToolType() + "'."
            + " COUNTERFACTUAL: if every media factory returned the same toolType, the server "
            + "would dispatch all media tasks to the same Conductor task.");
    }

    /**
     * audioTool produces toolType=generate_audio with correct config.
     *
     * COUNTERFACTUAL: assert audioTool differs from videoTool to prove neither is a stub.
     */
    @Test
    @Order(2)
    void test_audio_tool_basic_properties() {
        ToolDef aud = MediaTools.audioTool(
            "e2e_s16_audio",
            "TTS.",
            "openai",
            "tts-1");

        assertEquals("generate_audio", aud.getToolType(),
            "audio tool toolType should be 'generate_audio'. Got: " + aud.getToolType());
        Map<String, Object> config = aud.getConfig();
        assertEquals("tts-1", config.get("model"),
            "config.model should be 'tts-1'. Got: " + config.get("model"));
        assertEquals("GENERATE_AUDIO", config.get("taskType"),
            "config.taskType should be 'GENERATE_AUDIO'. Got: " + config.get("taskType"));

        // Counterfactual: audio vs video must differ.
        ToolDef vid = MediaTools.videoTool(
            "e2e_s16_audio_contrast_video",
            "Video.",
            "openai",
            "sora-2");
        assertNotEquals(aud.getToolType(), vid.getToolType(),
            "audioTool and videoTool must have DIFFERENT toolTypes. "
            + "COUNTERFACTUAL: a stub would make both identical.");
    }

    /**
     * videoTool produces toolType=generate_video.
     *
     * COUNTERFACTUAL: assert pdfTool differs to confirm.
     */
    @Test
    @Order(3)
    void test_video_tool_basic_properties() {
        ToolDef vid = MediaTools.videoTool(
            "e2e_s16_video",
            "Video gen.",
            "openai",
            "sora-2");
        assertEquals("generate_video", vid.getToolType(),
            "video tool toolType should be 'generate_video'. Got: " + vid.getToolType());
        assertEquals("GENERATE_VIDEO", vid.getConfig().get("taskType"),
            "config.taskType should be 'GENERATE_VIDEO'. Got: " + vid.getConfig().get("taskType"));

        ToolDef pdf = MediaTools.pdfTool();
        assertNotEquals(vid.getToolType(), pdf.getToolType(),
            "videoTool and pdfTool must have DIFFERENT toolTypes. "
            + "COUNTERFACTUAL: a stub would collapse them.");
    }

    /**
     * pdfTool produces toolType=generate_pdf.
     *
     * COUNTERFACTUAL: confirm input schema requires 'markdown' — contrast with images
     * which require 'prompt'.
     */
    @Test
    @Order(4)
    @SuppressWarnings("unchecked")
    void test_pdf_tool_basic_properties() {
        ToolDef pdf = MediaTools.pdfTool();
        assertEquals("generate_pdf", pdf.getToolType(),
            "pdf tool toolType should be 'generate_pdf'. Got: " + pdf.getToolType());
        assertEquals("GENERATE_PDF", pdf.getConfig().get("taskType"),
            "config.taskType should be 'GENERATE_PDF'. Got: " + pdf.getConfig().get("taskType"));

        // Required field check — pdf requires 'markdown'
        Map<String, Object> schema = pdf.getInputSchema();
        List<String> required = (List<String>) schema.get("required");
        assertNotNull(required, "pdf inputSchema.required is null");
        assertTrue(required.contains("markdown"),
            "pdf required must include 'markdown'. Got: " + required);
        assertFalse(required.contains("prompt"),
            "pdf required must NOT include 'prompt' (that's for image). Got: " + required
            + ". COUNTERFACTUAL: if the schema is shared/cloned, prompt would leak in.");

        // Contrast with image's required field
        ToolDef img = MediaTools.imageTool("e2e_s16_pdf_contrast_img", "img", "openai", "dall-e-3");
        Map<String, Object> imgSchema = img.getInputSchema();
        List<String> imgRequired = (List<String>) imgSchema.get("required");
        assertNotNull(imgRequired, "image inputSchema.required is null");
        assertTrue(imgRequired.contains("prompt"),
            "image required should include 'prompt'. Got: " + imgRequired);
        assertNotEquals(required, imgRequired,
            "pdf and image required lists must differ. Got pdf=" + required + " img=" + imgRequired
            + ". COUNTERFACTUAL: if schemas leak, both would be identical.");
    }

    /**
     * Plan compilation: an image tool serializes into agentDef.tools with the correct
     * toolType and llmProvider/model in config.
     *
     * COUNTERFACTUAL: A different model in config implies the field isn't a fixed string.
     */
    @Test
    @Order(5)
    @SuppressWarnings("unchecked")
    void test_media_tools_serialize_to_plan_with_distinct_models() {
        ToolDef img = MediaTools.imageTool(
            "e2e_s16_plan_image",
            "Image.",
            "openai",
            "dall-e-3");
        ToolDef gemImg = MediaTools.imageTool(
            "e2e_s16_plan_gem_image",
            "Image gemini.",
            "google_gemini",
            "imagen-3.0-generate-002");
        ToolDef aud = MediaTools.audioTool(
            "e2e_s16_plan_audio",
            "Audio.",
            "openai",
            "tts-1");

        Agent agent = Agent.builder()
            .name("e2e_s16_plan_agent")
            .model(MODEL)
            .instructions("Generate media.")
            .tools(List.of(img, gemImg, aud))
            .build();

        Map<String, Object> agentDef = getAgentDef(runtime.plan(agent));

        Map<String, Object> imgPlan = findToolByName(agentDef, "e2e_s16_plan_image");
        Map<String, Object> gemPlan = findToolByName(agentDef, "e2e_s16_plan_gem_image");
        Map<String, Object> audPlan = findToolByName(agentDef, "e2e_s16_plan_audio");

        assertEquals("generate_image", imgPlan.get("toolType"),
            "Image plan toolType wrong. Got: " + imgPlan.get("toolType"));
        assertEquals("generate_image", gemPlan.get("toolType"),
            "Gemini-image plan toolType wrong. Got: " + gemPlan.get("toolType"));
        assertEquals("generate_audio", audPlan.get("toolType"),
            "Audio plan toolType wrong. Got: " + audPlan.get("toolType")
            + ". COUNTERFACTUAL: if every media tool serialized as 'generate_image', this would fail.");

        Map<String, Object> imgConfig = (Map<String, Object>) imgPlan.get("config");
        Map<String, Object> gemConfig = (Map<String, Object>) gemPlan.get("config");
        assertEquals("dall-e-3", imgConfig.get("model"),
            "OpenAI image model wrong. Got: " + imgConfig.get("model"));
        assertEquals("imagen-3.0-generate-002", gemConfig.get("model"),
            "Gemini image model wrong. Got: " + gemConfig.get("model"));
        assertNotEquals(imgConfig.get("model"), gemConfig.get("model"),
            "OpenAI vs Gemini models must differ in plan. "
            + "COUNTERFACTUAL: if config.model were dropped or shared, both would match.");
        assertNotEquals(imgConfig.get("llmProvider"), gemConfig.get("llmProvider"),
            "OpenAI vs Gemini providers must differ. Got both='" + imgConfig.get("llmProvider") + "'.");
    }

    /**
     * Counterfactual: an agent without any media tools has NO generate_* toolType in plan.
     *
     * Proves the previous tests would fail if media toolTypes were always emitted by the
     * serializer regardless of input.
     */
    @Test
    @Order(6)
    @SuppressWarnings("unchecked")
    void test_no_media_tool_means_no_generate_in_plan() {
        ToolDef worker = ToolDef.builder()
            .name("e2e_s16_no_media_worker")
            .description("worker")
            .inputSchema(Map.of("type", "object", "properties", Map.of()))
            .toolType("worker")
            .func(input -> input)
            .build();

        Agent agent = Agent.builder()
            .name("e2e_s16_no_media_agent")
            .model(MODEL)
            .instructions("No media.")
            .tools(List.of(worker))
            .build();

        Map<String, Object> agentDef = getAgentDef(runtime.plan(agent));
        List<Map<String, Object>> tools = (List<Map<String, Object>>) agentDef.get("tools");
        assertNotNull(tools, "tools null");

        boolean anyMedia = tools.stream()
            .map(t -> (String) t.get("toolType"))
            .anyMatch(tt -> tt != null && tt.startsWith("generate_"));
        assertFalse(anyMedia,
            "Plan must not have generate_* toolType when no media tool was added. Got: "
            + tools.stream().map(t -> t.get("name") + "[" + t.get("toolType") + "]").collect(Collectors.toList())
            + ". COUNTERFACTUAL: if media types are always emitted, all plans would have them.");
    }
}
