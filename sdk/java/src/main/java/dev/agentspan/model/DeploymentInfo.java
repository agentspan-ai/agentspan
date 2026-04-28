// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.model;

/**
 * Result of deploying an agent to the server.
 */
public class DeploymentInfo {
    private final String workflowName;
    private final String workflowVersion;

    public DeploymentInfo(String workflowName, String workflowVersion) {
        this.workflowName = workflowName;
        this.workflowVersion = workflowVersion;
    }

    public String getWorkflowName() { return workflowName; }
    public String getWorkflowVersion() { return workflowVersion; }

    @Override
    public String toString() {
        return "DeploymentInfo{workflowName=" + workflowName + ", version=" + workflowVersion + "}";
    }
}
