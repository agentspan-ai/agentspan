/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.model;

import com.fasterxml.jackson.annotation.JsonInclude;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;

/**
 * Root configuration DTO for an agent definition.
 * Mirrors the Python Agent class fields for server-side compilation.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class AgentConfig {

    private String name;
    private String description;
    private String model;

    /**
     * Instructions can be a plain string or a PromptTemplateRef object.
     * When serialized from Python, callable instructions are resolved to strings.
     */
    private Object instructions;

    private List<ToolConfig> tools;

    /** Recursive sub-agent definitions. */
    private List<AgentConfig> agents;

    @Builder.Default
    private String strategy = "handoff";

    /**
     * Router can be an AgentConfig (agent-based) or a WorkerRef (function-based).
     */
    private Object router;

    private OutputTypeConfig outputType;
    private List<GuardrailConfig> guardrails;
    private MemoryConfig memory;

    @Builder.Default
    private int maxTurns = 25;

    private Integer maxTokens;

    @Builder.Default
    private int timeoutSeconds = 0;

    private Double temperature;

    /** Worker reference for stop_when callable. */
    private WorkerRef stopWhen;

    private TerminationConfig termination;
    private List<HandoffConfig> handoffs;
    private List<CallbackConfig> callbacks;

    /** Map of agent name -> list of allowed next agent names. */
    private Map<String, List<String>> allowedTransitions;

    private String introduction;
    private Map<String, Object> metadata;
    private CodeExecutionConfig codeExecution;
    private CliConfig cliConfig;

    /**
     * Controls whether parent conversation context is passed to this sub-agent.
     * "none" = fresh context (only the prompt), null/absent = inherit parent context.
     */
    private String includeContents;

    /** Extended thinking/reasoning config. */
    private ThinkingConfig thinkingConfig;

    /** Whether the agent should plan before executing. */
    private Boolean planner;

    /** Tools that must be called before the agent can complete. */
    private List<String> requiredTools;

    /**
     * Gate condition for conditional sequential pipelines.
     * Can be a Map (declarative, e.g. text_contains) or a WorkerRef (callable).
     */
    private Map<String, Object> gate;

    /** Agent-level credential names (e.g. ["GH_TOKEN", "AWS_ACCESS_KEY_ID"]). */
    private List<String> credentials;

    /** Whether this is an external agent (no model, references existing workflow). */
    @Builder.Default
    private boolean external = false;
}
