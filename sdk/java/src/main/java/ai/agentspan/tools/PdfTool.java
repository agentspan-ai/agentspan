// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.tools;

import ai.agentspan.model.ToolDef;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Factory for the server-side PDF-generation tool (Conductor {@code GENERATE_PDF} task).
 *
 * <p>Mirrors the Python SDK's {@code pdf_tool()} factory. No worker process or AI
 * provider is needed — the Conductor server converts markdown to PDF directly.
 * Supports GitHub Flavored Markdown including headings, tables, code blocks,
 * lists, blockquotes, images, and links.
 *
 * <p>The LLM decides <em>when</em> to call this tool and provides the
 * {@code markdown} parameter. Static parameters like {@code pageSize} and
 * {@code theme} can be baked in via the {@code defaults} map.
 *
 * <p>Example:
 * <pre>{@code
 * ToolDef pdf = PdfTool.create();
 *
 * Agent agent = Agent.builder()
 *     .name("report_writer")
 *     .model("openai/gpt-4o")
 *     .tools(List.of(pdf))
 *     .instructions("Write reports and generate PDFs.")
 *     .build();
 * }</pre>
 */
public class PdfTool {

    private PdfTool() {}

    /** Create a PDF-generation tool with default name, description, and schema. */
    public static ToolDef create() {
        return create("generate_pdf", "Generate a PDF document from markdown text.", null, null);
    }

    /** Create a PDF-generation tool with a custom name and description. */
    public static ToolDef create(String name, String description) {
        return create(name, description, null, null);
    }

    /** Create a PDF-generation tool with a custom name, description, and input schema. */
    public static ToolDef create(String name, String description, Map<String, Object> inputSchema) {
        return create(name, description, inputSchema, null);
    }

    /**
     * Create a PDF-generation tool with full customisation.
     *
     * @param name           Tool name shown to the LLM.
     * @param description    Human-readable description for the LLM.
     * @param inputSchema    JSON Schema for LLM-provided parameters. If {@code null},
     *                       a default schema with {@code markdown}, {@code pageSize},
     *                       {@code theme}, and {@code baseFontSize} is used.
     * @param defaults       Extra static parameters baked into the generation task
     *                       (e.g. {@code pageSize="LETTER"}, {@code theme="compact"}).
     *                       May be {@code null}.
     */
    public static ToolDef create(String name, String description,
            Map<String, Object> inputSchema, Map<String, Object> defaults) {
        var schema = inputSchema != null ? inputSchema : defaultInputSchema();

        var config = new LinkedHashMap<String, Object>();
        config.put("taskType", "GENERATE_PDF");
        if (defaults != null) {
            config.putAll(defaults);
        }

        return ToolDef.builder()
                .name(name)
                .description(description)
                .inputSchema(schema)
                .toolType("generate_pdf")
                .config(config)
                .build();
    }

    private static Map<String, Object> defaultInputSchema() {
        var schema = new LinkedHashMap<String, Object>();
        schema.put("type", "object");

        var props = new LinkedHashMap<String, Object>();
        props.put("markdown", prop("string", "Markdown text to convert to PDF.", null));
        props.put("pageSize", prop("string", "Page size: A4, LETTER, LEGAL, A3, or A5.", "A4"));
        props.put("theme", prop("string", "Style preset: 'default' or 'compact'.", "default"));
        props.put("baseFontSize", prop("number", "Base font size in points.", 11));

        schema.put("properties", props);
        schema.put("required", List.of("markdown"));
        return schema;
    }

    private static Map<String, Object> prop(String type, String description, Object defaultValue) {
        var p = new LinkedHashMap<String, Object>();
        p.put("type", type);
        p.put("description", description);
        if (defaultValue != null) {
            p.put("default", defaultValue);
        }
        return p;
    }
}
