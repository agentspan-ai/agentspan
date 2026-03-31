// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.model;

import java.util.Map;

/**
 * Reference to a named prompt template stored on the Conductor server.
 *
 * <p>Pass an instance as the {@code instructionsTemplate} on an Agent to use a
 * server-managed template instead of a hardcoded string. Variables replace
 * {@code ${var}} placeholders at execution time.
 *
 * <pre>{@code
 * Agent agent = Agent.builder()
 *     .name("support")
 *     .model("openai/gpt-4o-mini")
 *     .instructionsTemplate(new PromptTemplate("customer-support",
 *         Map.of("company", "Acme", "tone", "friendly")))
 *     .build();
 * }</pre>
 */
public class PromptTemplate {
    private final String name;
    private final Map<String, Object> variables;
    private final Integer version;

    /**
     * Reference a template by name, using the latest version with no variables.
     */
    public PromptTemplate(String name) {
        this(name, null, null);
    }

    /**
     * Reference a template by name with variable substitution.
     */
    public PromptTemplate(String name, Map<String, Object> variables) {
        this(name, variables, null);
    }

    /**
     * Reference a specific version of a template with variable substitution.
     */
    public PromptTemplate(String name, Map<String, Object> variables, Integer version) {
        this.name = name;
        this.variables = variables;
        this.version = version;
    }

    public String getName() { return name; }
    public Map<String, Object> getVariables() { return variables; }
    public Integer getVersion() { return version; }
}
