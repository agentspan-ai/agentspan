/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.context;

import java.time.Instant;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Per-request principal context stored in a ThreadLocal for the duration of each request.
 *
 * <p>Carries the resolved {@code userId} used for per-user secret scoping. AgentSpan defines
 * no identity model of its own — the host populates this: the standalone server's
 * {@code AuthFilter} sets an anonymous id, while an embedding application (e.g. orkes-conductor)
 * supplies its own principal id.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class RequestContext {
    private String requestId; // UUID per HTTP request
    private String executionId; // populated when request is execution-scoped
    private String userId; // resolved principal id, for per-user secret scoping
    private Instant createdAt;
}
