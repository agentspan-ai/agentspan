/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.model;

import java.util.Collections;
import java.util.Map;

/**
 * A tool call to execute before the LLM runs.
 *
 * <p>Passed to {@code Agent.Builder.prefillTools()} so the server executes these
 * tools before the first LLM turn and injects results into context.
 */
public class PrefillToolCall {
    private final String toolName;
    private final Map<String, Object> arguments;

    public PrefillToolCall(String toolName, Map<String, Object> arguments) {
        this.toolName = toolName;
        this.arguments = arguments != null ? arguments : Collections.emptyMap();
    }

    public String getToolName() { return toolName; }
    public Map<String, Object> getArguments() { return arguments; }

    /**
     * Create a PrefillToolCall from a tool name and arguments.
     */
    public static PrefillToolCall of(String toolName, Map<String, Object> arguments) {
        return new PrefillToolCall(toolName, arguments);
    }
}
