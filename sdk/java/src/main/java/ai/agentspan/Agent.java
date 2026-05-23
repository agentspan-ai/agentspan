// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan;

import ai.agentspan.enums.Strategy;
import ai.agentspan.execution.CliConfig;
import ai.agentspan.handoff.Handoff;
import ai.agentspan.model.GuardrailDef;
import ai.agentspan.model.PrefillToolCall;
import ai.agentspan.model.PromptTemplate;
import ai.agentspan.model.ToolDef;
import ai.agentspan.termination.TerminationCondition;

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
    private final List<Handoff> handoffs;
    private final Map<String, List<String>> allowedTransitions;
    /** Plan-first preamble flag (Google ADK style). Renamed from
     *  ``planner`` because the server-side AgentConfig now uses that JSON
     *  key for the PLAN_EXECUTE planner sub-agent slot. Wire-incompatible
     *  with the old name. */
    private final boolean enablePlanning;
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
    private final List<String> requiredTools;
    private final List<String> credentials;
    private final Map<String, Object> metadata;
    private final List<String> allowedCommands;
    private final String stopWhenTaskName;
    private final Integer fallbackMaxTurns;
    /** PLAN_EXECUTE named slots: planner (required) and fallback (optional).
     *  The server rejects the legacy ``agents=[planner, fallback]`` positional
     *  shape with HTTP 400 once strategy is PLAN_EXECUTE — set these instead. */
    private final Agent planner;
    private final Agent fallback;
    /** PLAN_EXECUTE planner context — text snippets / URLs whose bodies are
     *  fetched at planner-run time and appended to the planner prompt as a
     *  ``## Reference Context`` block. Only meaningful with PLAN_EXECUTE;
     *  the server compiler skips emission for any other strategy. */
    private final List<ai.agentspan.plans.Context> plannerContext;
    private final List<PrefillToolCall> prefillTools;
    private final boolean synthesize;
    private final boolean stateful;
    private final String baseUrl;
    private final ai.agentspan.gate.TextGate gate;
    private final Function<Map<String, Object>, Map<String, Object>> beforeAgentCallback;
    private final Function<Map<String, Object>, Map<String, Object>> afterAgentCallback;
    private final String framework;
    private final Map<String, Object> frameworkConfig;
    private final CliConfig cliConfig;

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
        this.handoffs = builder.handoffs != null ? new ArrayList<>(builder.handoffs) : new ArrayList<>();
        this.allowedTransitions = builder.allowedTransitions;
        this.enablePlanning = builder.enablePlanning;
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
        this.requiredTools = builder.requiredTools != null ? new ArrayList<>(builder.requiredTools) : new ArrayList<>();
        this.credentials = builder.credentials != null ? new ArrayList<>(builder.credentials) : new ArrayList<>();
        this.metadata = builder.metadata;
        this.allowedCommands = builder.allowedCommands != null ? new ArrayList<>(builder.allowedCommands) : new ArrayList<>();
        this.stopWhenTaskName = builder.stopWhenTaskName;
        this.fallbackMaxTurns = builder.fallbackMaxTurns;
        this.planner = builder.planner;
        this.fallback = builder.fallback;
        // plannerContext is only meaningful for PLAN_EXECUTE. Reject loudly
        // here so misconfig doesn't propagate to the server — same shape
        // as the planner/fallback validation in Python/TS SDKs.
        if (builder.plannerContext != null && !builder.plannerContext.isEmpty()) {
            if (builder.strategy != ai.agentspan.enums.Strategy.PLAN_EXECUTE) {
                throw new IllegalArgumentException(
                        "plannerContext is only valid with strategy=PLAN_EXECUTE. "
                                + "Got strategy=" + builder.strategy + ". The context block "
                                + "is appended to the planner's user prompt at runtime, "
                                + "which only exists in PLAN_EXECUTE.");
            }
            this.plannerContext = new ArrayList<>(builder.plannerContext);
        } else {
            this.plannerContext = null;
        }
        this.prefillTools = builder.prefillTools != null ? new ArrayList<>(builder.prefillTools) : new ArrayList<>();
        this.synthesize = builder.synthesize;
        this.stateful = builder.stateful;
        this.baseUrl = builder.baseUrl;
        this.gate = builder.gate;
        this.beforeAgentCallback = builder.beforeAgentCallback;
        this.afterAgentCallback = builder.afterAgentCallback;
        this.framework = builder.framework;
        this.frameworkConfig = builder.frameworkConfig;
        this.cliConfig = builder.cliConfig;
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
    public List<Handoff> getHandoffs() { return handoffs; }
    public Map<String, List<String>> getAllowedTransitions() { return allowedTransitions; }
    public boolean isEnablePlanning() { return enablePlanning; }
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
    public List<String> getRequiredTools() { return requiredTools; }
    public List<String> getCredentials() { return credentials; }
    public Map<String, Object> getMetadata() { return metadata; }
    public List<String> getAllowedCommands() { return allowedCommands; }
    public String getStopWhenTaskName() { return stopWhenTaskName; }
    public Integer getFallbackMaxTurns() { return fallbackMaxTurns; }
    public Agent getPlanner() { return planner; }
    public Agent getFallback() { return fallback; }
    public List<ai.agentspan.plans.Context> getPlannerContext() { return plannerContext; }
    public List<PrefillToolCall> getPrefillTools() { return prefillTools; }
    public boolean isSynthesize() { return synthesize; }
    public boolean isStateful() { return stateful; }
    public String getBaseUrl() { return baseUrl; }
    public ai.agentspan.gate.TextGate getGate() { return gate; }
    public Function<Map<String, Object>, Map<String, Object>> getBeforeAgentCallback() { return beforeAgentCallback; }
    public Function<Map<String, Object>, Map<String, Object>> getAfterAgentCallback() { return afterAgentCallback; }
    public String getFramework() { return framework; }
    public Map<String, Object> getFrameworkConfig() { return frameworkConfig; }
    public CliConfig getCliConfig() { return cliConfig; }

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
        private List<Handoff> handoffs;
        private Map<String, List<String>> allowedTransitions;
        private boolean enablePlanning = false;
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
        private List<String> requiredTools;
        private List<String> credentials;
        private Map<String, Object> metadata;
        private List<String> allowedCommands;
        private String stopWhenTaskName;
        private Integer fallbackMaxTurns;
        private Agent planner;
        private Agent fallback;
        private List<ai.agentspan.plans.Context> plannerContext;
        private List<PrefillToolCall> prefillTools;
        private boolean synthesize = true;
        private boolean stateful = false;
        private String baseUrl;
        private ai.agentspan.gate.TextGate gate;
        private Function<Map<String, Object>, Map<String, Object>> beforeAgentCallback;
        private Function<Map<String, Object>, Map<String, Object>> afterAgentCallback;
        private String framework;
        private Map<String, Object> frameworkConfig;
        private CliConfig cliConfig;

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

        /** Add tools to the agent (accumulates, does not replace). */
        public Builder tools(List<ToolDef> tools) {
            if (this.tools == null) this.tools = new ArrayList<>();
            this.tools.addAll(tools);
            return this;
        }

        /** Add tools with varargs (accumulates, does not replace). */
        public Builder tools(ToolDef... tools) {
            if (this.tools == null) this.tools = new ArrayList<>();
            this.tools.addAll(Arrays.asList(tools));
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

        /** Convenience: set guardrails via varargs. */
        public Builder guardrails(GuardrailDef... guardrails) {
            this.guardrails = guardrails == null ? null : java.util.Arrays.asList(guardrails);
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
        public Builder handoffs(List<Handoff> handoffs) {
            this.handoffs = new ArrayList<>(handoffs);
            return this;
        }

        public Builder handoffs(Handoff... handoffs) {
            this.handoffs = new ArrayList<>(Arrays.asList(handoffs));
            return this;
        }

        public Builder allowedTransitions(Map<String, List<String>> allowedTransitions) {
            this.allowedTransitions = allowedTransitions;
            return this;
        }

        /**
         * Enable plan-first preamble (Google ADK style). When true, the
         * server enhances the system prompt with "create a step-by-step
         * plan before executing tools." Renamed from {@code planner(...)}
         * because the server now uses the {@code planner} JSON key for the
         * PLAN_EXECUTE planner sub-agent slot — keeping the old name would
         * ship a boolean into a sub-agent slot.
         */
        public Builder enablePlanning(boolean enablePlanning) {
            this.enablePlanning = enablePlanning;
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
         * Enforce that specific tool names are called during the agent's run.
         * Matches Python's {@code required_tools} parameter.
         */
        public Builder requiredTools(List<String> requiredTools) {
            this.requiredTools = requiredTools;
            return this;
        }

        /** Varargs convenience for requiredTools. */
        public Builder requiredTools(String... requiredTools) {
            this.requiredTools = Arrays.asList(requiredTools);
            return this;
        }

        /**
         * Agent-level credential names to inject into the execution context.
         * Matches Python's {@code credentials} parameter.
         */
        public Builder credentials(List<String> credentials) {
            this.credentials = credentials;
            return this;
        }

        /** Varargs convenience for credentials. */
        public Builder credentials(String... credentials) {
            this.credentials = Arrays.asList(credentials);
            return this;
        }

        /**
         * Arbitrary metadata attached to the agent / workflow definition.
         * Matches Python's {@code metadata} parameter.
         */
        public Builder metadata(Map<String, Object> metadata) {
            this.metadata = metadata;
            return this;
        }

        /**
         * Shell commands allowed when {@code localCodeExecution} is enabled.
         * Matches Python's {@code allowed_commands} parameter.
         * Java always emits an empty list if not set.
         */
        public Builder allowedCommands(List<String> allowedCommands) {
            this.allowedCommands = allowedCommands;
            return this;
        }

        /**
         * Name of a Conductor worker task that acts as an early-exit condition.
         * The worker returns {@code {"stop": true}} to end the agent loop.
         * Matches Python's {@code stop_when} parameter.
         *
         * @param taskName the worker task name (also used as the workflow task reference)
         */
        public Builder stopWhen(String taskName) {
            this.stopWhenTaskName = taskName;
            return this;
        }

        /** Max LLM turns for the fallback agent in PLAN_EXECUTE strategy. */
        public Builder fallbackMaxTurns(int fallbackMaxTurns) {
            this.fallbackMaxTurns = fallbackMaxTurns;
            return this;
        }

        /**
         * PLAN_EXECUTE planner sub-agent (required when ``strategy == PLAN_EXECUTE``).
         * The server rejects ``agents=[planner, fallback]`` for this strategy with
         * HTTP 400 — use this named slot instead.
         */
        public Builder planner(Agent planner) {
            this.planner = planner;
            return this;
        }

        /**
         * PLAN_EXECUTE fallback sub-agent (optional). Used when the planner's
         * output cannot be compiled into a sub-workflow, or when the compiled
         * sub-workflow itself fails at runtime.
         */
        public Builder fallback(Agent fallback) {
            this.fallback = fallback;
            return this;
        }

        /**
         * PLAN_EXECUTE planner context — a list of text snippets and/or URLs
         * appended to the planner's user prompt as a {@code ## Reference Context}
         * block at runtime. URLs are fetched per planner invocation (no
         * compile-time fetch, no cache) so doc edits go live without recompile.
         *
         * <p>Pass {@link ai.agentspan.plans.Context} entries built via
         * {@code Context.text(...)} or {@code Context.url(...)} /
         * {@code Context.builder().url(...).header(...).build()} for credentialed
         * fetches — credential placeholders in the {@code ${CRED_NAME}} shape
         * are escaped server-side and resolved by the same credential pipeline
         * as HTTP tool headers.
         */
        public Builder plannerContext(List<ai.agentspan.plans.Context> plannerContext) {
            this.plannerContext = plannerContext;
            return this;
        }

        /** Shorthand: single-entry text-only planner context. Equivalent to
         *  {@code plannerContext(List.of(Context.text(text)))}. */
        public Builder plannerContext(String... texts) {
            List<ai.agentspan.plans.Context> ctx = new ArrayList<>();
            for (String t : texts) {
                ctx.add(ai.agentspan.plans.Context.text(t));
            }
            this.plannerContext = ctx;
            return this;
        }

        /** Tool calls to execute before the first LLM turn. Results are injected into context. */
        public Builder prefillTools(List<PrefillToolCall> prefillTools) {
            this.prefillTools = prefillTools;
            return this;
        }

        /**
         * Whether a final LLM synthesis step is added after handoff/router/swarm strategies.
         * Default true (backward compatible). Set to false to pass the last specialist's output through directly.
         */
        public Builder synthesize(boolean synthesize) {
            this.synthesize = synthesize;
            return this;
        }

        /** Enable stateful mode — the agent persists conversation history across runs. */
        public Builder stateful(boolean stateful) {
            this.stateful = stateful;
            return this;
        }

        /** Override the base URL for the LLM provider (e.g. a proxy or local endpoint). */
        public Builder baseUrl(String baseUrl) {
            this.baseUrl = baseUrl;
            return this;
        }

        /**
         * Attach a gate to stop a sequential pipeline if this agent's output contains the sentinel text.
         * Only meaningful when the agent is part of a sequential pipeline ({@code agent.then(next)}).
         */
        public Builder gate(ai.agentspan.gate.TextGate gate) {
            this.gate = gate;
            return this;
        }

        /** Register a callback invoked before this agent's entire execution (before any LLM calls). */
        public Builder beforeAgentCallback(Function<Map<String, Object>, Map<String, Object>> beforeAgentCallback) {
            this.beforeAgentCallback = beforeAgentCallback;
            return this;
        }

        /** Register a callback invoked after this agent's entire execution (after all LLM calls). */
        public Builder afterAgentCallback(Function<Map<String, Object>, Map<String, Object>> afterAgentCallback) {
            this.afterAgentCallback = afterAgentCallback;
            return this;
        }

        /** Set the framework type (e.g. {@code "skill"}) for framework-backed agents. */
        public Builder framework(String framework) {
            this.framework = framework;
            return this;
        }

        /** Set the raw framework configuration map sent verbatim to the server. */
        public Builder frameworkConfig(Map<String, Object> frameworkConfig) {
            this.frameworkConfig = frameworkConfig;
            return this;
        }

        /** Configure CLI command execution for this agent. */
        public Builder cliConfig(CliConfig cliConfig) {
            this.cliConfig = cliConfig;
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
