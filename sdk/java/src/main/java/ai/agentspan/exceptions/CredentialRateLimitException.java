// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.exceptions;

/** Rate limit exceeded on credential resolve (HTTP 429). Do not fall back to env vars. */
public class CredentialRateLimitException extends AgentspanException {
    public CredentialRateLimitException() {
        super("Credential resolution rate limit exceeded (429). "
            + "Reduce resolve call frequency or increase the server rate limit.");
    }
}
