/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.auth;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import java.time.Instant;

/**
 * Per-request context stored in ThreadLocal for the duration of each request.
 * Makes auth identity available throughout the call stack without explicit passing.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class RequestContext {
    private String  requestId;      // UUID per HTTP request
    private String  workflowId;     // populated when request is workflow-scoped
    private String  executionToken; // minted execution token, if present
    private User    user;
    private Instant createdAt;
}
