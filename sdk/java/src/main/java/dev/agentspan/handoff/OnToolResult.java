// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.handoff;

/**
 * Triggers a handoff when a specific tool returns a result (optionally containing text).
 *
 * <p>Example:
 * <pre>{@code
 * OnToolResult.of("check_eligibility", "refund_specialist")
 * OnToolResult.of("check_eligibility", "refund_specialist", "eligible")
 * }</pre>
 */
public class OnToolResult extends Handoff {
    private final String toolName;
    private final String resultContains;

    public OnToolResult(String toolName, String target, String resultContains) {
        super(target);
        this.toolName = toolName;
        this.resultContains = resultContains;
    }

    public static OnToolResult of(String toolName, String target) {
        return new OnToolResult(toolName, target, null);
    }

    public static OnToolResult of(String toolName, String target, String resultContains) {
        return new OnToolResult(toolName, target, resultContains);
    }

    public String getToolName() { return toolName; }
    public String getResultContains() { return resultContains; }
}
