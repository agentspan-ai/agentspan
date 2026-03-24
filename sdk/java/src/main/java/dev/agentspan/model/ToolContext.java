// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.model;

/**
 * Context passed to tool functions during execution.
 */
public class ToolContext {
    private final String sessionId;
    private final String workflowId;
    private final String taskId;

    public ToolContext(String sessionId, String workflowId, String taskId) {
        this.sessionId = sessionId;
        this.workflowId = workflowId;
        this.taskId = taskId;
    }

    public String getSessionId() {
        return sessionId;
    }

    public String getWorkflowId() {
        return workflowId;
    }

    public String getTaskId() {
        return taskId;
    }
}
