// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.exceptions;

import java.util.List;

/**
 * One or more declared credentials could not be resolved from the server.
 *
 * <p>Raised when a tool declares {@code credentials = {"X"}} but no value
 * for {@code X} exists in the user's secret store. Maps to a non-retryable
 * task failure — retrying won't fix a missing config.</p>
 *
 * <p>Mirrors Python's {@code CredentialNotFoundError} and .NET's
 * {@code CredentialNotFoundException}.</p>
 */
public class CredentialNotFoundException extends AgentspanException {

    private final List<String> missingNames;

    public CredentialNotFoundException(List<String> missingNames) {
        super("Required secrets not found: " + String.join(", ", missingNames));
        this.missingNames = List.copyOf(missingNames);
    }

    public CredentialNotFoundException(String singleName) {
        this(List.of(singleName));
    }

    public List<String> getMissingNames() {
        return missingNames;
    }
}
