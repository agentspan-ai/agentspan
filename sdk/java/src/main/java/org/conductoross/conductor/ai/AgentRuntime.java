// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai;

import java.io.File;
import java.io.FileWriter;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.conductoross.conductor.ai.enums.Framework;
import org.conductoross.conductor.ai.enums.Strategy;
import org.conductoross.conductor.ai.execution.CliCommandExecutor;
import org.conductoross.conductor.ai.execution.CliConfig;
import org.conductoross.conductor.ai.internal.AgentClient;
import org.conductoross.conductor.ai.internal.AgentRequest;
import org.conductoross.conductor.ai.internal.SseClient;
import org.conductoross.conductor.ai.internal.StartResponse;
import org.conductoross.conductor.ai.internal.WorkerManager;
import org.conductoross.conductor.ai.model.AgentHandle;
import org.conductoross.conductor.ai.model.AgentResult;
import org.conductoross.conductor.ai.model.AgentStream;
import org.conductoross.conductor.ai.model.CompileResponse;
import org.conductoross.conductor.ai.model.DeploymentInfo;
import org.conductoross.conductor.ai.model.GuardrailDef;
import org.conductoross.conductor.ai.model.GuardrailResult;
import org.conductoross.conductor.ai.model.ToolDef;
import org.conductoross.conductor.ai.plans.Plan;
import org.conductoross.conductor.ai.schedule.Schedule;
import org.conductoross.conductor.ai.schedule.Schedules;
import org.conductoross.conductor.ai.skill.Skill;
import org.conductoross.conductor.ai.termination.AndTermination;
import org.conductoross.conductor.ai.termination.MaxMessageTermination;
import org.conductoross.conductor.ai.termination.OrTermination;
import org.conductoross.conductor.ai.termination.TerminationCondition;
import org.conductoross.conductor.ai.termination.TextMentionTermination;
import org.conductoross.conductor.ai.termination.TokenUsageTermination;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import com.netflix.conductor.client.http.WorkflowClient;

import io.orkes.conductor.client.ApiClient;

/**
 * Main runtime for executing agents.
 *
 * <p>Manages worker threads, HTTP communication, and agent lifecycle.
 * Implements {@link AutoCloseable} for use in try-with-resources.
 *
 * <p>Example:
 * <pre>{@code
 * try (AgentRuntime runtime = new AgentRuntime()) {
 *     AgentResult result = runtime.run(agent, "Hello!");
 *     result.printResult();
 * }
 * }</pre>
 */
public class AgentRuntime implements AutoCloseable {
    private static final Logger logger = LoggerFactory.getLogger(AgentRuntime.class);

    private final AgentConfig config;
    /** Single native Conductor client (ApiClient) for the whole runtime — shared by every
     *  typed client (AgentClient/WorkerManager/Schedules) and the SSE stream. */
    private final ApiClient conductorClient;
    /** Agent control-plane client (/api/agent/*) built on the shared Conductor client. */
    private final AgentClient agentClient;
    /** Standard Conductor workflow client for /api/workflow/* — used by AgentHandle to
     *  enrich results with token usage and tool calls after execution completes. */
    private final WorkflowClient workflowClient;

    private final WorkerManager workerManager;
    private volatile Schedules schedules;

    /** Create a runtime with a Conductor client and worker tuning both from environment. */
    public AgentRuntime() {
        this(clientFromEnv(), AgentConfig.fromEnv());
    }

    /** Use the given worker tuning with a Conductor client built from environment. */
    public AgentRuntime(AgentConfig config) {
        this(clientFromEnv(), config);
    }

    /** Use the given Conductor client with worker tuning from environment. */
    public AgentRuntime(ApiClient conductorClient) {
        this(conductorClient, AgentConfig.fromEnv());
    }

    /**
     * Create a runtime with an explicit Conductor client and worker tuning.
     *
     * <p>The {@code conductorClient} (an {@code io.orkes.conductor.client.ApiClient})
     * owns the server URL and auth/token; build one with {@link #clientFromEnv()} or
     * {@link #client(String)}. {@code config} carries only worker-runner tuning.
     *
     * @param conductorClient the native Conductor client (server URL + auth)
     * @param config          worker-runner tuning
     */
    public AgentRuntime(ApiClient conductorClient, AgentConfig config) {
        this.config = config;
        this.conductorClient = conductorClient;
        this.agentClient = new AgentClient(conductorClient);
        this.workflowClient = new WorkflowClient(conductorClient);
        this.workerManager = new WorkerManager(config, conductorClient);
        logger.info("AgentRuntime initialized: {}", conductorClient.getBasePath());
    }

    // ── Conductor client factory ──────────────────────────────────────────

    /**
     * Build a native Conductor client from environment
     * ({@code AGENTSPAN_SERVER_URL}, {@code AGENTSPAN_AUTH_KEY},
     * {@code AGENTSPAN_AUTH_SECRET}).
     */
    public static ApiClient clientFromEnv() {
        return client(
                envVar("AGENTSPAN_SERVER_URL", "http://localhost:6767"),
                envVar("AGENTSPAN_AUTH_KEY", null),
                envVar("AGENTSPAN_AUTH_SECRET", null));
    }

    /** Build an unauthenticated Conductor client for {@code serverUrl}. */
    public static ApiClient client(String serverUrl) {
        return client(serverUrl, null, null);
    }

    /**
     * Build a Conductor client for {@code serverUrl} with optional key/secret auth
     * (the SDK's native token mechanism). The {@code /api} base path is appended.
     *
     * <p>Explicit timeouts are set so transient server delays (e.g. SQLite contention
     * under load) surface as bounded errors rather than blocking forever.
     */
    public static ApiClient client(String serverUrl, String authKey, String authSecret) {
        String basePath = normalizeUrl(serverUrl) + "/api";
        ApiClient.ApiClientBuilder builder = ApiClient.builder()
                .basePath(basePath)
                .connectTimeout(10_000) // ms — fail fast if server unreachable
                .readTimeout(30_000) // ms — bound slow server responses
                .writeTimeout(30_000);
        if (authKey != null && !authKey.isEmpty()) {
            builder.credentials(authKey, authSecret);
        }
        return builder.build();
    }

    private static String envVar(String key, String defaultValue) {
        String val = System.getenv(key);
        return val != null ? val : defaultValue;
    }

    /** Strip a trailing {@code /} and any {@code /api} suffix; defaults if null. */
    private static String normalizeUrl(String url) {
        String s = (url != null ? url : "http://localhost:6767").stripTrailing();
        while (s.endsWith("/")) s = s.substring(0, s.length() - 1);
        if (s.endsWith("/api")) s = s.substring(0, s.length() - 4);
        while (s.endsWith("/")) s = s.substring(0, s.length() - 1);
        return s;
    }

    // ── Synchronous API ──────────────────────────────────────────────────

    /**
     * Compile an agent into a workflow definition without executing it.
     *
     * <p>Serializes the agent and calls {@code POST /api/agent/compile}.
     * Returns the server response containing {@code workflowDef} and
     * {@code requiredWorkers}.
     *
     * <p>Example:
     * <pre>{@code
     * Map<String, Object> plan = runtime.plan(agent);
     * Map<String, Object> workflowDef = (Map<String, Object>) plan.get("workflowDef");
     * }</pre>
     *
     * @param agent the agent to compile
     * @return plan result with workflowDef and requiredWorkers
     */
    public CompileResponse plan(Agent agent) {
        logger.debug("Compiling agent '{}'", agent.getName());
        CompileResponse result = agentClient.compileAgent(agentRequest(agent).build());
        logger.info("Agent '{}' compiled successfully", agent.getName());
        return result;
    }

    /**
     * Execute an agent synchronously and return the result.
     *
     * @param agent  the agent to run
     * @param prompt the user's input message
     * @return the agent result
     */
    public AgentResult run(Agent agent, String prompt) {
        return runAsync(agent, prompt).join();
    }

    /**
     * Execute a {@code Strategy.PLAN_EXECUTE} harness with a deterministic
     * {@link Plan} — skips the planner LLM entirely.
     *
     * <p>The SDK forwards the plan as {@code static_plan} on the start
     * payload; the server's PAC extract_json picks it up as Case-0
     * (highest priority) and discards whatever the planner sub-agent
     * emits. Use this for deterministic pipelines, replays of a
     * previously-emitted plan, or testing.
     *
     * @param agent  the PLAN_EXECUTE harness
     * @param prompt the user's input message
     * @param plan   the deterministic plan to execute
     * @return the agent result
     */
    public AgentResult run(Agent agent, String prompt, Plan plan) {
        return runAsync(agent, prompt, plan).join();
    }

    /**
     * Start an agent (fire-and-forget) and return a handle.
     *
     * @param agent  the agent to start
     * @param prompt the user's input message
     * @return a handle for monitoring and interacting with the agent
     */
    public AgentHandle start(Agent agent, String prompt) {
        return startAsync(agent, prompt).join();
    }

    /**
     * Execute an agent and stream events as they occur.
     *
     * @param agent  the agent to run
     * @param prompt the user's input message
     * @return an AgentStream for consuming events
     */
    public AgentStream stream(Agent agent, String prompt) {
        return streamAsync(agent, prompt).join();
    }

    // ── Async API ────────────────────────────────────────────────────────

    /**
     * Execute an agent asynchronously.
     *
     * @param agent  the agent to run
     * @param prompt the user's input message
     * @return a CompletableFuture that resolves to the agent result
     */
    public CompletableFuture<AgentResult> runAsync(Agent agent, String prompt) {
        return runAsync(agent, prompt, (Plan) null);
    }

    /**
     * Async variant of {@link #run(Agent, String, Plan)}.
     */
    public CompletableFuture<AgentResult> runAsync(Agent agent, String prompt, Plan plan) {
        // Worker registration + runner start happen inside startAsync, under the
        // per-execution domain (runId) for stateful agents. Do NOT pre-register
        // here without that domain: it would build the runner polling the default
        // queue, and the later domain-aware registration could be skipped — leaving
        // the worker polling the wrong queue while the server enqueues under runId.
        return startAsync(agent, prompt, plan)
                .thenCompose(handle -> CompletableFuture.supplyAsync(() -> handle.waitForResult()));
    }

    /**
     * Start an agent asynchronously and return a handle.
     *
     * @param agent  the agent to start
     * @param prompt the user's input message
     * @return a CompletableFuture that resolves to an AgentHandle
     */
    public CompletableFuture<AgentHandle> startAsync(Agent agent, String prompt) {
        return startAsync(agent, prompt, (Plan) null);
    }

    /**
     * Async variant that forwards a deterministic {@link Plan}
     * to the server as {@code static_plan}. Only meaningful for
     * {@code Strategy.PLAN_EXECUTE} harnesses; ignored otherwise.
     */
    public CompletableFuture<AgentHandle> startAsync(Agent agent, String prompt, Plan plan) {
        // Stateful agents get a per-execution domain UUID. The server uses it
        // as taskToDomain for every worker task in this run; local workers are
        // registered under the same domain so they poll the per-execution
        // queue. Without this, concurrent stateful runs share a single domain
        // queue and can dequeue each other's tasks.
        // Mirrors Python runtime._has_stateful_tools + run_id = uuid.uuid4().
        final String runId =
                hasStatefulTools(agent) ? UUID.randomUUID().toString().replace("-", "") : null;
        prepareWorkers(agent, runId);
        workerManager.startAll();

        return CompletableFuture.supplyAsync(() -> {
            String sessionId = agent.getSessionId();

            logger.debug("Starting agent '{}' with prompt: {}", agent.getName(), prompt);

            StartResponse response = agentClient.startAgent(agentRequest(agent)
                    .prompt(prompt)
                    .sessionId(sessionId != null && !sessionId.isEmpty() ? sessionId : null)
                    .runId(runId != null && !runId.isEmpty() ? runId : null)
                    .staticPlan(plan)
                    .build());
            String executionId = response.getExecutionId();
            if (executionId == null) {
                throw new RuntimeException("Server returned no executionId for agent '" + agent.getName() + "'");
            }

            logger.info("Agent '{}' started with execution ID: {}", agent.getName(), executionId);
            return new AgentHandle(executionId, agentClient, workflowClient);
        });
    }

    private static boolean hasStatefulTools(Agent agent) {
        if (agent.isStateful()) return true;
        if (agent.getTools() != null) {
            for (ToolDef t : agent.getTools()) {
                if (t != null && t.isStateful()) return true;
            }
        }
        if (agent.getAgents() != null) {
            for (Agent sub : agent.getAgents()) {
                if (hasStatefulTools(sub)) return true;
            }
        }
        if (agent.getRouter() != null && hasStatefulTools(agent.getRouter())) return true;
        return false;
    }

    /**
     * Build an {@link AgentRequest} pre-populated with the agent definition.
     * The agent's framework string is resolved to a {@link Framework} enum value;
     * if it matches a known framework the request uses {@code framework + rawConfig},
     * otherwise it uses {@code agentConfig} (native path).
     */
    private static AgentRequest.Builder agentRequest(Agent agent) {
        return Framework.of(agent.getFramework())
                .map(fw -> AgentRequest.frameworkAgent(fw, agent))
                .orElseGet(() -> AgentRequest.nativeAgent(agent));
    }

    /**
     * Execute an agent and stream events asynchronously.
     *
     * @param agent  the agent to run
     * @param prompt the user's input message
     * @return a CompletableFuture that resolves to an AgentStream
     */
    public CompletableFuture<AgentStream> streamAsync(Agent agent, String prompt) {
        // Worker registration + runner start happen inside startAsync, under the
        // per-execution domain (runId) for stateful agents — see runAsync.
        return startAsync(agent, prompt).thenApply(handle -> {
            String executionId = handle.getExecutionId();
            SseClient sseClient = new SseClient(conductorClient, executionId);
            sseClient.connect();

            return new AgentStream(executionId, sseClient, agentClient);
        });
    }

    // ── Deploy / Serve / Resume ───────────────────────────────────────────

    /**
     * Compile and register agents on the server without executing them.
     *
     * <p>This is a CI/CD operation. It pushes the workflow definitions and task
     * definitions to the server. It does NOT register local workers or start any
     * processes. Use {@link #serve} separately for the runtime.
     *
     * @param agents one or more agents to deploy
     * @return list of DeploymentInfo, one per deployed agent
     */
    public List<DeploymentInfo> deploy(Agent... agents) {
        if (agents == null || agents.length == 0) {
            throw new IllegalArgumentException("deploy() requires at least one agent");
        }
        List<DeploymentInfo> results = new ArrayList<>();
        for (Agent agent : agents) {
            StartResponse resp = agentClient.deployAgent(agentRequest(agent).build());
            String registeredName = resp.getAgentName() != null ? resp.getAgentName() : agent.getName();
            results.add(new DeploymentInfo(registeredName, agent.getName()));
            logger.info("Deployed agent '{}' as '{}'", agent.getName(), registeredName);
        }
        return results;
    }

    /**
     * Async version of {@link #deploy}.
     *
     * @param agents one or more agents to deploy
     * @return CompletableFuture resolving to list of DeploymentInfo
     */
    public CompletableFuture<List<DeploymentInfo>> deployAsync(Agent... agents) {
        return CompletableFuture.supplyAsync(() -> deploy(agents));
    }

    /**
     * Deploy a single agent and reconcile its cron schedules declaratively.
     *
     * <p>{@code schedules} semantics:
     * <ul>
     *   <li>{@code null} → leave existing schedules untouched.</li>
     *   <li>empty list → purge all schedules for this agent.</li>
     *   <li>non-empty list → upsert these and prune any others for this agent.</li>
     * </ul>
     *
     * @param agent the agent to deploy
     * @param schedules schedules to attach (tri-state semantics above)
     * @return the {@link DeploymentInfo}
     */
    public DeploymentInfo deploy(Agent agent, List<Schedule> schedules) {
        List<DeploymentInfo> infos = deploy(new Agent[] {agent});
        if (schedules != null) {
            schedules().reconcile(agent.getName(), schedules);
        }
        return infos.get(0);
    }

    /** Accessor for the cron-schedule lifecycle API. */
    public Schedules schedules() {
        if (schedules == null) {
            synchronized (this) {
                if (schedules == null) {
                    schedules = new Schedules(conductorClient);
                }
            }
        }
        return schedules;
    }

    /**
     * Register workers and keep them polling until interrupted.
     *
     * <p>This is a runtime operation: it registers the Java tool functions as
     * Conductor workers and starts polling for tasks.
     *
     * @param agents agents whose workers should be served
     */
    public void serve(Agent... agents) {
        if (agents == null || agents.length == 0) {
            throw new IllegalArgumentException("serve() requires at least one agent — without one, no workers would "
                    + "register and the call would block forever.");
        }
        for (Agent agent : agents) {
            prepareWorkers(agent);
        }
        workerManager.startAll();
        logger.info("Serving {} agent(s) — waiting for tasks (Ctrl+C to stop)", agents.length);
        Runtime.getRuntime().addShutdownHook(new Thread(workerManager::stop, "agentspan-serve-shutdown"));
        try {
            Thread.currentThread().join();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    /**
     * Re-attach to an existing agent execution and re-register workers.
     *
     * <p>Fetches the workflow from the server and re-registers tool workers.
     * Returns an {@link AgentHandle} for continued interaction.
     *
     * @param executionId the execution ID from a previous {@link #start} call
     * @param agent       the same Agent definition that was originally executed
     * @return an AgentHandle bound to this runtime
     */
    public AgentHandle resume(String executionId, Agent agent) {
        prepareWorkers(agent);
        return new AgentHandle(executionId, agentClient, workflowClient);
    }

    /**
     * Async version of {@link #resume}.
     *
     * @param executionId the execution ID
     * @param agent       the agent definition originally executed
     * @return CompletableFuture resolving to an AgentHandle
     */
    public CompletableFuture<AgentHandle> resumeAsync(String executionId, Agent agent) {
        return CompletableFuture.supplyAsync(() -> resume(executionId, agent));
    }

    // ── Lifecycle ────────────────────────────────────────────────────────

    /**
     * Shutdown the runtime, stopping all worker threads and releasing HTTP connections.
     *
     * <p>Without explicit cleanup, the OkHttpClient's dispatcher thread pool and connection
     * pool remain alive after the workers stop. Over many sequential test suites this
     * accumulates idle threads and held connections, which increases server-side load and
     * can delay status-poll responses on a shared SQLite-backed server.
     */
    public void shutdown() {
        logger.info("Shutting down AgentRuntime");
        workerManager.stop();
        try {
            // Release the HTTP connection pool and dispatcher thread pool. Without this,
            // each closed AgentRuntime leaves idle OkHttp threads alive (60s keepalive)
            // and held connections, which accumulate over many sequential test suites.
            conductorClient.shutdown();
        } catch (Exception e) {
            logger.debug("Error releasing HTTP client resources: {}", e.getMessage());
        }
    }

    @Override
    public void close() {
        shutdown();
    }

    // ── Drop-in support for native framework agents (run / start / stream /
    //    deploy / serve / plan / resume all accept the raw native object) ──

    /** Drop-in: accepts a native ADK {@code BaseAgent} or any Agentspan {@link Agent}. */
    public AgentResult run(Object agent, String prompt) {
        return run(coerceAgent(agent), prompt);
    }

    /** Drop-in: accepts a native ADK {@code BaseAgent} or any Agentspan {@link Agent}. */
    public CompletableFuture<AgentResult> runAsync(Object agent, String prompt) {
        return runAsync(coerceAgent(agent), prompt);
    }

    /** Drop-in: accepts a native ADK {@code BaseAgent} or any Agentspan {@link Agent}. */
    public AgentHandle start(Object agent, String prompt) {
        return start(coerceAgent(agent), prompt);
    }

    /** Drop-in: accepts a native ADK {@code BaseAgent} or any Agentspan {@link Agent}. */
    public CompletableFuture<AgentHandle> startAsync(Object agent, String prompt) {
        return startAsync(coerceAgent(agent), prompt);
    }

    /** Drop-in: accepts a native ADK {@code BaseAgent} or any Agentspan {@link Agent}. */
    public AgentStream stream(Object agent, String prompt) {
        return stream(coerceAgent(agent), prompt);
    }

    /** Drop-in: accepts a native ADK {@code BaseAgent} or any Agentspan {@link Agent}. */
    public CompletableFuture<AgentStream> streamAsync(Object agent, String prompt) {
        return streamAsync(coerceAgent(agent), prompt);
    }

    /** Drop-in: accepts native ADK {@code BaseAgent} instances (or Agentspan {@link Agent}s). */
    public List<DeploymentInfo> deploy(Object... agents) {
        return deploy(coerceAgents(agents));
    }

    /** Drop-in: accepts native ADK {@code BaseAgent} instances (or Agentspan {@link Agent}s). */
    public CompletableFuture<List<DeploymentInfo>> deployAsync(Object... agents) {
        return deployAsync(coerceAgents(agents));
    }

    /** Drop-in: accepts native ADK {@code BaseAgent} instances (or Agentspan {@link Agent}s). */
    public void serve(Object... agents) {
        serve(coerceAgents(agents));
    }

    /** Drop-in: accepts a native ADK {@code BaseAgent} or any Agentspan {@link Agent}. */
    public CompileResponse plan(Object agent) {
        return plan(coerceAgent(agent));
    }

    /** Drop-in: accepts a native ADK {@code BaseAgent} or any Agentspan {@link Agent}. */
    public AgentHandle resume(String executionId, Object agent) {
        return resume(executionId, coerceAgent(agent));
    }

    /** Drop-in: accepts a native ADK {@code BaseAgent} or any Agentspan {@link Agent}. */
    public CompletableFuture<AgentHandle> resumeAsync(String executionId, Object agent) {
        return resumeAsync(executionId, coerceAgent(agent));
    }

    // Tool-bearing drop-ins for native LangChain4j {@code ChatModel} / LangGraph4j
    // {@code AgentExecutor.Builder} + {@code @Tool} POJOs. These take {@code Object}
    // (not the framework types) so the core class never references compileOnly
    // LangChain4j/LangGraph4j classes in a signature — important because Spring
    // introspects this bean's methods, which would otherwise force-resolve those
    // optional types. The native object is dispatched reflectively in coerceAgent.
    // Fixed-arity overloads (run(Agent,String), run(Object,String)) still win
    // resolution, so these only apply to 3+ arg framework calls.

    /** Drop-in: native LangChain4j {@code ChatModel} / LangGraph4j {@code Builder} + tool POJOs. */
    public AgentResult run(Object agent, String prompt, Object... tools) {
        return run(coerceAgent(agent, tools), prompt);
    }

    /** Drop-in (async): native framework object + tool POJOs. */
    public CompletableFuture<AgentResult> runAsync(Object agent, String prompt, Object... tools) {
        return runAsync(coerceAgent(agent, tools), prompt);
    }

    /** Drop-in (start): native framework object + tool POJOs. */
    public AgentHandle start(Object agent, String prompt, Object... tools) {
        return start(coerceAgent(agent, tools), prompt);
    }

    /** Drop-in (stream): native framework object + tool POJOs. */
    public AgentStream stream(Object agent, String prompt, Object... tools) {
        return stream(coerceAgent(agent, tools), prompt);
    }

    /**
     * Coerce a user-provided agent object to an Agentspan {@link Agent}.
     *
     * <p>Supports {@link Agent} (returned as-is) and these native framework objects, each
     * detected by fully-qualified-name so the core class never hard-references a
     * compileOnly framework type in a signature (resolution happens only in the method
     * body, when such an object is actually passed and the framework is on the classpath):
     * <ul>
     *   <li>{@code com.google.adk.agents.BaseAgent} → {@code AdkBridge}</li>
     *   <li>{@code dev.langchain4j.model.chat.ChatModel} → {@code LangChainBridge}</li>
     *   <li>{@code org.bsc.langgraph4j.agentexecutor.AgentExecutor$Builder} → {@code LangChainBridge}</li>
     * </ul>
     */
    private static Agent coerceAgent(Object agent) {
        return coerceAgent(agent, new Object[0]);
    }

    private static Agent coerceAgent(Object agent, Object[] tools) {
        if (agent == null) {
            throw new IllegalArgumentException("agent is null");
        }
        if (agent instanceof Agent a) {
            return a;
        }
        if (isInstanceOf(agent, "com.google.adk.agents.BaseAgent")) {
            return org.conductoross.conductor.ai.frameworks.AdkBridge.toAgentspan(
                    (com.google.adk.agents.BaseAgent) agent);
        }
        if (isInstanceOf(agent, "dev.langchain4j.model.chat.ChatModel")) {
            return buildLangchainAgent(agent, tools);
        }
        if (isInstanceOf(agent, "org.bsc.langgraph4j.agentexecutor.AgentExecutor$Builder")) {
            return buildLanggraphAgent(agent, tools);
        }
        throw new IllegalArgumentException(
                "Unsupported agent type: " + agent.getClass().getName()
                        + ". Expected org.conductoross.conductor.ai.Agent, a native ADK BaseAgent, "
                        + "a LangChain4j ChatModel, or a LangGraph4j AgentExecutor.Builder.");
    }

    private static Agent buildLangchainAgent(Object model, Object[] tools) {
        return org.conductoross.conductor.ai.frameworks.LangChainBridge.agentBuilder(
                        "langchain_agent",
                        (dev.langchain4j.model.chat.ChatModel) model,
                        null,
                        tools == null ? new Object[0] : tools)
                .build();
    }

    private static Agent buildLanggraphAgent(Object builderObj, Object[] tools) {
        // The LangGraph4j AgentExecutor.Builder carries the ChatModel and the (optional)
        // SystemMessage in package-private fields; recover them reflectively. A future
        // LangGraph4j build that changes the shape fails loudly rather than degrading.
        org.bsc.langgraph4j.agentexecutor.AgentExecutor.Builder builder =
                (org.bsc.langgraph4j.agentexecutor.AgentExecutor.Builder) builderObj;
        dev.langchain4j.model.chat.ChatModel model =
                readBuilderField(builder, "chatModel", dev.langchain4j.model.chat.ChatModel.class);
        if (model == null) {
            throw new IllegalArgumentException("run(AgentExecutor.Builder, ...): the Builder has no chatModel set. "
                    + "Call .chatModel(...) before handing the Builder to the runtime.");
        }
        String systemText = readSystemMessageText(builder);
        // Validate the Builder produces a compilable LangGraph4j StateGraph before shipping the config.
        try {
            builder.build();
        } catch (Exception e) {
            throw new RuntimeException(
                    "AgentExecutor.Builder is not a valid LangGraph4j configuration: " + e.getMessage(), e);
        }
        return org.conductoross.conductor.ai.frameworks.LangChainBridge.agentBuilder(
                        "langgraph_agent", model, systemText, tools == null ? new Object[0] : tools)
                .build();
    }

    @SuppressWarnings("unchecked")
    private static <T> T readBuilderField(Object o, String fieldName, Class<T> expected) {
        try {
            java.lang.reflect.Field f = o.getClass().getDeclaredField(fieldName);
            f.setAccessible(true);
            Object v = f.get(o);
            return expected.isInstance(v) ? (T) v : null;
        } catch (NoSuchFieldException nsf) {
            return null;
        } catch (Throwable t) {
            throw new RuntimeException(
                    "AgentExecutor.Builder field '" + fieldName
                            + "' is no longer accessible — likely a LangGraph4j upgrade. Open an issue.",
                    t);
        }
    }

    private static String readSystemMessageText(Object builder) {
        try {
            java.lang.reflect.Field f = builder.getClass().getDeclaredField("systemMessage");
            f.setAccessible(true);
            Object sys = f.get(builder);
            if (sys == null) return null;
            java.lang.reflect.Method m = sys.getClass().getMethod("text");
            Object t = m.invoke(sys);
            return t instanceof String s && !s.isEmpty() ? s : null;
        } catch (Throwable t) {
            return null;
        }
    }

    private static Agent[] coerceAgents(Object[] agents) {
        if (agents == null) return new Agent[0];
        Agent[] out = new Agent[agents.length];
        for (int i = 0; i < agents.length; i++) {
            try {
                out[i] = coerceAgent(agents[i]);
            } catch (IllegalArgumentException e) {
                throw new IllegalArgumentException("agents[" + i + "]: " + e.getMessage(), e);
            }
        }
        return out;
    }

    /**
     * Walk the entire type hierarchy looking for a type whose FQN matches, so the
     * dispatcher compiles and runs without ADK on the classpath — only callers
     * actually passing native ADK objects trigger the JVM to load ADK classes.
     */
    private static boolean isInstanceOf(Object o, String fqn) {
        return matchesType(o.getClass(), fqn);
    }

    private static boolean matchesType(Class<?> c, String fqn) {
        if (c == null) return false;
        if (fqn.equals(c.getName())) return true;
        if (matchesType(c.getSuperclass(), fqn)) return true;
        for (Class<?> i : c.getInterfaces()) {
            if (matchesType(i, fqn)) return true;
        }
        return false;
    }

    // ── Internal ─────────────────────────────────────────────────────────

    /**
     * Walk the agent tree and register tool workers with the WorkerManager.
     *
     * @param agent the agent (root or sub-agent)
     */
    /**
     * Like {@link #prepareWorkers(Agent)} but registers every worker under the
     * given per-execution domain. Used for stateful agents so concurrent
     * runs don't share a worker queue.
     */
    public void prepareWorkers(Agent agent, String domain) {
        if (domain == null || domain.isEmpty()) {
            prepareWorkers(agent);
            return;
        }
        workerManager.setCurrentDomain(domain);
        try {
            prepareWorkers(agent);
        } finally {
            workerManager.setCurrentDomain(null);
        }
    }

    public void prepareWorkers(Agent agent) {
        if ("skill".equals(agent.getFramework())) {
            for (Skill.SkillWorker worker : Skill.createSkillWorkers(agent)) {
                workerManager.register(worker.getName(), worker.getFunc());
            }
        }

        // Register tools for this agent
        for (ToolDef tool : agent.getTools()) {
            if (tool.getFunc() != null && "worker".equals(tool.getToolType())) {
                // Pass declared credentials through so the worker can fetch
                // them from the server before invoking the handler.
                workerManager.register(
                        tool.getName(),
                        tool.getFunc(),
                        workerManager.getCurrentDomain(),
                        tool.getCredentials(),
                        tool.getTimeoutSeconds());
            }
            // Recursively prepare workers for agent_tool child agents
            if ("agent_tool".equals(tool.getToolType()) && tool.getAgentRef() != null) {
                prepareWorkers(tool.getAgentRef());
            }
        }

        // Register callback workers (legacy single-function style)
        if (agent.getBeforeModelCallback() != null) {
            final Function<Map<String, Object>, Map<String, Object>> beforeCb = agent.getBeforeModelCallback();
            workerManager.register(agent.getName() + "_before_model", inputData -> {
                Map<String, Object> result = beforeCb.apply(inputData);
                return result != null ? result : Collections.emptyMap();
            });
        }
        if (agent.getAfterModelCallback() != null) {
            final Function<Map<String, Object>, Map<String, Object>> afterCb = agent.getAfterModelCallback();
            workerManager.register(agent.getName() + "_after_model", inputData -> {
                Map<String, Object> result = afterCb.apply(inputData);
                return result != null ? result : Collections.emptyMap();
            });
        }

        // Register CallbackHandler list workers — chain all handlers per position
        if (agent.getCallbacks() != null && !agent.getCallbacks().isEmpty()) {
            final List<CallbackHandler> handlers = agent.getCallbacks();
            final String agentName = agent.getName();
            String[][] positionMethods = {
                {"before_agent", "onAgentStart"},
                {"after_agent", "onAgentEnd"},
                {"before_model", "onModelStart"},
                {"after_model", "onModelEnd"},
                {"before_tool", "onToolStart"},
                {"after_tool", "onToolEnd"},
            };
            for (String[] pm : positionMethods) {
                String position = pm[0];
                String methodName = pm[1];
                // Find handlers that override this method
                List<CallbackHandler> active = new ArrayList<>();
                for (CallbackHandler h : handlers) {
                    try {
                        Method m = h.getClass().getMethod(methodName, Map.class);
                        if (!m.getDeclaringClass().equals(CallbackHandler.class)) {
                            active.add(h);
                        }
                    } catch (NoSuchMethodException ignored) {
                    }
                }
                if (active.isEmpty()) continue;

                // Only register if not already registered via legacy callbacks
                final List<CallbackHandler> activeHandlers = active;
                final String taskName = agentName + "_" + position;
                final String mName = methodName;
                workerManager.register(taskName, inputData -> {
                    for (CallbackHandler handler : activeHandlers) {
                        try {
                            Method m = handler.getClass().getMethod(mName, Map.class);
                            m.setAccessible(true); // allow invocation on package-private inner classes
                            Map<String, Object> result = (Map<String, Object>) m.invoke(handler, inputData);
                            if (result != null && !result.isEmpty()) return result;
                        } catch (Exception e) {
                            logger.warn("CallbackHandler {} failed for {}: {}", mName, taskName, e.getMessage());
                        }
                    }
                    return Collections.emptyMap();
                });
            }
        }

        // Register combined guardrail worker per agent (matches Python: {agent_name}_output_guardrail)
        List<GuardrailDef> customGuardrails =
                agent.getGuardrails().stream().filter(g -> g.getFunc() != null).collect(Collectors.toList());
        if (!customGuardrails.isEmpty()) {
            String taskName = agent.getName() + "_output_guardrail";
            workerManager.register(taskName, inputData -> {
                Object rawContent = inputData.get("content");
                String content = rawContent != null ? rawContent.toString() : "";
                int iteration = inputData.get("iteration") instanceof Number
                        ? ((Number) inputData.get("iteration")).intValue()
                        : 0;
                for (GuardrailDef g : customGuardrails) {
                    GuardrailResult result = g.getFunc().apply(content);
                    if (!result.isPassed()) {
                        String onFail = g.getOnFail().toJsonValue();
                        String fixedOutput = result.getFixedOutput();
                        if ("retry".equals(onFail) && iteration >= g.getMaxRetries()) onFail = "raise";
                        if ("fix".equals(onFail) && fixedOutput == null) onFail = "raise";
                        Map<String, Object> out = new LinkedHashMap<>();
                        out.put("passed", false);
                        out.put("message", result.getMessage() != null ? result.getMessage() : "");
                        out.put("on_fail", onFail);
                        out.put("fixed_output", fixedOutput);
                        out.put("guardrail_name", g.getName());
                        out.put("should_continue", "retry".equals(onFail));
                        return out;
                    }
                }
                Map<String, Object> out = new LinkedHashMap<>();
                out.put("passed", true);
                out.put("message", "");
                out.put("on_fail", "pass");
                out.put("fixed_output", null);
                out.put("guardrail_name", "");
                out.put("should_continue", false);
                return out;
            });
        }

        // Register termination condition worker for agents that have one
        if (agent.getTermination() != null) {
            final TerminationCondition termination = agent.getTermination();
            final String taskName = agent.getName() + "_termination";
            workerManager.register(taskName, input -> {
                String result = input.get("result") instanceof String
                        ? (String) input.get("result")
                        : (input.get("result") != null ? input.get("result").toString() : "");
                int iteration =
                        input.get("iteration") instanceof Number ? ((Number) input.get("iteration")).intValue() : 0;
                boolean shouldContinue = evaluateTermination(termination, result, iteration);
                Map<String, Object> out = new LinkedHashMap<>();
                out.put("should_continue", shouldContinue);
                out.put("reason", shouldContinue ? "" : "Termination condition met");
                return out;
            });
        }

        // Register local code execution worker
        if (agent.isLocalCodeExecution()) {
            String taskName = agent.getName() + "_execute_code";
            int codeTimeout = agent.getCodeExecutionTimeout() > 0 ? agent.getCodeExecutionTimeout() : 30;
            workerManager.register(
                    taskName,
                    inputData -> {
                        String language = inputData.get("language") instanceof String
                                ? (String) inputData.get("language")
                                : "python";
                        String code = inputData.get("code") instanceof String ? (String) inputData.get("code") : "";
                        return executeCode(language, code, codeTimeout);
                    },
                    workerManager.getCurrentDomain(),
                    Collections.emptyList(),
                    codeTimeout);
        }

        // Register local CLI command execution worker. Mirrors Python's
        // Agent._attach_cli_tool(): the {name}_run_command tool runs whitelisted
        // commands locally via CliCommandExecutor.
        if (agent.getCliConfig() != null && agent.getCliConfig().isEnabled()) {
            final CliConfig cliCfg = agent.getCliConfig();
            String taskName = agent.getName() + "_run_command";
            workerManager.register(
                    taskName,
                    inputData -> CliCommandExecutor.run(inputData, cliCfg),
                    workerManager.getCurrentDomain(),
                    Collections.emptyList(),
                    cliCfg.getTimeout());
        }

        // Register SWARM transfer workers
        if (Strategy.SWARM.equals(agent.getStrategy()) && !agent.getAgents().isEmpty()) {
            registerSwarmWorkers(agent);
        }

        // Register MANUAL process_selection worker.
        // The server creates a {name}_process_selection SIMPLE task after each
        // HUMAN pick-agent task. This worker maps the selected agent name to its
        // positional index (used by the SWITCH task to route to the right sub-agent).
        if (Strategy.MANUAL.equals(agent.getStrategy()) && !agent.getAgents().isEmpty()) {
            registerManualWorkers(agent);
        }

        // Recurse into sub-agents
        for (Agent subAgent : agent.getAgents()) {
            prepareWorkers(subAgent);
        }

        // Router agent
        if (agent.getRouter() != null) {
            prepareWorkers(agent.getRouter());
        }
    }

    /**
     * Evaluate a termination condition given the current LLM result and iteration count.
     *
     * @return {@code true} if the agent should continue (condition NOT met),
     *         {@code false} if the agent should stop (condition IS met)
     */
    private boolean evaluateTermination(TerminationCondition condition, String result, int iteration) {
        if (condition instanceof TextMentionTermination) {
            String text = ((TextMentionTermination) condition).getText();
            boolean found = result != null && result.contains(text);
            return !found; // should_continue = false when text found (stop)
        } else if (condition instanceof MaxMessageTermination) {
            int max = ((MaxMessageTermination) condition).getMaxMessages();
            return iteration < max; // should_continue = false when iteration >= max
        } else if (condition instanceof TokenUsageTermination) {
            // Token counts are not easily available from result text; always continue
            return true;
        } else if (condition instanceof AndTermination) {
            AndTermination and = (AndTermination) condition;
            boolean leftContinue = evaluateTermination(and.getLeft(), result, iteration);
            boolean rightContinue = evaluateTermination(and.getRight(), result, iteration);
            // AND: stop only when BOTH conditions say stop
            return leftContinue || rightContinue;
        } else if (condition instanceof OrTermination) {
            OrTermination or = (OrTermination) condition;
            boolean leftContinue = evaluateTermination(or.getLeft(), result, iteration);
            boolean rightContinue = evaluateTermination(or.getRight(), result, iteration);
            // OR: stop when EITHER condition says stop
            return leftContinue && rightContinue;
        }
        return true; // unknown condition type — keep going
    }

    /**
     * Register SWARM transfer, check_transfer, and handoff_check workers for the given agent.
     *
     * <p>The server creates these worker tasks for SWARM agents:
     * <ul>
     *   <li>{@code {source}_transfer_to_{peer}} — LLM-called transfer tool (complete with empty output)</li>
     *   <li>{@code {name}_check_transfer} — detects if LLM tool_calls contain a transfer</li>
     *   <li>{@code {name}_handoff_check} — determines the next active_agent and whether to loop</li>
     * </ul>
     */
    private void registerSwarmWorkers(Agent swarmAgent) {
        // Collect all participant names: the SWARM orchestrator (case "0") + sub-agents (cases "1", "2", ...)
        List<String> allNames = new ArrayList<>();
        allNames.add(swarmAgent.getName());
        for (Agent sub : swarmAgent.getAgents()) {
            allNames.add(sub.getName());
        }

        // Register {source}_transfer_to_{peer} workers — just complete with empty output
        for (String source : allNames) {
            for (String peer : allNames) {
                if (!source.equals(peer)) {
                    final String taskName = source + "_transfer_to_" + peer;
                    workerManager.register(taskName, input -> Collections.emptyMap());
                }
            }
        }

        // Register {name}_check_transfer workers for each participant.
        // Input: tool_calls (list of LLM tool calls)
        // Output: is_transfer (boolean), transfer_to (target agent name)
        for (String agentName : allNames) {
            final String prefix = agentName + "_transfer_to_";
            final String taskName = agentName + "_check_transfer";
            workerManager.register(taskName, input -> {
                Object toolCallsRaw = input.get("tool_calls");
                Map<String, Object> out = new LinkedHashMap<>();
                out.put("is_transfer", false);
                out.put("transfer_to", "");
                if (toolCallsRaw instanceof List) {
                    @SuppressWarnings("unchecked")
                    List<Object> toolCalls = (List<Object>) toolCallsRaw;
                    for (Object tc : toolCalls) {
                        String name = null;
                        if (tc instanceof Map) {
                            @SuppressWarnings("unchecked")
                            Map<String, Object> tcMap = (Map<String, Object>) tc;
                            name = tcMap.get("name") instanceof String ? (String) tcMap.get("name") : null;
                            if (name == null && tcMap.get("function") instanceof Map) {
                                @SuppressWarnings("unchecked")
                                Map<String, Object> fn = (Map<String, Object>) tcMap.get("function");
                                name = fn.get("name") instanceof String ? (String) fn.get("name") : null;
                            }
                        }
                        if (name != null && name.startsWith(prefix)) {
                            String target = name.substring(prefix.length());
                            out.put("is_transfer", true);
                            out.put("transfer_to", target);
                            break;
                        }
                    }
                }
                return out;
            });
        }

        // Register {swarmAgent.name}_handoff_check worker.
        // Determines the next active_agent index (string: "0"=parent, "1"=first sub, etc.)
        // and whether to continue looping (handoff=true).
        // Input: is_transfer (bool), transfer_to (agent name), active_agent (string index)
        final List<String> subNames = new ArrayList<>();
        for (Agent sub : swarmAgent.getAgents()) {
            subNames.add(sub.getName());
        }
        final String handoffTaskName = swarmAgent.getName() + "_handoff_check";
        workerManager.register(handoffTaskName, input -> {
            Object isTransferRaw = input.get("is_transfer");
            boolean isTransfer = Boolean.TRUE.equals(isTransferRaw)
                    || "true".equalsIgnoreCase(isTransferRaw != null ? isTransferRaw.toString() : "");
            String transferTo = input.get("transfer_to") instanceof String ? (String) input.get("transfer_to") : "";
            String currentAgent =
                    input.get("active_agent") instanceof String ? (String) input.get("active_agent") : "0";

            Map<String, Object> out = new LinkedHashMap<>();
            if (isTransfer && !transferTo.isEmpty()) {
                // Find the case index for the target agent
                int targetIdx = subNames.indexOf(transferTo);
                if (targetIdx >= 0) {
                    // Sub-agents are cases "1".."N"
                    out.put("active_agent", String.valueOf(targetIdx + 1));
                    out.put("handoff", true);
                } else if (transferTo.equals(swarmAgent.getName())) {
                    // Transfer back to parent (case "0")
                    out.put("active_agent", "0");
                    out.put("handoff", true);
                } else {
                    out.put("active_agent", currentAgent);
                    out.put("handoff", false);
                }
            } else {
                out.put("active_agent", currentAgent);
                out.put("handoff", false);
            }
            return out;
        });
    }

    /**
     * Register the {@code {name}_process_selection} worker for MANUAL strategy agents.
     *
     * <p>The server's MANUAL workflow loop has:
     * <ol>
     *   <li>HUMAN task ({@code {name}_pick_agent}) — pauses for human selection</li>
     *   <li>SIMPLE task ({@code {name}_process_selection}) — maps agent name → index</li>
     *   <li>SWITCH task routes to the selected sub-agent sub-workflow</li>
     * </ol>
     * This worker receives {@code {"human_output": {"selected": "<agentName>"}}} and
     * returns {@code {"selected": "<index>"}} where the index is the 0-based position
     * of the selected agent in the agents list.
     */
    @SuppressWarnings("unchecked")
    private void registerManualWorkers(Agent manualAgent) {
        List<Agent> subAgents = manualAgent.getAgents();
        Map<String, String> nameToIndex = new HashMap<>();
        for (int i = 0; i < subAgents.size(); i++) {
            nameToIndex.put(subAgents.get(i).getName(), String.valueOf(i));
        }

        final String taskName = manualAgent.getName() + "_process_selection";
        workerManager.register(taskName, inputData -> {
            String selected = null;
            Object humanOutput = inputData.get("human_output");
            if (humanOutput instanceof Map) {
                Object sel = ((Map<Object, Object>) humanOutput).get("selected");
                if (sel instanceof String) {
                    selected = (String) sel;
                }
            }
            String index = (selected != null) ? nameToIndex.get(selected) : null;
            if (index == null) {
                logger.warn("MANUAL process_selection: unknown agent '{}'; defaulting to 0", selected);
                index = "0";
            }
            Map<String, Object> out = new HashMap<>();
            out.put("selected", index);
            return out;
        });
    }

    private Map<String, Object> executeCode(String language, String code, int timeoutSeconds) {
        Map<String, Object> result = new LinkedHashMap<>();
        try {
            String interpreter;
            switch (language.toLowerCase()) {
                case "python":
                case "python3":
                    interpreter = "python3";
                    break;
                case "bash":
                case "sh":
                    interpreter = "bash";
                    break;
                case "node":
                case "javascript":
                    interpreter = "node";
                    break;
                default:
                    interpreter = language;
            }
            // Write code to temp file
            File tmpFile = File.createTempFile("agentspan_code_", language.startsWith("python") ? ".py" : ".sh");
            tmpFile.deleteOnExit();
            try (FileWriter fw = new FileWriter(tmpFile)) {
                fw.write(code);
            }

            ProcessBuilder pb = new ProcessBuilder(interpreter, tmpFile.getAbsolutePath());
            pb.redirectErrorStream(true);
            Process process = pb.start();

            boolean finished = process.waitFor(timeoutSeconds, TimeUnit.SECONDS);
            String output = new String(process.getInputStream().readAllBytes());

            if (!finished) {
                process.destroyForcibly();
                result.put("output", output);
                result.put("error", "Code execution timed out after " + timeoutSeconds + "s");
                result.put("exit_code", -1);
                result.put("success", false);
            } else {
                result.put("output", output);
                result.put("exit_code", process.exitValue());
                result.put("success", process.exitValue() == 0);
                if (process.exitValue() != 0) {
                    result.put("error", "Process exited with code " + process.exitValue());
                }
            }
            tmpFile.delete();
        } catch (Exception e) {
            result.put("output", "");
            result.put("error", e.getMessage());
            result.put("exit_code", -1);
            result.put("success", false);
        }
        return result;
    }
}
