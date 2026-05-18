/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.auth;

import java.util.Optional;

/**
 * ThreadLocal wrapper for RequestContext.
 *
 * <p>Set by AuthFilter at the start of each request.
 * Cleared by AuthFilter in a finally block.
 * Read anywhere in the call stack via get() or getRequiredUser().</p>
 */
public final class RequestContextHolder {

    private static final ThreadLocal<RequestContext> HOLDER = new ThreadLocal<>();

    private RequestContextHolder() {}

    public static void set(RequestContext ctx) {
        HOLDER.set(ctx);
    }

    public static Optional<RequestContext> get() {
        return Optional.ofNullable(HOLDER.get());
    }

    public static void clear() {
        HOLDER.remove();
    }

    /**
     * Convenience accessor — throws if no context is set.
     * Use in service code where authentication is guaranteed by the filter.
     */
    public static User getRequiredUser() {
        return get().map(RequestContext::getUser)
                .orElseThrow(() ->
                        new IllegalStateException("No RequestContext on this thread — auth filter may not have run"));
    }
}
