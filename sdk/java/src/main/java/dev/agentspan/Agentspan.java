// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan;

import dev.agentspan.model.AgentHandle;
import dev.agentspan.model.AgentResult;
import dev.agentspan.model.AgentStream;
import dev.agentspan.model.AsyncAgentStream;
import dev.agentspan.model.DeploymentInfo;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;

/**
 * Static facade for the Agentspan SDK.
 *
 * <p>Provides a convenient one-liner API using a shared singleton {@link AgentRuntime}.
 * For full lifecycle control, use {@link AgentRuntime} directly.
 *
 * <p>Example:
 * <pre>{@code
 * Agent agent = Agent.builder()
 *     .name("assistant")
 *     .model("openai/gpt-4o")
 *     .build();
 *
 * AgentResult result = Agentspan.run(agent, "Hello!");
 * result.printResult();
 * Agentspan.shutdown();
 * }</pre>
 */
public final class Agentspan {
    private static final Logger logger = LoggerFactory.getLogger(Agentspan.class);

    private static volatile AgentRuntime defaultRuntime;
    private static volatile AgentConfig defaultConfig;
    private static final Object lock = new Object();

    private Agentspan() {}

    /**
     * Pre-configure the default singleton runtime.
     *
     * <p>Must be called before the first {@link #run}, {@link #start}, or {@link #stream} call.
     *
     * @param config the configuration to use
     * @throws IllegalStateException if the runtime is already initialized
     */
    public static void configure(AgentConfig config) {
        synchronized (lock) {
            if (defaultRuntime != null) {
                throw new IllegalStateException(
                    "configure() must be called before the first run/start/stream call. "
                    + "Call shutdown() first to reset the default runtime.");
            }
            defaultConfig = config;
        }
    }

    /**
     * Execute an agent synchronously and return the result.
     *
     * @param agent  the agent to run
     * @param prompt the user's input message
     * @return the agent result
     */
    public static AgentResult run(Agent agent, String prompt) {
        return getOrCreateRuntime().run(agent, prompt);
    }

    /**
     * Execute an agent asynchronously.
     *
     * @param agent  the agent to run
     * @param prompt the user's input message
     * @return a CompletableFuture that resolves to the agent result
     */
    public static CompletableFuture<AgentResult> runAsync(Agent agent, String prompt) {
        return getOrCreateRuntime().runAsync(agent, prompt);
    }

    /**
     * Start an agent (fire-and-forget) and return a handle.
     *
     * @param agent  the agent to start
     * @param prompt the user's input message
     * @return a handle for monitoring and interacting with the agent
     */
    public static AgentHandle start(Agent agent, String prompt) {
        return getOrCreateRuntime().start(agent, prompt);
    }

    /**
     * Execute an agent and stream events as they occur.
     *
     * @param agent  the agent to run
     * @param prompt the user's input message
     * @return an AgentStream for consuming events
     */
    public static AgentStream stream(Agent agent, String prompt) {
        return getOrCreateRuntime().stream(agent, prompt);
    }

    /**
     * Start an agent asynchronously and return a CompletableFuture for the handle.
     *
     * @param agent  the agent to start
     * @param prompt the user's input message
     * @return a CompletableFuture that resolves to an AgentHandle
     */
    public static CompletableFuture<AgentHandle> startAsync(Agent agent, String prompt) {
        return getOrCreateRuntime().startAsync(agent, prompt);
    }

    /**
     * Stream agent events asynchronously.
     *
     * @param agent  the agent to run
     * @param prompt the user's input message
     * @return a CompletableFuture resolving to an AgentStream
     */
    public static CompletableFuture<AgentStream> streamAsync(Agent agent, String prompt) {
        return getOrCreateRuntime().streamAsync(agent, prompt);
    }

    /**
     * Compile an agent and return the server's plan without executing it.
     *
     * @param agent the agent to plan
     * @return the plan response map from the server
     */
    public static Map<String, Object> plan(Agent agent) {
        return getOrCreateRuntime().plan(agent);
    }

    /**
     * Deploy agents to the server without executing them (CI/CD operation).
     *
     * @param agents one or more agents to deploy
     * @return list of DeploymentInfo, one per deployed agent
     */
    public static List<DeploymentInfo> deploy(Agent... agents) {
        return getOrCreateRuntime().deploy(agents);
    }

    /**
     * Deploy agents to the server asynchronously.
     *
     * @param agents one or more agents to deploy
     * @return CompletableFuture resolving to list of DeploymentInfo
     */
    public static CompletableFuture<List<DeploymentInfo>> deployAsync(Agent... agents) {
        return getOrCreateRuntime().deployAsync(agents);
    }

    /**
     * Re-attach to an existing agent execution and re-register workers.
     *
     * @param executionId the execution ID from a previous start() call
     * @param agent       the same Agent definition originally executed
     * @return an AgentHandle for continued interaction
     */
    public static AgentHandle resume(String executionId, Agent agent) {
        return getOrCreateRuntime().resume(executionId, agent);
    }

    /**
     * Async version of {@link #resume}.
     *
     * @param executionId the execution ID
     * @param agent       the agent definition originally executed
     * @return CompletableFuture resolving to an AgentHandle
     */
    public static CompletableFuture<AgentHandle> resumeAsync(String executionId, Agent agent) {
        return getOrCreateRuntime().resumeAsync(executionId, agent);
    }

    /**
     * Register workers and keep them polling until interrupted (blocking).
     *
     * @param agents agents whose workers should be served
     */
    public static void serve(Agent... agents) {
        getOrCreateRuntime().serve(agents);
    }

    /**
     * Shutdown the default singleton runtime, stopping all worker threads.
     *
     * <p>Call this for explicit cleanup in long-running servers. In simple scripts,
     * this is not necessary as workers are daemon threads.
     */
    public static void shutdown() {
        synchronized (lock) {
            if (defaultRuntime != null) {
                logger.info("Shutting down default Agentspan singleton runtime");
                defaultRuntime.shutdown();
                defaultRuntime = null;
            }
        }
    }

    private static AgentRuntime getOrCreateRuntime() {
        if (defaultRuntime == null) {
            synchronized (lock) {
                if (defaultRuntime == null) {
                    AgentConfig config = defaultConfig != null ? defaultConfig : AgentConfig.fromEnv();
                    defaultRuntime = new AgentRuntime(config);
                    logger.info("Created default Agentspan singleton runtime");

                    // Register shutdown hook
                    Runtime.getRuntime().addShutdownHook(new Thread(() -> {
                        if (defaultRuntime != null) {
                            defaultRuntime.shutdown();
                        }
                    }, "agentspan-shutdown"));
                }
            }
        }
        return defaultRuntime;
    }
}
