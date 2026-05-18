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
     * Tool type: worker, http, api, mcp, generate_image, generate_audio, generate_video,
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

    /**
     * When {@code true}, this tool's worker is registered under a per-execution
     * domain so concurrent executions of the same agent cannot steal each other's
     * task results.  Matches {@code @tool(stateful=True)} in the Python SDK.
     */
    private boolean stateful;
}
