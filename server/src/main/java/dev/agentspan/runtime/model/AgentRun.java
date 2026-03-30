/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.model;

import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.annotation.JsonInclude;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Full details of a single agent execution.
 *
 * <p>Returned by {@code GET /api/agent/{id}}.  Combines execution metadata,
 * the full task list (for sub-workflow traversal by the SDK), and pre-computed
 * token usage for this execution level.</p>
 *
 * <p>Token usage covers only LLM tasks in <em>this</em> execution.  The SDK
 * aggregates across the full sub-agent tree by recursively fetching each
 * {@code SUB_WORKFLOW} task's {@code subWorkflowId}.</p>
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class AgentRun {

    private String executionId;
    private String agentName;
    private int version;
    private String status;
    private long startTime;
    private long endTime;
    private Map<String, Object> input;
    private Map<String, Object> output;

    /** Token usage for LLM tasks in this execution only — null if none ran. */
    private TokenUsage tokenUsage;

    /** All tasks in this execution. */
    private List<TaskDetail> tasks;

    // ── Inner types ──────────────────────────────────────────────────────────

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public static class TokenUsage {
        private int promptTokens;
        private int completionTokens;
        private int totalTokens;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public static class TaskDetail {
        private String taskType;
        private String referenceTaskName;
        private String status;
        /** Populated for {@code SUB_WORKFLOW} tasks — the child workflow ID. */
        private String subWorkflowId;

        private Map<String, Object> outputData;
    }
}
