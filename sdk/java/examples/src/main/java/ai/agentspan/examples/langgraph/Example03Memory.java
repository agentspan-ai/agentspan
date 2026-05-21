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
 * Example LangGraph 03 — Multi-turn conversation (memory-style).
 *
 * <p>Inspired by <code>sdk/python/examples/langgraph/03_memory.py</code> which
 * attaches a {@code MemorySaver} checkpointer to {@code create_agent}. In this
 * Java/Agentspan port we demonstrate the same surface — a single agent invoked
 * three times in sequence — but without an in-process checkpointer. The history
 * is passed back to the LLM directly inside the prompt for each turn, which is
 * the simplest portable pattern when running on the durable Agentspan runtime.
 *
 * <p>Demonstrates:
 * <ul>
 *   <li>Reusing a single {@link LangGraphBridge}-built agent for multiple turns</li>
 *   <li>Pure prompt-based history (no in-memory checkpointer required)</li>
 *   <li>How an LLM can recall facts when given prior context</li>
 * </ul>
 */
public class Example03Memory {

    public static void main(String[] args) {
        ChatModel model = OpenAiChatModel.builder()
                .apiKey(System.getenv().getOrDefault("OPENAI_API_KEY", "unused"))
                .modelName("gpt-4o-mini")
                .build();

        Agent agent = LangGraphBridge.toAgentspan(
                "memory_agent",
                model,
                "You are a friendly assistant. Pay close attention to facts the user shares."
        );

        System.out.println("=== Turn 1: Introduce a name ===");
        AgentResult turn1 = Agentspan.run(
                agent,
                "My name is Alice. Please remember that."
        );
        turn1.printResult();

        System.out.println("\n=== Turn 2: Ask the agent to recall ===");
        AgentResult turn2 = Agentspan.run(
                agent,
                "Earlier I told you my name was Alice. What is my name?"
        );
        turn2.printResult();

        System.out.println("\n=== Turn 3: Continue the conversation ===");
        AgentResult turn3 = Agentspan.run(
                agent,
                "Tell me one fun fact about the name Alice."
        );
        turn3.printResult();

        Agentspan.shutdown();
    }
}
