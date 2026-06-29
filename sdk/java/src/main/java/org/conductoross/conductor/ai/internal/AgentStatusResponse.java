// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.internal;

import java.util.Map;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Response from {@code GET /api/agent/{executionId}/status}.
 *
 * <p>Polled by {@link org.conductoross.conductor.ai.model.AgentHandle} until the
 * execution reaches a terminal status. Used internally — callers receive an
 * {@link org.conductoross.conductor.ai.model.AgentResult} after completion.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public final class AgentStatusResponse {

    @JsonProperty("executionId")
    private String executionId;

    @JsonProperty("status")
    private String status;

    @JsonProperty("isComplete")
    private boolean complete;

    @JsonProperty("isRunning")
    private boolean running;

    @JsonProperty("isWaiting")
    private boolean waiting;

    @JsonProperty("output")
    private Map<String, Object> output;

    @JsonProperty("reasonForIncompletion")
    private String reasonForIncompletion;

    @JsonProperty("pendingTool")
    private PendingTool pendingTool;

    public AgentStatusResponse() {}

    public String getExecutionId() {
        return executionId;
    }

    /**
     * Conductor workflow status string: {@code RUNNING}, {@code COMPLETED},
     * {@code FAILED}, {@code TERMINATED}, {@code TIMED_OUT}, {@code PAUSED}.
     */
    public String getStatus() {
        return status;
    }

    /** {@code true} when status is terminal (COMPLETED, FAILED, TERMINATED, TIMED_OUT). */
    public boolean isComplete() {
        return complete;
    }

    public boolean isRunning() {
        return running;
    }

    /** {@code true} when a HITL task is paused waiting for human input. */
    public boolean isWaiting() {
        return waiting;
    }

    /**
     * Final workflow output. Only present when {@link #isComplete()} is {@code true}.
     */
    public Map<String, Object> getOutput() {
        return output;
    }

    /**
     * Failure or termination reason. Only present for non-COMPLETED terminal runs.
     */
    public String getReasonForIncompletion() {
        return reasonForIncompletion;
    }

    /**
     * Details of the paused HITL task. Only present when {@link #isWaiting()} is {@code true}.
     */
    public PendingTool getPendingTool() {
        return pendingTool;
    }

    @Override
    public String toString() {
        return "AgentStatusResponse{executionId=" + executionId + ", status=" + status + ", complete=" + complete
                + ", waiting=" + waiting + "}";
    }
}
