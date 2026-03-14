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

import java.util.List;
import java.util.Map;

/**
 * Tool definition DTO.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class ToolConfig {

    private String name;
    private String description;
    private Map<String, Object> inputSchema;
    private Map<String, Object> outputSchema;

    /**
     * Tool type: worker, http, mcp, generate_image, generate_audio, generate_video,
     * generate_pdf, rag_index, rag_search.
     */
    @Builder.Default
    private String toolType = "worker";

    @Builder.Default
    private boolean approvalRequired = false;

    private Integer timeoutSeconds;

    /** Type-specific configuration (e.g., server_url for MCP, url/method/headers for HTTP). */
    private Map<String, Object> config;

    /** Tool-level guardrails. */
    private List<GuardrailConfig> guardrails;
}
