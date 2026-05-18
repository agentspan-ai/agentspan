/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.model;

import java.util.List;

import com.fasterxml.jackson.annotation.JsonInclude;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Termination condition DTO. Supports recursive AND/OR composites.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class TerminationConfig {

    /**
     * Condition type: text_mention, stop_message, max_message, token_usage, and, or.
     */
    private String type;

    // --- TextMentionTermination ---
    private String text;
    private Boolean caseSensitive;

    // --- StopMessageTermination ---
    private String stopMessage;

    // --- MaxMessageTermination ---
    private Integer maxMessages;

    // --- TokenUsageTermination ---
    private Integer maxTotalTokens;
    private Integer maxPromptTokens;
    private Integer maxCompletionTokens;

    // --- Composite (AND/OR) ---
    private List<TerminationConfig> conditions;
}
