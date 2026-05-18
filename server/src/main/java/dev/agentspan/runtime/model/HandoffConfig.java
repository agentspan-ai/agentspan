/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.model;

import com.fasterxml.jackson.annotation.JsonInclude;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Handoff condition DTO for swarm strategy.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class HandoffConfig {

    /** Handoff type: on_tool_result, on_text_mention, on_condition. */
    private String type;

    /** Target agent name. */
    private String target;

    // --- on_tool_result ---
    private String toolName;
    private String resultContains;

    // --- on_text_mention ---
    private String text;

    // --- on_condition (worker-based) ---
    /** Task name for the condition evaluation worker. */
    private String taskName;
}
