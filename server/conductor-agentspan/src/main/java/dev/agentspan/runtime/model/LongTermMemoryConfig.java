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
 * Long-term (OCG-backed) memory configuration DTO.
 *
 * <p>Emitted by the Python serializer when an {@code Agent} has a
 * {@code semantic_memory} backed by an {@code OCGMemoryStore}. Drives the
 * server-side compiler to inline memory retrieval (pre-loop) and
 * distill/save/feedback (post-loop) steps into the Conductor workflow, so
 * long-term memory works on the deployed/webhook execution path — not just
 * the client-side {@code run()} wrapper.
 *
 * <p>Unlike short-term {@link MemoryConfig} (pre-loaded conversation
 * messages), this drives HTTP calls to an OCG instance using a
 * server-resolvable credential name (never the client token).
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class LongTermMemoryConfig {

    /** Base URL of the OCG instance (no trailing slash). */
    private String ocgUrl;

    /**
     * Server-resolvable credential NAME (e.g. {@code "OCG_PUBLIC_KEY"}) for the
     * OCG bearer token. Resolved server-side via the {@code #{NAME}} placeholder
     * in HTTP task headers — never the raw client token.
     */
    private String credential;

    /** Agent owner / scope key, e.g. {@code "agent:ce-ticket-resolution"}. */
    private String agent;

    /** Optional user owner, e.g. {@code "user:alice"}. */
    private String user;

    /** Memory scope for writes (default {@code "agent"}). */
    private String scope;

    /** Max memories to retrieve per search. */
    private Integer maxResults;

    /** Model used by the distillation (memory summarizer) LLM step. */
    private String summaryModel;
}
