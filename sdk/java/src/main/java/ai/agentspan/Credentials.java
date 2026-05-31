// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan;

import ai.agentspan.exceptions.CredentialNotFoundException;

import java.util.Collections;
import java.util.Map;

/**
 * Thread-local accessor for resolved secrets — the only safe way to read
 * declared credentials inside a {@code @Tool} method.
 *
 * <p>Java is tier-1-only by design. {@code System.getenv()} returns an
 * immutable map at JVM start, so AgentSpan cannot inject env vars at
 * runtime the way Python's {@code os.environ}-mutation works. Tool code
 * must read its declared credentials via this accessor:</p>
 *
 * <pre>
 *   {@literal @}Tool(credentials = {"OPENAI_API_KEY"})
 *   public String chat(String prompt) {
 *       String key = Credentials.get("OPENAI_API_KEY");
 *       OpenAIClient client = new OpenAIClient(key);
 *       ...
 *   }
 * </pre>
 *
 * <p>The worker framework calls {@link #setForCall} immediately before
 * invoking the user's handler and {@link #clearForCall} in a {@code finally}
 * block after the call returns. The accessor is thread-local — concurrent
 * worker threads see independent secret contexts and cannot leak across
 * each other.</p>
 *
 * <p>See {@code docs/design/secret-injection-contract.md} for the full
 * cross-SDK contract. Java's design corresponds to Python's contextvars
 * accessor and .NET's per-call IToolContext — all tier-1 explicit-key.</p>
 */
public final class Credentials {

    private static final ThreadLocal<Map<String, String>> CURRENT =
            new ThreadLocal<>();

    private Credentials() {
        // static-only utility
    }

    /**
     * Read a resolved secret value by name.
     *
     * @param name the credential name declared in {@code @Tool(credentials = {...})}
     * @return the plaintext value
     * @throws CredentialNotFoundException if no secret context is set
     *         (called outside a {@code @Tool} method) or the name was not
     *         declared / not resolved
     */
    public static String get(String name) {
        Map<String, String> ctx = CURRENT.get();
        if (ctx == null) {
            throw new CredentialNotFoundException(
                    "Credentials.get(\"" + name + "\") called outside a credential-aware "
                            + "@Tool method. Either the calling code isn't a worker, or "
                            + "the tool was invoked without going through WorkerManager.");
        }
        String value = ctx.get(name);
        if (value == null) {
            throw new CredentialNotFoundException(name);
        }
        return value;
    }

    /**
     * Read a resolved secret value, or {@code null} when the secret context
     * isn't set / the name isn't present. Use this when you want to fall
     * back gracefully instead of failing the tool.
     */
    public static String getOrNull(String name) {
        Map<String, String> ctx = CURRENT.get();
        if (ctx == null) return null;
        return ctx.get(name);
    }

    /**
     * Return a read-only view of the current call's resolved secrets.
     * Empty map if no context is set.
     */
    public static Map<String, String> all() {
        Map<String, String> ctx = CURRENT.get();
        return ctx == null ? Collections.emptyMap() : Collections.unmodifiableMap(ctx);
    }

    // ── Worker-framework hooks (not for application code) ────────────────

    /**
     * Establish the per-call secret context. Called by {@code WorkerManager}
     * immediately before invoking a {@code @Tool} method. The handler runs
     * in the same thread, so {@code ThreadLocal} reaches it.
     */
    public static void setForCall(Map<String, String> credentials) {
        if (credentials == null || credentials.isEmpty()) {
            CURRENT.remove();
        } else {
            CURRENT.set(Map.copyOf(credentials));
        }
    }

    /**
     * Clear the per-call secret context. Called by {@code WorkerManager} in
     * a {@code finally} block. Always safe to call even if no context was set.
     */
    public static void clearForCall() {
        CURRENT.remove();
    }
}
