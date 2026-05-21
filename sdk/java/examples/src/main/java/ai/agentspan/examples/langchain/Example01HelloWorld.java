// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.langchain;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

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
 *   <li>{@code OPENAI_API_KEY} set (only the model identifier matters; the
 *       server makes the actual LLM call using its own credentials)</li>
 * </ul>
 */
public class Example01HelloWorld {

    public static void main(String[] args) {
        ChatModel model = OpenAiChatModel.builder()
                .apiKey(System.getenv().getOrDefault("OPENAI_API_KEY", "unused"))
                .modelName("gpt-4o-mini")
                .build();

        AgentResult result = Agentspan.run(
                model,
                "Say hello and tell me a fun fact about Python programming."
        );
        result.printResult();

        Agentspan.shutdown();
    }
}
