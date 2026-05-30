// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.exceptions;

/**
 * Credential resolution service returned 5xx or was unreachable.
 *
 * <p>Treated as fatal — no env-var fallback. Mirrors Python's
 * {@code CredentialServiceError}.</p>
 */
public class CredentialServiceException extends AgentspanException {

    private final int statusCode;

    public CredentialServiceException(int statusCode, String detail) {
        super("Credential service error (HTTP " + statusCode + "): " + detail);
        this.statusCode = statusCode;
    }

    public int getStatusCode() {
        return statusCode;
    }
}
