// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.exceptions;

/** Execution token is invalid, expired, or revoked (HTTP 401). Do not retry. */
public class CredentialAuthException extends AgentspanException {
    public CredentialAuthException(String detail) {
        super(detail != null && !detail.isEmpty()
            ? "Credential authentication failed (token expired or revoked): " + detail
            : "Credential authentication failed (token expired or revoked)");
    }
}
