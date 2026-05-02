// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.model;

import java.util.HashMap;
import java.util.Map;

/**
 * Context passed to tool functions during execution.
 *
 * <p>{@link #getState()} provides a mutable dictionary that persists across all tool
 * calls within the same agent execution. Tools can read and write to it to share
 * data without relying on the LLM to relay state (mirrors Python SDK's
 * {@code ToolContext.state}).
 */
public class ToolContext {
    private final String sessionId;
    private final String workflowId;
    private final String taskId;
    private final Map<String, Object> state;

    public ToolContext(String sessionId, String workflowId, String taskId) {
        this(sessionId, workflowId, taskId, new HashMap<>());
    }

    public ToolContext(String sessionId, String workflowId, String taskId, Map<String, Object> initialState) {
        this.sessionId = sessionId;
        this.workflowId = workflowId;
        this.taskId = taskId;
        this.state = initialState != null ? new HashMap<>(initialState) : new HashMap<>();
    }

    public String getSessionId() { return sessionId; }
    public String getWorkflowId() { return workflowId; }
    public String getTaskId() { return taskId; }

    /**
     * Shared state dictionary persisted across tool calls within the same agent execution.
     * Mutate this map to pass data to subsequent tool calls.
     */
    public Map<String, Object> getState() { return state; }
}
