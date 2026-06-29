// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.model;

import java.util.Collections;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Response from {@code POST /api/agent/compile}.
 *
 * <p>Returned by {@link org.conductoross.conductor.ai.AgentRuntime#plan(org.conductoross.conductor.ai.Agent)}.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public final class CompileResponse {

    @JsonProperty("workflowDef")
    private Map<String, Object> workflowDef;

    @JsonProperty("requiredWorkers")
    private List<String> requiredWorkers;

    public CompileResponse() {}

    /** The compiled Conductor workflow definition. */
    public Map<String, Object> getWorkflowDef() {
        return workflowDef != null ? workflowDef : Collections.emptyMap();
    }

    /**
     * Task type names the SDK must register local workers for before the agent
     * can make progress. The SDK handles this automatically inside
     * {@link org.conductoross.conductor.ai.AgentRuntime#run}.
     */
    public List<String> getRequiredWorkers() {
        return requiredWorkers != null ? requiredWorkers : Collections.emptyList();
    }

    @Override
    public String toString() {
        return "CompileResponse{requiredWorkers=" + getRequiredWorkers() + "}";
    }
}
