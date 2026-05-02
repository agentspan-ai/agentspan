// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.model;

/**
 * Result of deploying an agent to the server.
 *
 * <pre>{@code
 * List<DeploymentInfo> deployments = runtime.deploy(agent1, agent2);
 * for (DeploymentInfo d : deployments) {
 *     System.out.println("Deployed: " + d.getAgentName() + " -> " + d.getRegisteredName());
 * }
 * }</pre>
 */
public class DeploymentInfo {
    private final String registeredName;
    private final String agentName;

    public DeploymentInfo(String registeredName, String agentName) {
        this.registeredName = registeredName;
        this.agentName = agentName;
    }

    /** The name under which this agent is registered on the server. */
    public String getRegisteredName() { return registeredName; }

    /** The original agent name. */
    public String getAgentName() { return agentName; }

    @Override
    public String toString() {
        return "DeploymentInfo{agentName=" + agentName + ", registeredName=" + registeredName + "}";
    }
}
