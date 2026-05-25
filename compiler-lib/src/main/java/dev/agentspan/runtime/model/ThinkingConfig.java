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
 * Configuration for extended thinking/reasoning mode.
 * When enabled, the LLM uses a thinking budget to reason step-by-step.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class ThinkingConfig {

    @Builder.Default
    private boolean enabled = true;

    /** Maximum number of tokens the LLM can use for thinking. */
    private Integer budgetTokens;
}
