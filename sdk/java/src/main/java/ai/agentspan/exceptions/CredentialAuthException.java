// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.exceptions;

/**
 * Execution token rejected by {@code POST /api/workers/secrets} (HTTP 401).
 *
 * <p>Non-retryable. Token has expired, been revoked, or is structurally
 * invalid. Mirrors Python's {@code CredentialAuthError}.</p>
 */
public class CredentialAuthException extends AgentspanException {
    public CredentialAuthException(String detail) {
        super("Credential authentication failed (token expired or revoked): " + detail);
    }
}
