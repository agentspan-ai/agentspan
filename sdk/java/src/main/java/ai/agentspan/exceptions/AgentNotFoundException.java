// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.exceptions;

/** Thrown when a requested agent is not found on the server. */
public class AgentNotFoundException extends AgentspanException {
    private final String agentName;

    public AgentNotFoundException(String agentName) {
        super("Agent not found: " + agentName);
        this.agentName = agentName;
    }

    public String getAgentName() { return agentName; }
}
