// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.credentials;

import dev.agentspan.exceptions.CredentialNotFoundException;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Credential accessor for worker tool functions.
 *
 * <p>The worker framework calls {@link #setCredentialContext(Map)} before executing a tool,
 * making credentials available via {@link #getCredential(String)} inside the call frame.
 *
 * <p>Uses {@link ThreadLocal} so each worker thread has its own independent context.
 *
 * <pre>{@code
 * // Inside a @Tool function declared with credentials={"OPENAI_API_KEY"}:
 * String apiKey = Credentials.getCredential("OPENAI_API_KEY");
 * }</pre>
 */
public class Credentials {

    private static final ThreadLocal<Map<String, String>> CONTEXT = new ThreadLocal<>();

    private Credentials() {}

    /** Set the credential context for the current thread. Called by the worker framework. */
    public static void setCredentialContext(Map<String, String> credentials) {
        CONTEXT.set(credentials != null ? new HashMap<>(credentials) : null);
    }

    /** Clear the credential context for the current thread. Called by the worker framework. */
    public static void clearCredentialContext() {
        CONTEXT.remove();
    }

    /**
     * Read a credential value from the current thread's execution context.
     *
     * <p>Only usable inside tool functions executed by the worker framework.
     *
     * @param name the logical credential name (e.g. {@code "OPENAI_API_KEY"})
     * @return the plaintext credential value
     * @throws CredentialNotFoundException if the credential is not in the current context
     */
    public static String getCredential(String name) {
        Map<String, String> ctx = CONTEXT.get();
        if (ctx == null || !ctx.containsKey(name)) {
            throw new CredentialNotFoundException(name);
        }
        return ctx.get(name);
    }

    /**
     * Batch-resolve credentials from Conductor task input data.
     *
     * <p>Extracts the execution token from {@code __agentspan_ctx__} in the task input
     * and returns a map of credential name to resolved value.
     *
     * @param inputData    the Conductor task's input data map
     * @param names        credential names to resolve
     * @return map of credential name to resolved value
     */
    public static Map<String, String> resolveCredentials(Map<String, Object> inputData, List<String> names) {
        Map<String, String> result = new HashMap<>();
        Map<String, String> ctx = CONTEXT.get();
        if (ctx != null) {
            for (String name : names) {
                if (ctx.containsKey(name)) result.put(name, ctx.get(name));
            }
        }
        return result;
    }
}
