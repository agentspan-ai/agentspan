// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.internal;

import java.util.Map;

/**
 * Internal per-call transport for resolved secrets, from {@code WorkerManager} (which
 * resolves declared credentials before invoking a handler) to {@code ToolRegistry}
 * (which snapshots them into the {@code ToolContext} it builds for the call).
 *
 * <p>Not part of the public API — tool code reads secrets via
 * {@code ToolContext.getCredential(...)}, never from here. A {@link ThreadLocal} is used
 * (rather than the input map) so secrets never enter task input/output that may be logged
 * or serialized. {@code WorkerManager} sets the context immediately before invoking the
 * handler and clears it in a {@code finally}, on the same worker thread; concurrent worker
 * threads therefore see independent contexts and cannot leak across each other.
 */
public final class CredentialContext {

    private static final ThreadLocal<Map<String, String>> CURRENT = new ThreadLocal<>();

    private CredentialContext() {}

    /** Establish the per-call secret context (no-op clear when empty/null). */
    public static void set(Map<String, String> credentials) {
        if (credentials == null || credentials.isEmpty()) {
            CURRENT.remove();
        } else {
            CURRENT.set(Map.copyOf(credentials));
        }
    }

    /** Clear the per-call secret context. Always safe to call. */
    public static void clear() {
        CURRENT.remove();
    }

    /** The current call's resolved secrets, or an empty map if none. */
    public static Map<String, String> current() {
        Map<String, String> ctx = CURRENT.get();
        return ctx == null ? Map.of() : ctx;
    }
}
