// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.exceptions;

/** Credential service returned a 5xx error or is unreachable. Always fatal. */
public class CredentialServiceException extends AgentspanException {
    private final int statusCode;

    public CredentialServiceException(int statusCode, String detail) {
        super(detail != null && !detail.isEmpty()
            ? "Credential service error (HTTP " + statusCode + "): " + detail
            : "Credential service error (HTTP " + statusCode + ")");
        this.statusCode = statusCode;
    }

    public int getStatusCode() { return statusCode; }
}
