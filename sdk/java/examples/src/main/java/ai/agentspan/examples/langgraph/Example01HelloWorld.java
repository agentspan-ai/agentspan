// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.langgraph;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;
import ai.agentspan.frameworks.LangGraphBridge;

import dev.langchain4j.model.chat.ChatModel;
import dev.langchain4j.model.openai.OpenAiChatModel;

/**
 * Example LangGraph 01 — Hello World using the native LangGraph4j SDK.
 *
 * <p>Builds a real LangGraph4j {@code AgentExecutor} (a {@code StateGraph}
 * implementing the ReAct pattern) via
 * {@code org.bsc.langgraph4j.agentexecutor.AgentExecutor.builder()} and hands
 * the configuration to {@link LangGraphBridge#toAgentspan} so it runs on
 * the durable Agentspan runtime.
 */
public class Example01HelloWorld {

    public static void main(String[] args) {
        ChatModel model = OpenAiChatModel.builder()
                .apiKey(System.getenv().getOrDefault("OPENAI_API_KEY", "unused"))
                .modelName("gpt-4o-mini")
                .build();

        Agent agent = LangGraphBridge.toAgentspan(
                "hello_world_agent",
                model,
                null
        );

        AgentResult result = Agentspan.run(
                agent,
                "Say hello and tell me a fun fact about state machines."
        );
        result.printResult();

        Agentspan.shutdown();
    }
}
