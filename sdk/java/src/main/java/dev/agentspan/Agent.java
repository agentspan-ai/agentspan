// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan;

import dev.agentspan.enums.Strategy;
import dev.agentspan.model.GuardrailDef;
import dev.agentspan.model.PromptTemplate;
import dev.agentspan.model.ToolDef;
import dev.agentspan.termination.TerminationCondition;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.regex.Pattern;

/**
 * An AI agent backed by a durable Conductor workflow.
 *
 * <p>Use {@link #builder()} to create instances with a fluent API.
 *
 * <p>Everything is an Agent. A single agent wraps an LLM + tools.
 * An agent with sub-agents IS a multi-agent system.
 *
 * <p>Example:
 * <pre>{@code
 * Agent agent = Agent.builder()
 *     .name("assistant")
 *     .model("openai/gpt-4o")
 *     .instructions("You are a helpful assistant.")
 *     .maxTurns(10)
 *     .build();
 * }</pre>
 */
public class Agent {
    private static final Pattern VALID_NAME = Pattern.compile("^[a-zA-Z_][a-zA-Z0-9_-]*$");

    private final String name;
    private final String model;
    private final String instructions;
    private final List<ToolDef> tools;
    private final List<Agent> agents;
    private final Strategy strategy;
    private final Agent router;
    private final List<GuardrailDef> guardrails;
    private final int maxTurns;
    private final Integer maxTokens;
    private final Double temperature;
    private final int timeoutSeconds;
    private final TerminationCondition termination;
    private final Class<?> outputType;
    private final String sessionId;
    private final Map<String, List<String>> allowedTransitions;
    private final boolean planner;
    private final boolean localCodeExecution;
    private final java.util.List<String> allowedLanguages;
    private final int codeExecutionTimeout;
    private final String includeContents;
    private final Integer thinkingBudgetTokens;
    private final String introduction;
    private final PromptTemplate instructionsTemplate;
    private final Function<Map<String, Object>, Map<String, Object>> beforeModelCallback;
    private final Function<Map<String, Object>, Map<String, Object>> afterModelCallback;
    private final List<CallbackHandler> callbacks;

    private Agent(Builder builder) {
        this.name = builder.name;
        this.model = builder.model;
        this.instructions = builder.instructions;
        this.tools = builder.tools != null ? new ArrayList<>(builder.tools) : new ArrayList<>();
        this.agents = builder.agents != null ? new ArrayList<>(builder.agents) : new ArrayList<>();
        this.strategy = builder.strategy != null ? builder.strategy : Strategy.HANDOFF;
        this.router = builder.router;
        this.guardrails = builder.guardrails != null ? new ArrayList<>(builder.guardrails) : new ArrayList<>();
        this.maxTurns = builder.maxTurns;
        this.maxTokens = builder.maxTokens;
        this.temperature = builder.temperature;
        this.timeoutSeconds = builder.timeoutSeconds;
        this.termination = builder.termination;
        this.outputType = builder.outputType;
        this.sessionId = builder.sessionId;
        this.allowedTransitions = builder.allowedTransitions;
        this.planner = builder.planner;
        this.localCodeExecution = builder.localCodeExecution;
        this.allowedLanguages = builder.allowedLanguages != null ? new ArrayList<>(builder.allowedLanguages) : null;
        this.codeExecutionTimeout = builder.codeExecutionTimeout;
        this.includeContents = builder.includeContents;
        this.thinkingBudgetTokens = builder.thinkingBudgetTokens;
        this.introduction = builder.introduction;
        this.instructionsTemplate = builder.instructionsTemplate;
        this.beforeModelCallback = builder.beforeModelCallback;
        this.afterModelCallback = builder.afterModelCallback;
        this.callbacks = builder.callbacks != null ? new ArrayList<>(builder.callbacks) : new ArrayList<>();
    }

    /**
     * Returns true if this agent is external (no local model — references a deployed workflow).
     */
    public boolean isExternal() {
        return model == null || model.isEmpty();
    }

    /**
     * Create a sequential pipeline: {@code agent.then(other)}.
     *
     * <p>Returns a new Agent with {@code strategy=SEQUENTIAL} combining both sides.
     * Mirrors the {@code >>} operator in the Python SDK.
     *
     * @param other the next agent in the pipeline
     * @return a new sequential pipeline agent
     */
    public Agent then(Agent other) {
        List<Agent> leftAgents = this.strategy == Strategy.SEQUENTIAL ? new ArrayList<>(this.agents) : List.of(this);
        List<Agent> rightAgents = other.strategy == Strategy.SEQUENTIAL ? new ArrayList<>(other.agents) : List.of(other);
        List<Agent> allAgents = new ArrayList<>(leftAgents);
        allAgents.addAll(rightAgents);

        StringBuilder combinedName = new StringBuilder();
        for (int i = 0; i < allAgents.size(); i++) {
            if (i > 0) combinedName.append("_");
            combinedName.append(allAgents.get(i).getName());
        }

        return Agent.builder()
            .name(combinedName.toString())
            .model(this.model)
            .agents(allAgents)
            .strategy(Strategy.SEQUENTIAL)
            .build();
    }

    // ── Getters ──────────────────────────────────────────────────────────

    public String getName() { return name; }
    public String getModel() { return model; }
    public String getInstructions() { return instructions; }
    public List<ToolDef> getTools() { return tools; }
    public List<Agent> getAgents() { return agents; }
    public Strategy getStrategy() { return strategy; }
    public Agent getRouter() { return router; }
    public List<GuardrailDef> getGuardrails() { return guardrails; }
    public int getMaxTurns() { return maxTurns; }
    public Integer getMaxTokens() { return maxTokens; }
    public Double getTemperature() { return temperature; }
    public int getTimeoutSeconds() { return timeoutSeconds; }
    public TerminationCondition getTermination() { return termination; }
    public Class<?> getOutputType() { return outputType; }
    public String getSessionId() { return sessionId; }
    public Map<String, List<String>> getAllowedTransitions() { return allowedTransitions; }
    public boolean isPlanner() { return planner; }
    public boolean isLocalCodeExecution() { return localCodeExecution; }
    public java.util.List<String> getAllowedLanguages() { return allowedLanguages; }
    public int getCodeExecutionTimeout() { return codeExecutionTimeout; }
    public String getIncludeContents() { return includeContents; }
    public Integer getThinkingBudgetTokens() { return thinkingBudgetTokens; }
    public String getIntroduction() { return introduction; }
    public PromptTemplate getInstructionsTemplate() { return instructionsTemplate; }
    public Function<Map<String, Object>, Map<String, Object>> getBeforeModelCallback() { return beforeModelCallback; }
    public Function<Map<String, Object>, Map<String, Object>> getAfterModelCallback() { return afterModelCallback; }
    public List<CallbackHandler> getCallbacks() { return callbacks; }

    public static Builder builder() {
        return new Builder();
    }

    @Override
    public String toString() {
        if (isExternal()) {
            return "Agent{name=" + name + ", external=true}";
        }
        StringBuilder sb = new StringBuilder("Agent{name=").append(name)
            .append(", model=").append(model);
        if (!tools.isEmpty()) sb.append(", tools=").append(tools.size());
        if (!agents.isEmpty()) sb.append(", agents=").append(agents.size()).append(", strategy=").append(strategy);
        sb.append("}");
        return sb.toString();
    }

    /**
     * Fluent builder for {@link Agent}.
     */
    public static class Builder {
        private String name;
        private String model;
        private String instructions;
        private List<ToolDef> tools;
        private List<Agent> agents;
        private Strategy strategy = Strategy.HANDOFF;
        private Agent router;
        private List<GuardrailDef> guardrails;
        private int maxTurns = 25;
        private Integer maxTokens;
        private Double temperature;
        private int timeoutSeconds = 0;
        private TerminationCondition termination;
        private Class<?> outputType;
        private String sessionId;
        private Map<String, List<String>> allowedTransitions;
        private boolean planner = false;
        private boolean localCodeExecution = false;
        private java.util.List<String> allowedLanguages = null;
        private int codeExecutionTimeout = 30;
        private String includeContents;
        private Integer thinkingBudgetTokens;
        private String introduction;
        private PromptTemplate instructionsTemplate;
        private Function<Map<String, Object>, Map<String, Object>> beforeModelCallback;
        private Function<Map<String, Object>, Map<String, Object>> afterModelCallback;
        private List<CallbackHandler> callbacks;

        /** Set the agent name (required). Must match {@code ^[a-zA-Z_][a-zA-Z0-9_-]*$}. */
        public Builder name(String name) {
            this.name = name;
            return this;
        }

        /** Set the LLM model in "provider/model" format (e.g. "openai/gpt-4o"). */
        public Builder model(String model) {
            this.model = model;
            return this;
        }

        /** Set the system prompt / instructions for the agent. */
        public Builder instructions(String instructions) {
            this.instructions = instructions;
            return this;
        }

        /** Set the list of tools the agent can use. */
        public Builder tools(List<ToolDef> tools) {
            this.tools = tools;
            return this;
        }

        /** Set tools with varargs. */
        public Builder tools(ToolDef... tools) {
            this.tools = Arrays.asList(tools);
            return this;
        }

        /** Set the list of sub-agents for multi-agent orchestration. */
        public Builder agents(List<Agent> agents) {
            this.agents = agents;
            return this;
        }

        /** Set sub-agents with varargs. */
        public Builder agents(Agent... agents) {
            this.agents = Arrays.asList(agents);
            return this;
        }

        /** Set the multi-agent orchestration strategy. */
        public Builder strategy(Strategy strategy) {
            this.strategy = strategy;
            return this;
        }

        /** Set the router agent for ROUTER strategy. */
        public Builder router(Agent router) {
            this.router = router;
            return this;
        }

        /** Set guardrails for input/output validation. */
        public Builder guardrails(List<GuardrailDef> guardrails) {
            this.guardrails = guardrails;
            return this;
        }

        /** Set the maximum number of agent loop iterations. */
        public Builder maxTurns(int maxTurns) {
            this.maxTurns = maxTurns;
            return this;
        }

        /** Set the maximum number of tokens for LLM generation. */
        public Builder maxTokens(int maxTokens) {
            this.maxTokens = maxTokens;
            return this;
        }

        /** Set the sampling temperature for the LLM. */
        public Builder temperature(double temperature) {
            this.temperature = temperature;
            return this;
        }

        /** Set the execution timeout in seconds. */
        public Builder timeoutSeconds(int timeoutSeconds) {
            this.timeoutSeconds = timeoutSeconds;
            return this;
        }

        /** Set a composable termination condition. */
        public Builder termination(TerminationCondition termination) {
            this.termination = termination;
            return this;
        }

        /** Set a class for structured output. */
        public Builder outputType(Class<?> outputType) {
            this.outputType = outputType;
            return this;
        }

        /** Set a session ID for multi-turn conversation continuity. */
        public Builder sessionId(String sessionId) {
            this.sessionId = sessionId;
            return this;
        }

        /**
         * Restrict which agents can transfer to which other agents.
         * Keys are source agent names; values are lists of allowed target names.
         */
        public Builder allowedTransitions(Map<String, List<String>> allowedTransitions) {
            this.allowedTransitions = allowedTransitions;
            return this;
        }

        /**
         * Enable planner mode. The server enhances the system prompt with planning
         * instructions so the agent creates a step-by-step plan before executing tools.
         */
        public Builder planner(boolean planner) {
            this.planner = planner;
            return this;
        }

        /**
         * Enable local code execution. When true, the agent can execute code locally
         * using the registered code execution worker.
         */
        public Builder localCodeExecution(boolean localCodeExecution) {
            this.localCodeExecution = localCodeExecution;
            return this;
        }

        /**
         * Set the list of allowed languages for local code execution.
         * Defaults to ["python"] if not specified.
         */
        public Builder allowedLanguages(java.util.List<String> allowedLanguages) {
            this.allowedLanguages = allowedLanguages;
            return this;
        }

        /**
         * Set the timeout in seconds for local code execution.
         * Defaults to 30 seconds.
         */
        public Builder codeExecutionTimeout(int codeExecutionTimeout) {
            this.codeExecutionTimeout = codeExecutionTimeout;
            return this;
        }

        /**
         * Control what context is passed to this sub-agent.
         * Use {@code "none"} for a clean slate (no parent conversation history).
         * Default (null) passes all context.
         */
        public Builder includeContents(String includeContents) {
            this.includeContents = includeContents;
            return this;
        }

        /**
         * Enable extended thinking/reasoning with the given token budget.
         * Only supported by models with extended thinking capability.
         */
        public Builder thinkingBudgetTokens(int thinkingBudgetTokens) {
            this.thinkingBudgetTokens = thinkingBudgetTokens;
            return this;
        }

        /**
         * Set an introduction for this agent. In multi-agent discussions
         * (ROUND_ROBIN, RANDOM, SWARM), the introduction is prepended to
         * the conversation transcript so other agents know who they're
         * collaborating with.
         */
        public Builder introduction(String introduction) {
            this.introduction = introduction;
            return this;
        }

        /**
         * Set a server-side prompt template for agent instructions.
         * Takes precedence over {@link #instructions(String)} if both are set.
         */
        public Builder instructionsTemplate(PromptTemplate instructionsTemplate) {
            this.instructionsTemplate = instructionsTemplate;
            return this;
        }

        /**
         * Register a callback invoked before each LLM call.
         * Receives the current messages list and may return an override response map.
         */
        public Builder beforeModelCallback(Function<Map<String, Object>, Map<String, Object>> beforeModelCallback) {
            this.beforeModelCallback = beforeModelCallback;
            return this;
        }

        /**
         * Register a callback invoked after each LLM call.
         * Receives the LLM result and may return an override response map.
         */
        public Builder afterModelCallback(Function<Map<String, Object>, Map<String, Object>> afterModelCallback) {
            this.afterModelCallback = afterModelCallback;
            return this;
        }

        /**
         * Register composable {@link CallbackHandler} instances for lifecycle hooks.
         * Multiple handlers run in list order; first non-empty return short-circuits.
         */
        public Builder callbacks(List<CallbackHandler> callbacks) {
            this.callbacks = callbacks;
            return this;
        }

        /** Varargs convenience for callbacks. */
        public Builder callbacks(CallbackHandler... callbacks) {
            this.callbacks = Arrays.asList(callbacks);
            return this;
        }

        /**
         * Build the Agent.
         *
         * @throws IllegalArgumentException if name is missing or invalid
         */
        public Agent build() {
            if (name == null || name.isEmpty()) {
                throw new IllegalArgumentException("Agent name is required");
            }
            if (!VALID_NAME.matcher(name).matches()) {
                throw new IllegalArgumentException(
                    "Invalid agent name '" + name + "'. Must start with a letter or underscore "
                    + "and contain only letters, digits, underscores, or hyphens.");
            }
            if (maxTurns < 1) {
                throw new IllegalArgumentException("maxTurns must be >= 1, got " + maxTurns);
            }
            return new Agent(this);
        }
    }
}
