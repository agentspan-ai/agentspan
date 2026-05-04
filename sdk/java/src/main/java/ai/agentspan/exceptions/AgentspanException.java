// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.exceptions;

/**
 * Base exception for all Agentspan SDK errors.
 */
public class AgentspanException extends RuntimeException {

    public AgentspanException(String message) {
        super(message);
    }

    public AgentspanException(String message, Throwable cause) {
        super(message, cause);
    }
}
