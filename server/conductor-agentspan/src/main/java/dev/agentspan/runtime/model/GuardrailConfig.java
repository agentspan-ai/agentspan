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
 * Guardrail definition DTO.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class GuardrailConfig {

    private String name;

    /** Guardrail type: regex, llm, custom, external. */
    private String guardrailType;

    /** Position: input or output. */
    @Builder.Default
    private String position = "output";

    /** Action on failure: retry, raise, fix, human. */
    @Builder.Default
    private String onFail = "retry";

    @Builder.Default
    private int maxRetries = 3;

    // --- Regex-specific fields ---
    private List<String> patterns;

    /** Regex mode: block or allow. */
    private String mode;

    /** Custom failure message. */
    private String message;

    // --- LLM-specific fields ---
    private String model;
    private String policy;
    private Integer maxTokens;

    // --- Custom/External-specific fields ---
    /** Task name for custom @guardrail workers or external guardrails. */
    private String taskName;
}
