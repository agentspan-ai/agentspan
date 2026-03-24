// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan;

import dev.agentspan.internal.AgentConfigSerializer;
import dev.agentspan.internal.HttpApi;
import dev.agentspan.internal.SseClient;
import dev.agentspan.internal.WorkerManager;
import dev.agentspan.model.AgentHandle;
import dev.agentspan.model.AgentResult;
import dev.agentspan.model.AgentStream;
import dev.agentspan.model.ToolDef;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executors;

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
    private final HttpApi httpApi;
    private final WorkerManager workerManager;
    private final AgentConfigSerializer serializer;

    /**
     * Create a runtime using environment variable configuration.
     */
    public AgentRuntime() {
        this(AgentConfig.fromEnv());
    }

    /**
     * Create a runtime with explicit configuration.
     *
     * @param config the agent configuration
     */
    public AgentRuntime(AgentConfig config) {
        this.config = config;
        this.httpApi = new HttpApi(config);
        this.workerManager = new WorkerManager(config);
        this.serializer = new AgentConfigSerializer();
        logger.info("AgentRuntime initialized: {}", config.getServerUrl());
    }

    // ── Synchronous API ──────────────────────────────────────────────────

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
        prepareWorkers(agent);
        workerManager.startAll();

        return startAsync(agent, prompt).thenCompose(handle ->
            CompletableFuture.supplyAsync(() -> handle.waitForResult())
        );
    }

    /**
     * Start an agent asynchronously and return a handle.
     *
     * @param agent  the agent to start
     * @param prompt the user's input message
     * @return a CompletableFuture that resolves to an AgentHandle
     */
    public CompletableFuture<AgentHandle> startAsync(Agent agent, String prompt) {
        prepareWorkers(agent);
        workerManager.startAll();

        return CompletableFuture.supplyAsync(() -> {
            Map<String, Object> agentConfig = serializer.serialize(agent);
            String sessionId = agent.getSessionId();

            logger.debug("Starting agent '{}' with prompt: {}", agent.getName(), prompt);

            Map<String, Object> response = httpApi.startAgent(agentConfig, prompt, sessionId);
            String workflowId = extractWorkflowId(response);

            logger.info("Agent '{}' started with workflow ID: {}", agent.getName(), workflowId);
            return new AgentHandle(workflowId, httpApi);
        });
    }

    /**
     * Execute an agent and stream events asynchronously.
     *
     * @param agent  the agent to run
     * @param prompt the user's input message
     * @return a CompletableFuture that resolves to an AgentStream
     */
    public CompletableFuture<AgentStream> streamAsync(Agent agent, String prompt) {
        prepareWorkers(agent);
        workerManager.startAll();

        return startAsync(agent, prompt).thenApply(handle -> {
            String workflowId = handle.getWorkflowId();
            String sseUrl = config.getServerUrl() + "/agent/" + workflowId + "/stream";

            SseClient sseClient = new SseClient(sseUrl, config, httpApi.getHttpClient());
            sseClient.connect();

            return new AgentStream(workflowId, sseClient, httpApi);
        });
    }

    // ── Lifecycle ────────────────────────────────────────────────────────

    /**
     * Shutdown the runtime, stopping all worker threads.
     */
    public void shutdown() {
        logger.info("Shutting down AgentRuntime");
        workerManager.stop();
    }

    @Override
    public void close() {
        shutdown();
    }

    // ── Internal ─────────────────────────────────────────────────────────

    /**
     * Walk the agent tree and register tool workers with the WorkerManager.
     *
     * @param agent the agent (root or sub-agent)
     */
    public void prepareWorkers(Agent agent) {
        // Register tools for this agent
        for (ToolDef tool : agent.getTools()) {
            if (tool.getFunc() != null && "worker".equals(tool.getToolType())) {
                workerManager.register(tool.getName(), tool.getFunc());
            }
        }

        // Register guardrail workers
        for (dev.agentspan.model.GuardrailDef guardrail : agent.getGuardrails()) {
            if (guardrail.getFunc() != null) {
                String taskName = guardrail.getName() + "_guardrail";
                workerManager.register(taskName, inputData -> {
                    String content = (String) inputData.getOrDefault("content", "");
                    return guardrail.getFunc().apply(content);
                });
            }
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

    private String extractWorkflowId(Map<String, Object> response) {
        // Try several possible keys
        Object id = response.get("workflowId");
        if (id != null) return id.toString();

        id = response.get("id");
        if (id != null) return id.toString();

        id = response.get("correlationId");
        if (id != null) return id.toString();

        // If only one value in the map, use it
        if (response.size() == 1) {
            return response.values().iterator().next().toString();
        }

        throw new RuntimeException("Cannot extract workflow ID from response: " + response);
    }
}
