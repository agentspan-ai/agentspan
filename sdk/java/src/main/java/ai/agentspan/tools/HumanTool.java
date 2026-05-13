// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.tools;

import ai.agentspan.model.ToolDef;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Factory for a tool that pauses execution for human input (Conductor {@code HUMAN} task).
 *
 * <p>No worker process is needed. The Conductor server presents the LLM's arguments to a human
 * operator and the human's response is returned as the tool output.
 *
 * <pre>{@code
 * ToolDef ask = HumanTool.create(
 *     "ask_user", "Ask the user a question and wait for their response.");
 * }</pre>
 */
public class HumanTool {

    private HumanTool() {}

    /** Create a human-input tool with a default {@code question} input field. */
    public static ToolDef create(String name, String description) {
        return create(name, description, null);
    }

    /**
     * Create a human-input tool with a custom input schema.
     *
     * @param name        tool name shown to the LLM
     * @param description tool description shown to the LLM (also shown to the human operator)
     * @param inputSchema custom JSON Schema for the LLM-provided parameters;
     *                    if {@code null}, a default schema with a {@code question} field is used
     */
    public static ToolDef create(String name, String description, Map<String, Object> inputSchema) {
        if (inputSchema == null) {
            Map<String, Object> questionProp = new LinkedHashMap<>();
            questionProp.put("type", "string");
            questionProp.put("description", "The question or prompt to present to the human.");

            Map<String, Object> props = new LinkedHashMap<>();
            props.put("question", questionProp);

            inputSchema = new LinkedHashMap<>();
            inputSchema.put("type", "object");
            inputSchema.put("properties", props);
            inputSchema.put("required", List.of("question"));
        }
        return ToolDef.builder()
                .name(name)
                .description(description)
                .inputSchema(inputSchema)
                .toolType("human")
                .build();
    }
}
