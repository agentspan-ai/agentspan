// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.exceptions;

/**
 * Thrown when the workflow / agent / execution ID is not found (HTTP 404).
 *
 * <p>Subclass of {@link AgentAPIException} — catch this when you want to
 * distinguish "doesn't exist" from generic server errors. Mirrors
 * {@code AgentNotFoundError} in the Python SDK.
 */
public class AgentNotFoundException extends AgentAPIException {
    public AgentNotFoundException(int statusCode, String responseBody) {
        super(statusCode, responseBody);
    }
}
