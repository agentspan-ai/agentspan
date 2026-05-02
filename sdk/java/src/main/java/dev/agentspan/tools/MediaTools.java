// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.tools;

import dev.agentspan.model.ToolDef;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Factory methods for server-side media generation tools.
 *
 * <p>Media tools run entirely on the Conductor server — no local worker process needed.
 *
 * <pre>{@code
 * ToolDef img = MediaTools.imageTool("generate_image", "Generate an image", "openai", "dall-e-3");
 * ToolDef tts = MediaTools.audioTool("speak", "Convert text to speech", "openai", "tts-1");
 * ToolDef vid = MediaTools.videoTool("make_video", "Generate a video", "openai", "sora-2");
 * ToolDef pdf = MediaTools.pdfTool();
 * }</pre>
 */
public class MediaTools {

    private MediaTools() {}

    /** Create an image-generation tool (Conductor {@code GENERATE_IMAGE} task). */
    public static ToolDef imageTool(String name, String description,
            String llmProvider, String model) {
        return imageTool(name, description, llmProvider, model, null);
    }

    /** Create an image-generation tool with a custom input schema. */
    public static ToolDef imageTool(String name, String description,
            String llmProvider, String model, Map<String, Object> inputSchema) {
        if (inputSchema == null) {
            inputSchema = new LinkedHashMap<>();
            inputSchema.put("type", "object");
            Map<String, Object> props = new LinkedHashMap<>();
            props.put("prompt", prop("string", "Text description of the image to generate."));
            props.put("style", prop("string", "Image style: 'vivid' or 'natural'."));
            props.put("width", intProp("Image width in pixels."));
            props.put("height", intProp("Image height in pixels."));
            props.put("size", prop("string", "Image size (e.g. '1024x1024')."));
            props.put("n", intProp("Number of images to generate."));
            props.put("outputFormat", prop("string", "Output format: 'png', 'jpg', or 'webp'."));
            inputSchema.put("properties", props);
            inputSchema.put("required", List.of("prompt"));
        }
        return mediaTool("generate_image", "GENERATE_IMAGE", name, description, llmProvider, model, inputSchema);
    }

    /** Create an audio / text-to-speech tool (Conductor {@code GENERATE_AUDIO} task). */
    public static ToolDef audioTool(String name, String description,
            String llmProvider, String model) {
        return audioTool(name, description, llmProvider, model, null);
    }

    /** Create an audio / text-to-speech tool with a custom input schema. */
    public static ToolDef audioTool(String name, String description,
            String llmProvider, String model, Map<String, Object> inputSchema) {
        if (inputSchema == null) {
            inputSchema = new LinkedHashMap<>();
            inputSchema.put("type", "object");
            Map<String, Object> props = new LinkedHashMap<>();
            props.put("text", prop("string", "Text to convert to speech."));
            Map<String, Object> voice = prop("string", "Voice to use.");
            voice.put("enum", Arrays.asList("alloy", "echo", "fable", "onyx", "nova", "shimmer"));
            props.put("voice", voice);
            props.put("speed", numProp("Speech speed multiplier (0.25 to 4.0)."));
            props.put("responseFormat", prop("string", "Audio format: 'mp3', 'wav', 'opus', 'aac', or 'flac'."));
            props.put("n", intProp("Number of audio outputs to generate."));
            inputSchema.put("properties", props);
            inputSchema.put("required", List.of("text"));
        }
        return mediaTool("generate_audio", "GENERATE_AUDIO", name, description, llmProvider, model, inputSchema);
    }

    /** Create a video-generation tool (Conductor {@code GENERATE_VIDEO} task). */
    public static ToolDef videoTool(String name, String description,
            String llmProvider, String model) {
        return videoTool(name, description, llmProvider, model, null);
    }

    /** Create a video-generation tool with a custom input schema. */
    public static ToolDef videoTool(String name, String description,
            String llmProvider, String model, Map<String, Object> inputSchema) {
        if (inputSchema == null) {
            inputSchema = new LinkedHashMap<>();
            inputSchema.put("type", "object");
            Map<String, Object> props = new LinkedHashMap<>();
            props.put("prompt", prop("string", "Text description of the video scene."));
            props.put("duration", intProp("Video duration in seconds."));
            props.put("width", intProp("Video width in pixels."));
            props.put("height", intProp("Video height in pixels."));
            props.put("fps", intProp("Frames per second."));
            props.put("outputFormat", prop("string", "Video format (e.g. 'mp4')."));
            props.put("style", prop("string", "Video style (e.g. 'cinematic', 'natural')."));
            props.put("aspectRatio", prop("string", "Aspect ratio (e.g. '16:9', '1:1')."));
            props.put("n", intProp("Number of videos to generate."));
            inputSchema.put("properties", props);
            inputSchema.put("required", List.of("prompt"));
        }
        return mediaTool("generate_video", "GENERATE_VIDEO", name, description, llmProvider, model, inputSchema);
    }

    /** Create a PDF-generation tool with default name/description (Conductor {@code GENERATE_PDF} task). */
    public static ToolDef pdfTool() {
        return pdfTool("generate_pdf", "Generate a PDF document from markdown text.", null);
    }

    /** Create a PDF-generation tool (Conductor {@code GENERATE_PDF} task). */
    public static ToolDef pdfTool(String name, String description, Map<String, Object> inputSchema) {
        if (inputSchema == null) {
            inputSchema = new LinkedHashMap<>();
            inputSchema.put("type", "object");
            Map<String, Object> props = new LinkedHashMap<>();
            props.put("markdown", prop("string", "Markdown text to convert to PDF."));
            props.put("pageSize", prop("string", "Page size: A4, LETTER, LEGAL, A3, or A5."));
            props.put("theme", prop("string", "Style preset: 'default' or 'compact'."));
            props.put("baseFontSize", numProp("Base font size in points."));
            inputSchema.put("properties", props);
            inputSchema.put("required", List.of("markdown"));
        }
        Map<String, Object> config = new LinkedHashMap<>();
        config.put("taskType", "GENERATE_PDF");
        return ToolDef.builder()
                .name(name)
                .description(description)
                .inputSchema(inputSchema)
                .toolType("generate_pdf")
                .config(config)
                .build();
    }

    private static ToolDef mediaTool(String toolType, String taskType,
            String name, String description,
            String llmProvider, String model,
            Map<String, Object> inputSchema) {
        Map<String, Object> config = new LinkedHashMap<>();
        config.put("taskType", taskType);
        config.put("llmProvider", llmProvider);
        config.put("model", model);
        return ToolDef.builder()
                .name(name)
                .description(description)
                .inputSchema(inputSchema)
                .toolType(toolType)
                .config(config)
                .build();
    }

    private static Map<String, Object> prop(String type, String description) {
        Map<String, Object> p = new LinkedHashMap<>();
        p.put("type", type);
        p.put("description", description);
        return p;
    }

    private static Map<String, Object> intProp(String description) {
        Map<String, Object> p = new LinkedHashMap<>();
        p.put("type", "integer");
        p.put("description", description);
        return p;
    }

    private static Map<String, Object> numProp(String description) {
        Map<String, Object> p = new LinkedHashMap<>();
        p.put("type", "number");
        p.put("description", description);
        return p;
    }
}
