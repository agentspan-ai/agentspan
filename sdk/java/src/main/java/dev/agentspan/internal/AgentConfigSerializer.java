// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.internal;

import dev.agentspan.Agent;
import dev.agentspan.execution.CliConfig;
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
        // Skill (and other framework) agents — emit the raw framework config so the server
        // can compile sub-agents and tools from the SKILL.md content.
        if ("skill".equals(agent.getFramework())) {
            Map<String, Object> skillMap = new LinkedHashMap<>();
            skillMap.put("name", agent.getName());
            skillMap.put("model", agent.getModel() != null ? agent.getModel() : null);
            skillMap.put("_framework", "skill");
            Map<String, Object> cfg = agent.getFrameworkConfig();
            if (cfg != null) skillMap.putAll(cfg);
            return skillMap;
        }

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
            boolean agentStateful = agent.isStateful();
            for (ToolDef tool : agent.getTools()) {
                toolsList.add(serializeTool(tool, agentStateful));
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

        // Condition-based handoffs
        if (agent.getHandoffs() != null && !agent.getHandoffs().isEmpty()) {
            agentMap.put("handoffs", agent.getHandoffs().stream()
                .map(h -> serializeHandoff(h, agent.getName()))
                .collect(java.util.stream.Collectors.toList()));
        }

        // Allowed transitions (constrained handoff paths)
        if (agent.getAllowedTransitions() != null && !agent.getAllowedTransitions().isEmpty()) {
            agentMap.put("allowedTransitions", agent.getAllowedTransitions());
        }

        // Planner mode
        if (agent.isPlanner()) {
            agentMap.put("planner", true);
        }

        // Synthesize — only emit when explicitly disabled (true is the server default)
        if (!agent.isSynthesize()) {
            agentMap.put("synthesize", false);
        }

        // Code execution
        if (agent.isLocalCodeExecution()) {
            List<String> langs = agent.getAllowedLanguages();
            List<String> effectiveLangs = langs != null && !langs.isEmpty() ? langs : List.of("python");
            List<String> cmds = agent.getAllowedCommands();
            int timeout = agent.getCodeExecutionTimeout() > 0 ? agent.getCodeExecutionTimeout() : 30;

            Map<String, Object> codeExec = new LinkedHashMap<>();
            codeExec.put("enabled", true);
            codeExec.put("allowedLanguages", effectiveLangs);
            codeExec.put("allowedCommands", cmds != null ? cmds : new ArrayList<>());
            codeExec.put("timeout", timeout);
            agentMap.put("codeExecution", codeExec);

            // Inject execute_code worker tool so the LLM sees it as a callable function.
            // Python SDK does the same in Agent._attach_code_execution_tool().
            // The tool name is {agent_name}_execute_code to avoid multi-agent collisions.
            String execToolName = agent.getName() + "_execute_code";
            Map<String, Object> execTool = new LinkedHashMap<>();
            execTool.put("name", execToolName);
            execTool.put("description",
                "Execute code in the specified language. Supported languages: "
                + String.join(", ", effectiveLangs)
                + ". Each execution runs in an isolated environment — no state, variables, "
                + "or imports persist between calls.");
            Map<String, Object> inputSchema = new LinkedHashMap<>();
            inputSchema.put("type", "object");
            Map<String, Object> properties = new LinkedHashMap<>();
            Map<String, Object> langProp = new LinkedHashMap<>();
            langProp.put("type", "string");
            langProp.put("description", "The programming language to use. One of: "
                + String.join(", ", effectiveLangs));
            langProp.put("enum", effectiveLangs);
            Map<String, Object> codeProp = new LinkedHashMap<>();
            codeProp.put("type", "string");
            codeProp.put("description", "The code to execute.");
            properties.put("language", langProp);
            properties.put("code", codeProp);
            inputSchema.put("properties", properties);
            inputSchema.put("required", List.of("language", "code"));
            execTool.put("inputSchema", inputSchema);
            execTool.put("outputSchema",
                Map.of("type", "object", "additionalProperties", Map.of()));
            execTool.put("toolType", "worker");

            // Append or create tools list
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> existingTools = (List<Map<String, Object>>) agentMap.get("tools");
            if (existingTools == null) {
                List<Map<String, Object>> toolsList = new ArrayList<>();
                toolsList.add(execTool);
                agentMap.put("tools", toolsList);
            } else {
                existingTools.add(execTool);
            }
        }

        // CLI config
        CliConfig cliConfig = agent.getCliConfig();
        if (cliConfig != null) {
            Map<String, Object> cliMap = new LinkedHashMap<>();
            cliMap.put("enabled", cliConfig.isEnabled());
            cliMap.put("allowedCommands", cliConfig.getAllowedCommands());
            cliMap.put("timeout", cliConfig.getTimeout());
            cliMap.put("allowShell", cliConfig.isAllowShell());
            if (cliConfig.getWorkingDir() != null) cliMap.put("workingDir", cliConfig.getWorkingDir());
            agentMap.put("cliConfig", cliMap);
        }

        // Include contents (context passed to sub-agent)
        if (agent.getIncludeContents() != null && !agent.getIncludeContents().isEmpty()) {
            agentMap.put("includeContents", agent.getIncludeContents());
        }

        // Thinking config (extended reasoning)
        if (agent.getThinkingBudgetTokens() != null) {
            Map<String, Object> thinkingConfig = new LinkedHashMap<>();
            thinkingConfig.put("enabled", true);
            thinkingConfig.put("budgetTokens", agent.getThinkingBudgetTokens());
            agentMap.put("thinkingConfig", thinkingConfig);
        }

        // Introduction (prepended to conversation in multi-agent discussions)
        if (agent.getIntroduction() != null && !agent.getIntroduction().isEmpty()) {
            agentMap.put("introduction", agent.getIntroduction());
        }

        // Required tools (tool names the agent must invoke)
        if (agent.getRequiredTools() != null && !agent.getRequiredTools().isEmpty()) {
            agentMap.put("requiredTools", agent.getRequiredTools());
        }

        // Agent-level credentials
        if (agent.getCredentials() != null && !agent.getCredentials().isEmpty()) {
            agentMap.put("credentials", agent.getCredentials());
        }

        // Metadata (arbitrary key-value pairs attached to the workflow)
        if (agent.getMetadata() != null && !agent.getMetadata().isEmpty()) {
            agentMap.put("metadata", agent.getMetadata());
        }

        // Stop when (early-exit condition worker task)
        if (agent.getStopWhenTaskName() != null && !agent.getStopWhenTaskName().isEmpty()) {
            Map<String, Object> stopWhen = new LinkedHashMap<>();
            stopWhen.put("taskName", agent.getStopWhenTaskName());
            agentMap.put("stopWhen", stopWhen);
        }

        // Stateful mode
        if (agent.isStateful()) {
            agentMap.put("stateful", true);
        }

        // Base URL override for the LLM provider
        if (agent.getBaseUrl() != null && !agent.getBaseUrl().isEmpty()) {
            agentMap.put("baseUrl", agent.getBaseUrl());
        }

        // Gate (stop sequential pipeline when output contains sentinel text)
        if (agent.getGate() != null) {
            dev.agentspan.gate.TextGate g = agent.getGate();
            Map<String, Object> gateMap = new LinkedHashMap<>();
            gateMap.put("type", "text_contains");
            gateMap.put("text", g.getText());
            gateMap.put("caseSensitive", g.isCaseSensitive());
            agentMap.put("gate", gateMap);
        }

        // Callbacks (before/after model hooks — legacy single-function style)
        List<Map<String, Object>> callbacks = new ArrayList<>();
        if (agent.getBeforeAgentCallback() != null) {
            Map<String, Object> cb = new LinkedHashMap<>();
            cb.put("position", "before_agent");
            cb.put("taskName", agent.getName() + "_before_agent");
            callbacks.add(cb);
        }
        if (agent.getAfterAgentCallback() != null) {
            Map<String, Object> cb = new LinkedHashMap<>();
            cb.put("position", "after_agent");
            cb.put("taskName", agent.getName() + "_after_agent");
            callbacks.add(cb);
        }
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
        return serializeTool(tool, false);
    }

    private Map<String, Object> serializeTool(ToolDef tool, boolean agentStateful) {
        Map<String, Object> toolMap = new LinkedHashMap<>();
        toolMap.put("name", tool.getName());
        toolMap.put("description", tool.getDescription());
        toolMap.put("inputSchema", tool.getInputSchema());
        if (agentStateful) {
            toolMap.put("stateful", true);
        }
        if ("worker".equals(tool.getToolType())) {
            Map<String, Object> outSchema = tool.getOutputSchema();
            toolMap.put("outputSchema", outSchema != null ? outSchema
                : Map.of("type", "object", "additionalProperties", Map.of()));
        }
        toolMap.put("toolType", tool.getToolType());

        if (tool.isApprovalRequired()) {
            toolMap.put("approvalRequired", true);
        }
        if (tool.getTimeoutSeconds() > 0) {
            toolMap.put("timeoutSeconds", tool.getTimeoutSeconds());
        }
        if (tool.getRetryCount() >= 0) {
            toolMap.put("retryCount", tool.getRetryCount());
        }
        if (tool.getRetryDelaySeconds() >= 0) {
            toolMap.put("retryDelaySeconds", tool.getRetryDelaySeconds());
        }
        if (tool.getRetryLogic() != null && !tool.getRetryLogic().isEmpty()) {
            toolMap.put("retryLogic", tool.getRetryLogic());
        }

        // Credentials must be nested inside config so the server includes them
        // in the execution token's declared_names (matches Python SDK behaviour).
        List<String> creds = tool.getCredentials();
        Map<String, Object> toolConfig = tool.getConfig();
        if (creds != null && !creds.isEmpty()) {
            Map<String, Object> merged = new LinkedHashMap<>();
            if (toolConfig != null) merged.putAll(toolConfig);
            merged.put("credentials", creds);
            toolMap.put("config", merged);
        } else if (toolConfig != null && !toolConfig.isEmpty()) {
            toolMap.put("config", toolConfig);
        }

        if (tool.getGuardrails() != null && !tool.getGuardrails().isEmpty()) {
            toolMap.put("guardrails", tool.getGuardrails().stream()
                .map(g -> serializeGuardrail(g, tool.getName()))
                .collect(java.util.stream.Collectors.toList()));
        }

        return toolMap;
    }

    private Map<String, Object> serializeHandoff(dev.agentspan.handoff.Handoff h, String agentName) {
        Map<String, Object> hMap = new LinkedHashMap<>();
        hMap.put("target", h.getTarget());
        if (h instanceof dev.agentspan.handoff.OnTextMention) {
            dev.agentspan.handoff.OnTextMention otm = (dev.agentspan.handoff.OnTextMention) h;
            hMap.put("type", "on_text_mention");
            hMap.put("text", otm.getText());
        } else if (h instanceof dev.agentspan.handoff.OnToolResult) {
            dev.agentspan.handoff.OnToolResult otr = (dev.agentspan.handoff.OnToolResult) h;
            hMap.put("type", "on_tool_result");
            hMap.put("toolName", otr.getToolName());
            if (otr.getResultContains() != null) {
                hMap.put("resultContains", otr.getResultContains());
            }
        } else {
            hMap.put("type", "on_condition");
            hMap.put("taskName", agentName + "_handoff_" + h.getTarget());
        }
        return hMap;
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
