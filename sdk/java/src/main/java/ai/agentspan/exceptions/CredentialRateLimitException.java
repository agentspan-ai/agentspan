// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.exceptions;

/**
 * Rate limit hit on {@code POST /api/workers/secrets} (HTTP 429).
 *
 * <p>Non-retryable from the worker's perspective — reduce resolve frequency
 * or raise the server-side limit.</p>
 */
public class CredentialRateLimitException extends AgentspanException {
    public CredentialRateLimitException() {
        super("Credential resolution rate limit exceeded (HTTP 429). "
                + "Reduce resolve frequency or increase the server rate limit.");
    }
}
