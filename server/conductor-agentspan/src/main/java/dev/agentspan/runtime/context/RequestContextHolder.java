/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.context;

import java.util.Optional;

/**
 * ThreadLocal wrapper for {@link RequestContext}.
 *
 * <p>Set by the host at the start of each request (the standalone server's {@code AuthFilter},
 * or an embedding application's security adapter) and cleared in a finally block. Read anywhere
 * in the call stack via {@link #get()} or {@link #getRequiredUserId()}.
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
     * Convenience accessor for the current principal id — throws if no context is set.
     * Use in service code where a request context is guaranteed by the host's filter.
     */
    public static String getRequiredUserId() {
        return get().map(RequestContext::getUserId)
                .orElseThrow(() -> new IllegalStateException(
                        "No RequestContext on this thread — context filter may not have run"));
    }
}
