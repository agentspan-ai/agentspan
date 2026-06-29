// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.examples.langchain;

import org.conductoross.conductor.ai.AgentRuntime;
import org.conductoross.conductor.ai.model.AgentResult;

import dev.langchain4j.model.chat.ChatModel;
import dev.langchain4j.model.openai.OpenAiChatModel;

/**
 * Example LangChain 01 — Hello World using the native LangChain4j SDK.
 *
 * <p>Builds a real {@code dev.langchain4j.model.openai.OpenAiChatModel}
 * (the canonical LangChain4j chat-model class) and hands it directly to
 * {@link Agentspan#run(ChatModel, String)} via the drop-in overload so the
 * agent runs on the durable Agentspan runtime.
 *
 * <p>Requirements:
 * <ul>
 *   <li>{@code AGENTSPAN_SERVER_URL=http://localhost:6767/api}</li>
 *   <li>Agentspan server with OpenAI credentials configured server-side.</li>
 * </ul>
 */
public class Example01HelloWorld {

    public static void main(String[] args) {
        AgentRuntime runtime = new AgentRuntime();
        // apiKey is required by LangChain4j's builder but unused — Agentspan
        // runs the LLM call on the server with server-registered credentials.
        ChatModel model = OpenAiChatModel.builder()
                .apiKey("agentspan-server-handles-credentials")
                .modelName("gpt-4o-mini")
                .build();

        AgentResult result = runtime.run(
                model,
                "Say hello and tell me a fun fact about Python programming."
        );
        result.printResult();

        runtime.shutdown();
    }
}
