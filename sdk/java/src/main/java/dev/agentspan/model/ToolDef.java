// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.model;

import dev.agentspan.Agent;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

/**
 * Definition of a tool that can be used by an agent.
 *
 * <p>Use {@link Builder} to create instances.
 */
public class ToolDef {
    private final String name;
    private final String description;
    private final Map<String, Object> inputSchema;
    private final Map<String, Object> outputSchema;
    private final Function<Map<String, Object>, Object> func;
    private final boolean approvalRequired;
    private final int timeoutSeconds;
    private final String toolType;
    private final Map<String, Object> config;
    private final List<String> credentials;
    private final List<GuardrailDef> guardrails;
    /** For {@code agent_tool} type: the child Agent whose workers must be registered. Not serialized directly. */
    private final Agent agentRef;
    private final int retryCount;
    private final int retryDelaySeconds;
    private final String retryLogic;

    private ToolDef(Builder builder) {
        this.name = builder.name;
        this.description = builder.description;
        this.inputSchema = builder.inputSchema;
        this.outputSchema = builder.outputSchema;
        this.func = builder.func;
        this.approvalRequired = builder.approvalRequired;
        this.timeoutSeconds = builder.timeoutSeconds;
        this.toolType = builder.toolType;
        this.config = builder.config;
        this.credentials = builder.credentials != null ? builder.credentials : new ArrayList<>();
        this.guardrails = builder.guardrails != null ? builder.guardrails : new ArrayList<>();
        this.agentRef = builder.agentRef;
        this.retryCount = builder.retryCount;
        this.retryDelaySeconds = builder.retryDelaySeconds;
        this.retryLogic = builder.retryLogic;
    }

    public String getName() { return name; }
    public String getDescription() { return description; }
    public Map<String, Object> getInputSchema() { return inputSchema; }
    public Map<String, Object> getOutputSchema() { return outputSchema; }
    public Function<Map<String, Object>, Object> getFunc() { return func; }
    public boolean isApprovalRequired() { return approvalRequired; }
    public int getTimeoutSeconds() { return timeoutSeconds; }
    public String getToolType() { return toolType; }
    public int getRetryCount() { return retryCount; }
    public int getRetryDelaySeconds() { return retryDelaySeconds; }
    public String getRetryLogic() { return retryLogic; }
    public Map<String, Object> getConfig() { return config; }
    public List<String> getCredentials() { return credentials; }
    public List<GuardrailDef> getGuardrails() { return guardrails; }
    public Agent getAgentRef() { return agentRef; }

    public static Builder builder() {
        return new Builder();
    }

    public static class Builder {
        private String name;
        private String description = "";
        private Map<String, Object> inputSchema;
        private Map<String, Object> outputSchema;
        private Function<Map<String, Object>, Object> func;
        private boolean approvalRequired = false;
        private int timeoutSeconds = 0;
        private String toolType = "worker";
        private int retryCount = -1;
        private int retryDelaySeconds = -1;
        private String retryLogic = "";
        private Map<String, Object> config;
        private List<String> credentials;
        private List<GuardrailDef> guardrails;
        private Agent agentRef;

        public Builder name(String name) { this.name = name; return this; }
        public Builder description(String description) { this.description = description; return this; }
        public Builder inputSchema(Map<String, Object> inputSchema) { this.inputSchema = inputSchema; return this; }
        public Builder outputSchema(Map<String, Object> outputSchema) { this.outputSchema = outputSchema; return this; }
        public Builder func(Function<Map<String, Object>, Object> func) { this.func = func; return this; }
        public Builder approvalRequired(boolean approvalRequired) { this.approvalRequired = approvalRequired; return this; }
        public Builder timeoutSeconds(int timeoutSeconds) { this.timeoutSeconds = timeoutSeconds; return this; }
        public Builder retryCount(int retryCount) { this.retryCount = retryCount; return this; }
        public Builder retryDelaySeconds(int retryDelaySeconds) { this.retryDelaySeconds = retryDelaySeconds; return this; }
        public Builder retryLogic(String retryLogic) { this.retryLogic = retryLogic; return this; }
        public Builder toolType(String toolType) { this.toolType = toolType; return this; }
        public Builder config(Map<String, Object> config) { this.config = config; return this; }
        public Builder credentials(List<String> credentials) { this.credentials = credentials; return this; }
        public Builder guardrails(List<GuardrailDef> guardrails) { this.guardrails = guardrails; return this; }
        public Builder agentRef(Agent agentRef) { this.agentRef = agentRef; return this; }

        public ToolDef build() {
            if (name == null || name.isEmpty()) {
                throw new IllegalArgumentException("ToolDef requires a name");
            }
            return new ToolDef(this);
        }
    }
}
