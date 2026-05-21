// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan;

import ai.agentspan.model.AgentHandle;
import ai.agentspan.model.AgentResult;
import ai.agentspan.model.AgentStream;
import ai.agentspan.model.DeploymentInfo;
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

    // ── Drop-in support for native framework agents (run / start / stream /
    //    deploy / serve / plan / resume all accept the raw native object) ──

    /** Drop-in: accepts a native ADK {@code BaseAgent} or any Agentspan {@link Agent}. */
    public static AgentResult run(Object agent, String prompt) {
        return run(coerceAgent(agent), prompt);
    }

    /** Drop-in: accepts a native ADK {@code BaseAgent} or any Agentspan {@link Agent}. */
    public static CompletableFuture<AgentResult> runAsync(Object agent, String prompt) {
        return runAsync(coerceAgent(agent), prompt);
    }

    /** Drop-in: accepts a native ADK {@code BaseAgent} or any Agentspan {@link Agent}. */
    public static AgentHandle start(Object agent, String prompt) {
        return start(coerceAgent(agent), prompt);
    }

    /** Drop-in: accepts a native ADK {@code BaseAgent} or any Agentspan {@link Agent}. */
    public static CompletableFuture<AgentHandle> startAsync(Object agent, String prompt) {
        return startAsync(coerceAgent(agent), prompt);
    }

    /** Drop-in: accepts a native ADK {@code BaseAgent} or any Agentspan {@link Agent}. */
    public static AgentStream stream(Object agent, String prompt) {
        return stream(coerceAgent(agent), prompt);
    }

    /** Drop-in: accepts a native ADK {@code BaseAgent} or any Agentspan {@link Agent}. */
    public static CompletableFuture<AgentStream> streamAsync(Object agent, String prompt) {
        return streamAsync(coerceAgent(agent), prompt);
    }

    /** Drop-in: accepts native ADK {@code BaseAgent} instances (or Agentspan {@link Agent}s). */
    public static List<DeploymentInfo> deploy(Object... agents) {
        return deploy(coerceAgents(agents));
    }

    /** Drop-in: accepts native ADK {@code BaseAgent} instances (or Agentspan {@link Agent}s). */
    public static CompletableFuture<List<DeploymentInfo>> deployAsync(Object... agents) {
        return deployAsync(coerceAgents(agents));
    }

    /** Drop-in: accepts native ADK {@code BaseAgent} instances (or Agentspan {@link Agent}s). */
    public static void serve(Object... agents) {
        serve(coerceAgents(agents));
    }

    /** Drop-in: accepts a native ADK {@code BaseAgent} or any Agentspan {@link Agent}. */
    public static Map<String, Object> plan(Object agent) {
        return plan(coerceAgent(agent));
    }

    /** Drop-in: accepts a native ADK {@code BaseAgent} or any Agentspan {@link Agent}. */
    public static AgentHandle resume(String executionId, Object agent) {
        return resume(executionId, coerceAgent(agent));
    }

    /** Drop-in: accepts a native ADK {@code BaseAgent} or any Agentspan {@link Agent}. */
    public static CompletableFuture<AgentHandle> resumeAsync(String executionId, Object agent) {
        return resumeAsync(executionId, coerceAgent(agent));
    }

    // ── LangChain4j / LangGraph4j drop-in overloads ─────────────────────────
    //
    // Same shape as the ADK drop-in: the user writes idiomatic
    // LangChain4j (a ChatModel + @Tool POJOs) or LangGraph4j
    // (AgentExecutor.Builder) and hands the native object straight to
    // Agentspan.run / start / deploy / serve. No bridge call in user code.
    //
    // Why two flavours:
    //   - ChatModel + tools:           pure LangChain4j idiom; no LangGraph
    //                                  dep needed.
    //   - AgentExecutor.Builder:       LangGraph4j idiom; user passes the
    //                                  Builder along with the original tool
    //                                  POJOs (the Builder doesn't preserve
    //                                  references to them once toolsFromObject
    //                                  has run).
    //
    // Both delegate to LangChainBridge.agentBuilder under the hood. Users who
    // need a custom agent name, system prompt structure, or Agentspan-side
    // guardrails should call LangChainBridge.agentBuilder(...) directly.

    // 2-arg overloads exist so Java's overload resolution doesn't pick
    // the more-general run(Object, String) over the varargs version when
    // the user passes no tools. Without these, Agentspan.run(model, prompt)
    // would silently dispatch through coerceAgent and fail with
    // "Unsupported agent type: ChatModel".

    /** Drop-in: native LangChain4j {@code ChatModel}, no tools. */
    public static AgentResult run(dev.langchain4j.model.chat.ChatModel model, String prompt) {
        return run(langchainAgent(model, null), prompt);
    }

    /** Drop-in: native LangChain4j {@code ChatModel} + {@code @Tool} POJOs. */
    public static AgentResult run(dev.langchain4j.model.chat.ChatModel model, String prompt, Object... tools) {
        return run(langchainAgent(model, tools), prompt);
    }

    /** Drop-in: native LangChain4j {@code ChatModel}, no tools (async). */
    public static CompletableFuture<AgentResult> runAsync(dev.langchain4j.model.chat.ChatModel model, String prompt) {
        return runAsync(langchainAgent(model, null), prompt);
    }

    /** Drop-in: native LangChain4j {@code ChatModel} + {@code @Tool} POJOs (async). */
    public static CompletableFuture<AgentResult> runAsync(dev.langchain4j.model.chat.ChatModel model, String prompt, Object... tools) {
        return runAsync(langchainAgent(model, tools), prompt);
    }

    /** Drop-in: native LangChain4j {@code ChatModel}, no tools (start). */
    public static AgentHandle start(dev.langchain4j.model.chat.ChatModel model, String prompt) {
        return start(langchainAgent(model, null), prompt);
    }

    /** Drop-in: native LangChain4j {@code ChatModel} + {@code @Tool} POJOs (start). */
    public static AgentHandle start(dev.langchain4j.model.chat.ChatModel model, String prompt, Object... tools) {
        return start(langchainAgent(model, tools), prompt);
    }

    /** Drop-in: native LangChain4j {@code ChatModel}, no tools (stream). */
    public static AgentStream stream(dev.langchain4j.model.chat.ChatModel model, String prompt) {
        return stream(langchainAgent(model, null), prompt);
    }

    /** Drop-in: native LangChain4j {@code ChatModel} + {@code @Tool} POJOs (stream). */
    public static AgentStream stream(dev.langchain4j.model.chat.ChatModel model, String prompt, Object... tools) {
        return stream(langchainAgent(model, tools), prompt);
    }

    /** Drop-in deploy for a native LangChain4j configuration. */
    public static List<DeploymentInfo> deploy(dev.langchain4j.model.chat.ChatModel model, Object... tools) {
        return deploy(langchainAgent(model, tools));
    }

    /** Drop-in serve for a native LangChain4j configuration. */
    public static void serve(dev.langchain4j.model.chat.ChatModel model, Object... tools) {
        serve(langchainAgent(model, tools));
    }

    /** Drop-in: native LangGraph4j {@code AgentExecutor.Builder}, no tools. */
    public static AgentResult run(org.bsc.langgraph4j.agentexecutor.AgentExecutor.Builder builder, String prompt) {
        return run(langgraphAgent(builder, null), prompt);
    }

    /** Drop-in: native LangGraph4j {@code AgentExecutor.Builder} + tool POJOs. */
    public static AgentResult run(org.bsc.langgraph4j.agentexecutor.AgentExecutor.Builder builder, String prompt, Object... tools) {
        return run(langgraphAgent(builder, tools), prompt);
    }

    /** Drop-in: native LangGraph4j {@code AgentExecutor.Builder}, no tools (async). */
    public static CompletableFuture<AgentResult> runAsync(org.bsc.langgraph4j.agentexecutor.AgentExecutor.Builder builder, String prompt) {
        return runAsync(langgraphAgent(builder, null), prompt);
    }

    /** Drop-in: native LangGraph4j {@code AgentExecutor.Builder} + tool POJOs (async). */
    public static CompletableFuture<AgentResult> runAsync(org.bsc.langgraph4j.agentexecutor.AgentExecutor.Builder builder, String prompt, Object... tools) {
        return runAsync(langgraphAgent(builder, tools), prompt);
    }

    /** Drop-in: native LangGraph4j {@code AgentExecutor.Builder}, no tools (start). */
    public static AgentHandle start(org.bsc.langgraph4j.agentexecutor.AgentExecutor.Builder builder, String prompt) {
        return start(langgraphAgent(builder, null), prompt);
    }

    /** Drop-in: native LangGraph4j {@code AgentExecutor.Builder} + tool POJOs (start). */
    public static AgentHandle start(org.bsc.langgraph4j.agentexecutor.AgentExecutor.Builder builder, String prompt, Object... tools) {
        return start(langgraphAgent(builder, tools), prompt);
    }

    /** Drop-in: native LangGraph4j {@code AgentExecutor.Builder}, no tools (stream). */
    public static AgentStream stream(org.bsc.langgraph4j.agentexecutor.AgentExecutor.Builder builder, String prompt) {
        return stream(langgraphAgent(builder, null), prompt);
    }

    /** Drop-in: native LangGraph4j {@code AgentExecutor.Builder} + tool POJOs (stream). */
    public static AgentStream stream(org.bsc.langgraph4j.agentexecutor.AgentExecutor.Builder builder, String prompt, Object... tools) {
        return stream(langgraphAgent(builder, tools), prompt);
    }

    /** Drop-in deploy for a native LangGraph4j configuration. */
    public static List<DeploymentInfo> deploy(org.bsc.langgraph4j.agentexecutor.AgentExecutor.Builder builder, Object... tools) {
        return deploy(langgraphAgent(builder, tools));
    }

    /** Drop-in serve for a native LangGraph4j configuration. */
    public static void serve(org.bsc.langgraph4j.agentexecutor.AgentExecutor.Builder builder, Object... tools) {
        serve(langgraphAgent(builder, tools));
    }

    private static Agent langchainAgent(dev.langchain4j.model.chat.ChatModel model, Object[] tools) {
        return ai.agentspan.frameworks.LangChainBridge
                .agentBuilder("langchain_agent", model, null, tools == null ? new Object[0] : tools)
                .build();
    }

    private static Agent langgraphAgent(org.bsc.langgraph4j.agentexecutor.AgentExecutor.Builder builder, Object[] tools) {
        // The LangGraph4j AgentExecutor.Builder carries the ChatModel and the
        // (optional) SystemMessage in package-private fields. We use reflection
        // to recover them — failure here means a future ADK build changed the
        // shape; we throw a clear message rather than silently degrading.
        dev.langchain4j.model.chat.ChatModel model = readBuilderField(
                builder, "chatModel", dev.langchain4j.model.chat.ChatModel.class);
        if (model == null) {
            throw new IllegalArgumentException(
                    "Agentspan.run(AgentExecutor.Builder, ...): the Builder has no chatModel set. "
                    + "Call .chatModel(...) before handing the Builder to Agentspan.");
        }
        String systemText = readSystemMessageText(builder);

        // Validate the Builder produces a compilable LangGraph4j StateGraph
        // before shipping the config — same safety check the old bridge did.
        try {
            builder.build();
        } catch (Exception e) {
            throw new RuntimeException(
                    "AgentExecutor.Builder is not a valid LangGraph4j configuration: "
                    + e.getMessage(), e);
        }
        return ai.agentspan.frameworks.LangChainBridge
                .agentBuilder("langgraph_agent", model, systemText, tools == null ? new Object[0] : tools)
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
            throw new RuntimeException("AgentExecutor.Builder field '" + fieldName
                    + "' is no longer accessible — likely a LangGraph4j upgrade. "
                    + "Open an issue.", t);
        }
    }

    private static String readSystemMessageText(Object builder) {
        try {
            java.lang.reflect.Field f = builder.getClass().getDeclaredField("systemMessage");
            f.setAccessible(true);
            Object sys = f.get(builder);
            if (sys == null) return null;
            // dev.langchain4j.data.message.SystemMessage has a public text() method
            java.lang.reflect.Method m = sys.getClass().getMethod("text");
            Object t = m.invoke(sys);
            return t instanceof String s && !s.isEmpty() ? s : null;
        } catch (Throwable t) {
            return null;
        }
    }

    /**
     * Internal: coerce a user-provided agent object to an Agentspan {@link Agent}.
     *
     * <p>Supports:
     * <ul>
     *   <li>{@link Agent} — returned as-is</li>
     *   <li>{@code com.google.adk.agents.BaseAgent} — translated via
     *       {@link ai.agentspan.frameworks.AdkBridge} (ADK must be on the
     *       runtime classpath when this branch executes)</li>
     * </ul>
     */
    private static Agent coerceAgent(Object agent) {
        if (agent == null) {
            throw new IllegalArgumentException("agent is null");
        }
        if (agent instanceof Agent a) {
            return a;
        }
        if (isInstanceOf(agent, "com.google.adk.agents.BaseAgent")) {
            // ADK is on the classpath (we just resolved BaseAgent), so loading
            // AdkBridge here is safe — its direct ADK references will link.
            return ai.agentspan.frameworks.AdkBridge.toAgentspan(
                    (com.google.adk.agents.BaseAgent) agent);
        }
        throw new IllegalArgumentException(
                "Unsupported agent type: " + agent.getClass().getName()
                + ". Expected ai.agentspan.Agent or a native ADK BaseAgent.");
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
     * Walk the entire type hierarchy (superclasses, interfaces, and
     * superinterfaces of both) looking for a type whose FQN matches.
     *
     * <p>Used instead of {@code instanceof} so the dispatcher compiles and
     * runs without ADK on the classpath — only callers actually passing
     * native ADK objects trigger the JVM to load ADK classes. The recursive
     * walk also handles interface-typed frameworks (where the target is an
     * interface inherited via a superclass) — important for future bridge
     * targets even though ADK's {@code BaseAgent} is itself a class today.
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
