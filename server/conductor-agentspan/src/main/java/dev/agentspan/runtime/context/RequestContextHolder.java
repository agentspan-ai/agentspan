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
 */
public final class RequestContextHolder {

    private static final ThreadLocal<RequestContext> HOLDER = new InheritableThreadLocal<>();

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
}
