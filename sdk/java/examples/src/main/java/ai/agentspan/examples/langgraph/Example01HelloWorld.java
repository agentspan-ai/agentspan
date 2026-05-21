// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.langgraph;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import dev.langchain4j.model.chat.ChatModel;
import dev.langchain4j.model.openai.OpenAiChatModel;

import org.bsc.langgraph4j.agentexecutor.AgentExecutor;

/**
 * Example LangGraph 01 — Hello World using the native LangGraph4j SDK.
 *
 * <p>Builds a real LangGraph4j {@code AgentExecutor.Builder} (the same builder
 * the LangGraph4j docs use for the prebuilt ReAct agent) and hands it directly
 * to {@link Agentspan#run(AgentExecutor.Builder, String, Object...)} via the
 * drop-in overload so it runs on the durable Agentspan runtime.
 */
public class Example01HelloWorld {

    public static void main(String[] args) {
        // apiKey is required by LangChain4j's builder but unused — Agentspan
        // runs the LLM call on the server with server-registered credentials.
        ChatModel model = OpenAiChatModel.builder()
                .apiKey("agentspan-server-handles-credentials")
                .modelName("gpt-4o-mini")
                .build();

        AgentExecutor.Builder agent = AgentExecutor.builder().chatModel(model);

        AgentResult result = Agentspan.run(
                agent,
                "Say hello and tell me a fun fact about state machines."
        );
        result.printResult();

        Agentspan.shutdown();
    }
}
