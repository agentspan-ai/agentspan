// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.frameworks;

import ai.agentspan.Agent;

import dev.langchain4j.model.chat.ChatModel;

import org.bsc.langgraph4j.CompiledGraph;
import org.bsc.langgraph4j.StateGraph;
import org.bsc.langgraph4j.agentexecutor.AgentExecutor;

/**
 * Adapter that takes a native LangGraph4j {@link AgentExecutor} configuration and
 * produces an Agentspan {@link Agent} ready for {@code Agentspan.run(...)}.
 *
 * <p>LangGraph4j builds ReAct-style agents as {@code StateGraph<AgentExecutor.State>}.
 * For Agentspan execution, we extract the {@link ChatModel} + {@code @Tool} POJOs
 * (the same inputs the LangGraph4j {@code AgentExecutor.Builder} accepts) and let
 * the durable Agentspan runtime drive the ReAct loop server-side.
 *
 * <p>The compiled local graph remains available — callers can choose to run
 * the graph in-process via {@link CompiledGraph#stream}, or hand it off to
 * Agentspan; the example author writes idiomatic LangGraph4j code either way.
 */
public final class LangGraphBridge {

    private LangGraphBridge() {}

    /**
     * Build a LangGraph4j {@link AgentExecutor} StateGraph from the given
     * {@link ChatModel} and {@code @Tool} POJOs, then produce an Agentspan
     * {@link Agent}. This mirrors {@code AgentExecutor.builder().chatModel(...)
     * .toolsFromObject(...).build()}.
     */
    public static Agent toAgentspan(String name, ChatModel model, String systemPrompt, Object... tools) {
        return agentBuilder(name, model, systemPrompt, tools).build();
    }

    /** Same as {@link #toAgentspan(String, ChatModel, String, Object...)} with no tools. */
    public static Agent toAgentspan(String name, ChatModel model, String systemPrompt) {
        return agentBuilder(name, model, systemPrompt).build();
    }

    /**
     * Same as {@link #toAgentspan} but returns the populated
     * {@link Agent.Builder} so callers can attach Agentspan-only features
     * (guardrails, gate, termination, callbacks) before {@code .build()}:
     *
     * <pre>{@code
     * Agent agent = LangGraphBridge.agentBuilder("name", model, "prompt", new MyTools())
     *     .guardrails(piiGuard)
     *     .build();
     * Agentspan.run(agent, "...");
     * }</pre>
     */
    public static Agent.Builder agentBuilder(String name, ChatModel model, String systemPrompt, Object... tools) {
        // Build the native LangGraph4j StateGraph to validate the configuration
        // would compile under LangGraph4j. We don't run the local graph —
        // Agentspan does — but constructing it proves the user's tools/model
        // are valid for LangGraph4j's expectations (tool specs extractable,
        // model is a ChatModel).
        AgentExecutor.Builder builder = AgentExecutor.builder().chatModel(model);
        if (tools != null) {
            for (Object t : tools) {
                if (t != null) builder.toolsFromObject(t);
            }
        }
        try {
            builder.build(); // throws GraphStateException if mis-wired
        } catch (Exception e) {
            throw new RuntimeException("LangGraph4j AgentExecutor configuration is invalid: "
                    + e.getMessage(), e);
        }
        return LangChainBridge.agentBuilder(name, model, systemPrompt, tools);
    }
}
