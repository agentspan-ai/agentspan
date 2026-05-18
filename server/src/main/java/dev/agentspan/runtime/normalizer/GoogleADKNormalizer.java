/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.normalizer;

import java.util.*;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import dev.agentspan.runtime.model.*;

/**
 * Normalizes Google ADK agent raw configs into the canonical {@link AgentConfig}.
 *
 * <p>Key differences from OpenAI:
 * <ul>
 *   <li>{@code instruction} (singular) instead of {@code instructions}</li>
 *   <li>{@code sub_agents} instead of {@code handoffs}</li>
 *   <li>Model names like "gemini-2.0-flash" are prefixed with "google_gemini/"</li>
 * </ul>
 */
@Component
public class GoogleADKNormalizer implements AgentConfigNormalizer {

    private static final Logger log = LoggerFactory.getLogger(GoogleADKNormalizer.class);

    /**
     * Default model provider for ADK agents. Can be overridden via
     * {@code AGENT_DEFAULT_MODEL} environment variable to use a different
     * provider when Google Gemini is not available.
     * Format: "provider/model" (e.g. "openai/gpt-4o-mini", "anthropic/claude-sonnet-4-20250514").
     */
    private static final String DEFAULT_MODEL_ENV = "AGENT_DEFAULT_MODEL";

    @Override
    public String frameworkId() {
        return "google_adk";
    }

    @Override
    @SuppressWarnings("unchecked")
    public AgentConfig normalize(Map<String, Object> raw) {
        log.info("Normalizing Google ADK agent config: {}", raw.get("name"));

        AgentConfig config = new AgentConfig();
        config.setName(getString(raw, "name", "google_adk_agent"));

        // Model: check for env override, then prefix with "google_gemini/" if no provider
        String model = getString(raw, "model", "gemini-2.0-flash");
        String envModel = System.getenv(DEFAULT_MODEL_ENV);
        if (envModel != null && !envModel.isEmpty()) {
            // Use the env-specified model, ignoring the ADK agent's model field
            config.setModel(envModel);
        } else {
            config.setModel(ensureProvider(model, "google_gemini"));
        }

        // Instructions: ADK uses "instruction" (singular)
        // If global_instruction is set, prepend it to the instruction
        Object instruction = raw.get("instruction");
        if (instruction == null) {
            instruction = raw.get("instructions");
        }
        Object globalInstruction = raw.get("global_instruction");
        if (globalInstruction instanceof String && !((String) globalInstruction).isEmpty()) {
            String combined = (String) globalInstruction;
            if (instruction instanceof String && !((String) instruction).isEmpty()) {
                combined = combined + "\n\n" + instruction;
            }
            instruction = combined;
        }
        config.setInstructions(instruction);

        // Description
        String description = getString(raw, "description", "");
        if (!description.isEmpty()) {
            config.setDescription(description);
        }

        // Tools
        List<Map<String, Object>> rawTools = getList(raw, "tools");
        if (rawTools != null) {
            List<ToolConfig> tools = new ArrayList<>();
            for (Map<String, Object> t : rawTools) {
                ToolConfig tool = normalizeTool(t);
                if (tool != null) {
                    tools.add(tool);
                }
            }
            if (!tools.isEmpty()) {
                config.setTools(tools);
            }
        }

        // Code execution — check for code_execution tool
        if (hasToolType(rawTools, "CodeExecutionTool", "code_execution")) {
            config.setCodeExecution(CodeExecutionConfig.builder().enabled(true).build());
        }

        // Sub-agents → agents + strategy
        // Detect agent type from _type field to set the correct strategy
        String agentType = getString(raw, "_type", "");
        List<Map<String, Object>> subAgents = getList(raw, "sub_agents");
        if (subAgents != null && !subAgents.isEmpty()) {
            String strategy =
                    switch (agentType) {
                        case "SequentialAgent" -> "sequential";
                        case "ParallelAgent" -> "parallel";
                        default -> "handoff";
                    };
            config.setStrategy(strategy);
            List<AgentConfig> agents = new ArrayList<>();
            for (Map<String, Object> sa : subAgents) {
                agents.add(normalize(sa));
            }
            config.setAgents(agents);
        }

        // Transfer control: compute allowedTransitions from disallow_* flags
        if (subAgents != null && !subAgents.isEmpty()) {
            Map<String, List<String>> transitions = new LinkedHashMap<>();
            List<String> subNames = new ArrayList<>();
            for (Map<String, Object> sa : subAgents) {
                subNames.add(getString(sa, "name", ""));
            }

            boolean hasConstraints = false;
            for (Map<String, Object> sa : subAgents) {
                String saName = getString(sa, "name", "");
                boolean disallowParent = Boolean.TRUE.equals(sa.get("disallow_transfer_to_parent"));
                boolean disallowPeers = Boolean.TRUE.equals(sa.get("disallow_transfer_to_peers"));

                if (disallowParent || disallowPeers) {
                    hasConstraints = true;
                    List<String> allowed = new ArrayList<>();
                    if (!disallowParent) {
                        allowed.add(config.getName());
                    }
                    if (!disallowPeers) {
                        for (String peer : subNames) {
                            if (!peer.equals(saName)) {
                                allowed.add(peer);
                            }
                        }
                    }
                    transitions.put(saName, allowed);
                }
            }

            if (hasConstraints) {
                config.setAllowedTransitions(transitions);
            }
        }

        // LoopAgent: map to sequential with maxTurns = max_iterations
        if ("LoopAgent".equals(agentType)) {
            config.setStrategy("sequential");
            Integer maxIter = getInt(raw, "max_iterations");
            if (maxIter != null && maxIter > 0) {
                config.setMaxTurns(maxIter);
            }
        }

        // Output key: pass through for state management
        String outputKey = getString(raw, "output_key");
        if (outputKey != null && !outputKey.isEmpty()) {
            if (config.getMetadata() == null) {
                config.setMetadata(new HashMap<>());
            }
            config.getMetadata().put("output_key", outputKey);
        }

        // Output schema
        Object outputSchema = raw.get("output_schema");
        if (outputSchema instanceof Map) {
            config.setOutputType(OutputTypeConfig.builder()
                    .schema((Map<String, Object>) outputSchema)
                    .build());
        }

        // Temperature and max tokens (top-level)
        if (raw.containsKey("temperature")) {
            config.setTemperature(getDouble(raw, "temperature"));
        }
        if (raw.containsKey("max_tokens")) {
            config.setMaxTokens(getInt(raw, "max_tokens"));
        }

        // Generate config (ADK specific)
        Map<String, Object> generateConfig = getMap(raw, "generate_content_config");
        if (generateConfig != null) {
            if (generateConfig.containsKey("temperature")) {
                config.setTemperature(getDouble(generateConfig, "temperature"));
            }
            if (generateConfig.containsKey("max_output_tokens")) {
                config.setMaxTokens(getInt(generateConfig, "max_output_tokens"));
            }
        }

        // Callbacks: extract _worker_ref from ADK callback fields
        String[] callbackFields = {
            "before_model_callback", "after_model_callback",
            "before_tool_callback", "after_tool_callback",
            "before_agent_callback", "after_agent_callback"
        };
        List<CallbackConfig> callbacks = new ArrayList<>();
        for (String field : callbackFields) {
            Map<String, Object> cb = getMap(raw, field);
            if (cb != null && cb.containsKey("_worker_ref")) {
                String position = field.replace("_callback", "");
                String taskName = (String) cb.get("_worker_ref");
                callbacks.add(CallbackConfig.builder()
                        .position(position)
                        .taskName(taskName)
                        .build());
                log.debug("Extracted callback: position={}, taskName={}", position, taskName);
            }
        }
        if (!callbacks.isEmpty()) {
            config.setCallbacks(callbacks);
        }

        // Planner: detect planner field and set flag
        Object planner = raw.get("planner");
        if (planner != null) {
            config.setPlanner(true);
        }

        // Include contents: control context passed to sub-agents
        String includeContents = getString(raw, "include_contents");
        if (includeContents != null) {
            config.setIncludeContents(includeContents);
        }

        // Thinking config: from generate_content_config or top-level
        if (generateConfig != null) {
            Map<String, Object> thinkingCfg = getMap(generateConfig, "thinking_config");
            if (thinkingCfg != null) {
                Integer budget = getInt(thinkingCfg, "thinking_budget");
                if (budget == null) budget = getInt(thinkingCfg, "budget_tokens");
                config.setThinkingConfig(ThinkingConfig.builder()
                        .enabled(true)
                        .budgetTokens(budget)
                        .build());
            }
        }
        // Also check top-level thinkingConfig (from native SDK)
        Map<String, Object> topThinking = getMap(raw, "thinkingConfig");
        if (topThinking != null && config.getThinkingConfig() == null) {
            config.setThinkingConfig(ThinkingConfig.builder()
                    .enabled(Boolean.TRUE.equals(topThinking.get("enabled")))
                    .budgetTokens(getInt(topThinking, "budgetTokens"))
                    .build());
        }

        return config;
    }

    @SuppressWarnings("unchecked")
    private ToolConfig normalizeTool(Map<String, Object> raw) {
        // Worker ref (callable extracted by SDK)
        if (raw.containsKey("_worker_ref")) {
            return ToolConfig.builder()
                    .name(getString(raw, "_worker_ref", "unknown_tool"))
                    .description(getString(raw, "description", ""))
                    .inputSchema((Map<String, Object>) raw.get("parameters"))
                    .toolType("worker")
                    .build();
        }

        // Typed object
        String type = getString(raw, "_type", getString(raw, "type", ""));

        switch (type) {
            case "GoogleSearchTool":
            case "google_search":
                return ToolConfig.builder()
                        .name("google_search")
                        .description("Search using Google")
                        .toolType("http")
                        .config(Map.of("builtin", "google_search"))
                        .build();

            case "CodeExecutionTool":
            case "code_execution":
                // Handled via codeExecution config
                return null;

            case "FunctionTool":
            case "function":
                return ToolConfig.builder()
                        .name(getString(raw, "name", "unknown_tool"))
                        .description(getString(raw, "description", ""))
                        .inputSchema((Map<String, Object>) raw.get("parameters"))
                        .toolType("worker")
                        .build();

            case "AgentTool": {
                // Agent-as-tool: wrap a child agent as a callable tool
                Map<String, Object> agentRaw = getMap(raw, "agent");
                if (agentRaw == null) {
                    log.warn("AgentTool '{}' has no embedded agent, skipping", getString(raw, "name", "unknown"));
                    return null;
                }
                AgentConfig childAgent = normalize(agentRaw);
                String toolName = getString(raw, "name", childAgent.getName());
                String toolDesc = getString(raw, "description", "Invoke agent: " + childAgent.getName());

                Map<String, Object> inputSchema = new LinkedHashMap<>();
                inputSchema.put("type", "object");
                inputSchema.put(
                        "properties",
                        Map.of(
                                "request",
                                Map.of(
                                        "type",
                                        "string",
                                        "description",
                                        "The request or question to send to this agent")));
                inputSchema.put("required", List.of("request"));
                inputSchema.put("additionalProperties", false);

                Map<String, Object> toolConfig = new LinkedHashMap<>();
                toolConfig.put("agentConfig", childAgent);

                return ToolConfig.builder()
                        .name(toolName)
                        .description(toolDesc)
                        .inputSchema(inputSchema)
                        .toolType("agent_tool")
                        .config(toolConfig)
                        .build();
            }

            default:
                if (raw.containsKey("name")) {
                    return ToolConfig.builder()
                            .name(getString(raw, "name", "unknown_tool"))
                            .description(getString(raw, "description", ""))
                            .inputSchema((Map<String, Object>) raw.get("parameters"))
                            .toolType("worker")
                            .build();
                }
                log.warn("Skipping unrecognized Google ADK tool: {}", raw);
                return null;
        }
    }

    // ── Utility methods ─────────────────────────────────────────────

    private String ensureProvider(String model, String defaultProvider) {
        if (model == null || model.isEmpty()) {
            return defaultProvider + "/gemini-2.0-flash";
        }
        return model.contains("/") ? model : defaultProvider + "/" + model;
    }

    private boolean hasToolType(List<Map<String, Object>> tools, String... typeNames) {
        if (tools == null) return false;
        Set<String> names = Set.of(typeNames);
        for (Map<String, Object> t : tools) {
            String type = getString(t, "_type", getString(t, "type", ""));
            if (names.contains(type)) return true;
        }
        return false;
    }

    private String getString(Map<String, Object> map, String key, String defaultValue) {
        Object v = map.get(key);
        return v instanceof String ? (String) v : defaultValue;
    }

    private String getString(Map<String, Object> map, String key) {
        return getString(map, key, null);
    }

    private Integer getInt(Map<String, Object> map, String key) {
        Object v = map.get(key);
        if (v instanceof Number) return ((Number) v).intValue();
        return null;
    }

    private Double getDouble(Map<String, Object> map, String key) {
        Object v = map.get(key);
        if (v instanceof Number) return ((Number) v).doubleValue();
        return null;
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> getList(Map<String, Object> map, String key) {
        Object v = map.get(key);
        if (v instanceof List) return (List<Map<String, Object>>) v;
        return null;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> getMap(Map<String, Object> map, String key) {
        Object v = map.get(key);
        if (v instanceof Map) return (Map<String, Object>) v;
        return null;
    }
}
