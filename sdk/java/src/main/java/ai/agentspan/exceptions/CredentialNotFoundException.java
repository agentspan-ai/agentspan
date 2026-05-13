// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.exceptions;

/**
 * Thrown when a required credential is not found.
 */
public class CredentialNotFoundException extends AgentspanException {
    private final String credentialName;

    public CredentialNotFoundException(String name) {
        super("Credential not found: " + name);
        this.credentialName = name;
    }

    public String getCredentialName() {
        return credentialName;
    }
}
