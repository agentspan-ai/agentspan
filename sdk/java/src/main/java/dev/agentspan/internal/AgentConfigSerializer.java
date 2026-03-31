// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.internal;

import dev.agentspan.Agent;
import dev.agentspan.model.GuardrailDef;
import dev.agentspan.model.PromptTemplate;
import dev.agentspan.model.ToolDef;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Serializes an {@link Agent} tree to the camelCase JSON dict for POST /agent/start.
 */
public class AgentConfigSerializer {
    private static final Logger logger = LoggerFactory.getLogger(AgentConfigSerializer.class);

    /**
     * Serialize an Agent to a Map suitable for JSON serialization.
     *
     * @param agent the agent to serialize
     * @return a map representation of the agent config
     */
    public Map<String, Object> serialize(Agent agent) {
        return serializeAgent(agent);
    }

    private Map<String, Object> serializeAgent(Agent agent) {
        Map<String, Object> agentMap = new LinkedHashMap<>();

        agentMap.put("name", agent.getName());

        // Model — omit for external agents
        if (!agent.isExternal()) {
            agentMap.put("model", agent.getModel());
        }

        // Strategy — only if sub-agents present
        if (agent.getAgents() != null && !agent.getAgents().isEmpty()) {
            agentMap.put("strategy", agent.getStrategy().toJsonValue());
        }

        // Max turns
        if (agent.getMaxTurns() > 0) {
            agentMap.put("maxTurns", agent.getMaxTurns());
        }

        // Timeout (always emit, including 0)
        agentMap.put("timeoutSeconds", agent.getTimeoutSeconds());

        // External flag (always emit)
        agentMap.put("external", agent.isExternal());

        // Instructions — prefer PromptTemplate over plain string
        if (agent.getInstructionsTemplate() != null) {
            PromptTemplate pt = agent.getInstructionsTemplate();
            Map<String, Object> tmpl = new LinkedHashMap<>();
            tmpl.put("type", "prompt_template");
            tmpl.put("name", pt.getName());
            if (pt.getVariables() != null && !pt.getVariables().isEmpty()) {
                tmpl.put("variables", pt.getVariables());
            }
            if (pt.getVersion() != null) {
                tmpl.put("version", pt.getVersion());
            }
            agentMap.put("instructions", tmpl);
        } else if (agent.getInstructions() != null && !agent.getInstructions().isEmpty()) {
            agentMap.put("instructions", agent.getInstructions());
        }

        // Tools
        if (agent.getTools() != null && !agent.getTools().isEmpty()) {
            List<Map<String, Object>> toolsList = new ArrayList<>();
            for (ToolDef tool : agent.getTools()) {
                toolsList.add(serializeTool(tool));
            }
            agentMap.put("tools", toolsList);
        }

        // Sub-agents (recursive)
        if (agent.getAgents() != null && !agent.getAgents().isEmpty()) {
            List<Map<String, Object>> agentsList = new ArrayList<>();
            for (Agent subAgent : agent.getAgents()) {
                agentsList.add(serializeAgent(subAgent));
            }
            agentMap.put("agents", agentsList);
        }

        // Router agent (for ROUTER strategy)
        if (agent.getRouter() != null) {
            agentMap.put("router", serializeAgent(agent.getRouter()));
        }

        // Guardrails
        if (agent.getGuardrails() != null && !agent.getGuardrails().isEmpty()) {
            List<Map<String, Object>> guardrailsList = new ArrayList<>();
            for (GuardrailDef g : agent.getGuardrails()) {
                guardrailsList.add(serializeGuardrail(g, agent.getName()));
            }
            agentMap.put("guardrails", guardrailsList);
        }

        // Max tokens
        if (agent.getMaxTokens() != null) {
            agentMap.put("maxTokens", agent.getMaxTokens());
        }

        // Temperature
        if (agent.getTemperature() != null) {
            agentMap.put("temperature", agent.getTemperature());
        }

        // Termination condition
        if (agent.getTermination() != null) {
            agentMap.put("termination", agent.getTermination().toMap());
        }

        // Output type
        if (agent.getOutputType() != null) {
            agentMap.put("outputType", serializeOutputType(agent.getOutputType()));
        }

        // Session ID
        if (agent.getSessionId() != null && !agent.getSessionId().isEmpty()) {
            agentMap.put("sessionId", agent.getSessionId());
        }

        // Allowed transitions (constrained handoff paths)
        if (agent.getAllowedTransitions() != null && !agent.getAllowedTransitions().isEmpty()) {
            agentMap.put("allowedTransitions", agent.getAllowedTransitions());
        }

        // Planner mode
        if (agent.isPlanner()) {
            agentMap.put("planner", true);
        }

        // Include contents (context passed to sub-agent)
        if (agent.getIncludeContents() != null && !agent.getIncludeContents().isEmpty()) {
            agentMap.put("includeContents", agent.getIncludeContents());
        }

        // Thinking budget (extended reasoning)
        if (agent.getThinkingBudgetTokens() != null) {
            agentMap.put("thinkingBudgetTokens", agent.getThinkingBudgetTokens());
        }

        // Introduction (prepended to conversation in multi-agent discussions)
        if (agent.getIntroduction() != null && !agent.getIntroduction().isEmpty()) {
            agentMap.put("introduction", agent.getIntroduction());
        }

        // Callbacks (before/after model hooks — legacy single-function style)
        List<Map<String, Object>> callbacks = new ArrayList<>();
        if (agent.getBeforeModelCallback() != null) {
            Map<String, Object> cb = new LinkedHashMap<>();
            cb.put("position", "before_model");
            cb.put("taskName", agent.getName() + "_before_model");
            callbacks.add(cb);
        }
        if (agent.getAfterModelCallback() != null) {
            Map<String, Object> cb = new LinkedHashMap<>();
            cb.put("position", "after_model");
            cb.put("taskName", agent.getName() + "_after_model");
            callbacks.add(cb);
        }
        // CallbackHandler list — emit a task entry for each position that any handler overrides
        if (agent.getCallbacks() != null && !agent.getCallbacks().isEmpty()) {
            String[][] positionMethods = {
                {"before_agent", "onAgentStart"},
                {"after_agent",  "onAgentEnd"},
                {"before_model", "onModelStart"},
                {"after_model",  "onModelEnd"},
                {"before_tool",  "onToolStart"},
                {"after_tool",   "onToolEnd"},
            };
            for (String[] pm : positionMethods) {
                String position = pm[0];
                String methodName = pm[1];
                // Check if any handler overrides this method
                boolean hasOverride = false;
                for (dev.agentspan.CallbackHandler h : agent.getCallbacks()) {
                    try {
                        java.lang.reflect.Method m = h.getClass().getMethod(methodName, Map.class);
                        if (!m.getDeclaringClass().equals(dev.agentspan.CallbackHandler.class)) {
                            hasOverride = true;
                            break;
                        }
                    } catch (NoSuchMethodException ignored) {}
                }
                if (hasOverride) {
                    // Only add if not already present from legacy callbacks
                    boolean alreadyAdded = callbacks.stream()
                        .anyMatch(c -> position.equals(c.get("position")));
                    if (!alreadyAdded) {
                        Map<String, Object> cb = new LinkedHashMap<>();
                        cb.put("position", position);
                        cb.put("taskName", agent.getName() + "_" + position);
                        callbacks.add(cb);
                    }
                }
            }
        }
        if (!callbacks.isEmpty()) {
            agentMap.put("callbacks", callbacks);
        }

        return agentMap;
    }

    private Map<String, Object> serializeTool(ToolDef tool) {
        Map<String, Object> toolMap = new LinkedHashMap<>();
        toolMap.put("name", tool.getName());
        toolMap.put("description", tool.getDescription());
        toolMap.put("inputSchema", tool.getInputSchema());
        toolMap.put("toolType", tool.getToolType());

        if (tool.isApprovalRequired()) {
            toolMap.put("approvalRequired", true);
        }
        if (tool.getTimeoutSeconds() > 0) {
            toolMap.put("timeoutSeconds", tool.getTimeoutSeconds());
        }
        if (tool.getConfig() != null && !tool.getConfig().isEmpty()) {
            toolMap.put("config", tool.getConfig());
        }
        if (tool.getCredentials() != null && !tool.getCredentials().isEmpty()) {
            toolMap.put("credentials", tool.getCredentials());
        }

        return toolMap;
    }

    private Map<String, Object> serializeGuardrail(GuardrailDef g, String agentName) {
        Map<String, Object> gMap = new LinkedHashMap<>();
        gMap.put("name", g.getName());
        gMap.put("position", g.getPosition().toJsonValue());
        gMap.put("onFail", g.getOnFail().toJsonValue());
        gMap.put("maxRetries", g.getMaxRetries());
        gMap.put("guardrailType", g.getGuardrailType() != null ? g.getGuardrailType() : "custom");

        if (g.getFunc() != null) {
            // Python uses {agent_name}_output_guardrail as the combined worker task name
            gMap.put("taskName", agentName + "_output_guardrail");
        }

        if (g.getConfig() != null && !g.getConfig().isEmpty()) {
            gMap.putAll(g.getConfig());
        }

        return gMap;
    }

    private Map<String, Object> serializeOutputType(Class<?> outputType) {
        Map<String, Object> outputTypeMap = new LinkedHashMap<>();
        outputTypeMap.put("schema", generateJsonSchema(outputType));
        outputTypeMap.put("className", outputType.getSimpleName());
        return outputTypeMap;
    }

    /**
     * Generate a basic JSON Schema from a Java class using its declared fields.
     */
    private Map<String, Object> generateJsonSchema(Class<?> cls) {
        Map<String, Object> schema = new LinkedHashMap<>();
        schema.put("type", "object");
        Map<String, Object> properties = new LinkedHashMap<>();
        List<String> required = new ArrayList<>();

        for (java.lang.reflect.Field field : cls.getDeclaredFields()) {
            if (java.lang.reflect.Modifier.isStatic(field.getModifiers())) continue;
            Map<String, Object> propSchema = ToolRegistry.typeToJsonSchema(field.getType());
            properties.put(field.getName(), propSchema);
            required.add(field.getName());
        }

        schema.put("properties", properties);
        if (!required.isEmpty()) {
            schema.put("required", required);
        }
        return schema;
    }
}
