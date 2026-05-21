/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.ai;

/**
 * Recognises authentication failures from upstream LLM providers and
 * formats a clear, actionable error message.
 *
 * <p>The fail-fast in {@link AgentspanAIModelProvider#getModel} catches the
 * "empty key at JVM startup" case. This mapper handles the harder case: a
 * non-empty but invalid key (typo, expired, revoked) where the only signal
 * is a 401 returned by the provider's HTTP endpoint, often surfaced as a
 * {@code NonTransientAiException} mid-stream with the generic message
 * "cannot retry due to server authentication".</p>
 */
final class AuthErrorMessageMapper {

    private AuthErrorMessageMapper() {}

    /**
     * Return true if the throwable (or any cause in its chain) looks like a
     * provider authentication failure. Matches "401", "Unauthorized", and
     * "invalid_api_key" / "invalid api key" in the message text.
     */
    static boolean isAuthFailure(Throwable t) {
        Throwable cur = t;
        while (cur != null) {
            String msg = cur.getMessage();
            if (msg != null) {
                String lower = msg.toLowerCase();
                if (lower.contains("401")
                        || lower.contains("unauthorized")
                        || lower.contains("invalid_api_key")
                        || lower.contains("invalid api key")) {
                    return true;
                }
            }
            cur = cur.getCause();
        }
        return false;
    }

    /**
     * Build a user-facing error message naming the provider, the env var,
     * and the three remediation paths (env, credentials API, UI).
     */
    static String buildMessage(String provider, String envVar) {
        return "Provider rejected the API key for '"
                + provider
                + "' (401). "
                + envVar
                + " is set but invalid, expired, or revoked. "
                + "Update "
                + envVar
                + " in the server's environment and restart, "
                + "push a fresh value via PUT /api/credentials/"
                + envVar
                + ", or save it via the Credentials UI.";
    }
}
