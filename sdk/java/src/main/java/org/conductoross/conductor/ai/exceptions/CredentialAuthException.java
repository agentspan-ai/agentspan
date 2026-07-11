// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.exceptions;

/**
 * Credential access rejected (unauthorized).
 *
 * <p>Non-retryable. Token has expired, been revoked, or is structurally
 * invalid. Mirrors Python's {@code CredentialAuthError}.</p>
 */
public class CredentialAuthException extends AgentspanException {
    public CredentialAuthException(String detail) {
        super("Credential authentication failed (token expired or revoked): " + detail);
    }
}
