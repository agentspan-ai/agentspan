// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.langgraph;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import dev.langchain4j.model.chat.ChatModel;
import dev.langchain4j.model.openai.OpenAiChatModel;

import org.bsc.langgraph4j.agentexecutor.AgentExecutor;

/**
 * Example LangGraph 07 — System prompt (persona) demonstration.
 *
 * <p>Mirrors <code>sdk/python/examples/langgraph/07_system_prompt.py</code>
 * which passes a {@code system_prompt=...} to {@code create_agent}. The
 * drop-in {@link Agentspan#run} overload takes a single user prompt — fold
 * the persona into that prompt as a leading section so it steers every reply.
 *
 * <p>Demonstrates:
 * <ul>
 *   <li>Detailed persona/system prompt steering tone and behavior</li>
 *   <li>No tools — the agent answers from the LLM directly</li>
 *   <li>How the persona section shapes every reply</li>
 * </ul>
 */
public class Example07SystemPrompt {

    private static final String TUTOR_SYSTEM_PROMPT = String.join("\n",
            "You are Socrates, an ancient Greek philosopher and skilled tutor.",
            "",
            "Your teaching style:",
            "- Never give direct answers; instead guide students through questions",
            "- Use the Socratic method: ask probing questions that lead to insight",
            "- When a student is close to an answer, acknowledge their progress",
            "- Celebrate intellectual curiosity",
            "- Use analogies from everyday ancient Greek life when helpful",
            "- Speak with wisdom and calm, occasionally referencing your own experiences",
            "",
            "Remember: your goal is to help the student discover the answer themselves,",
            "not to provide it for them."
    );

    public static void main(String[] args) {
        // apiKey is required by LangChain4j's builder but unused — Agentspan
        // runs the LLM call on the server with server-registered credentials.
        ChatModel model = OpenAiChatModel.builder()
                .apiKey("agentspan-server-handles-credentials")
                .modelName("gpt-4o-mini")
                .build();

        AgentExecutor.Builder agent = AgentExecutor.builder().chatModel(model);

        // Drop-in overload — fold the persona into the user message.
        AgentResult result = Agentspan.run(
                agent,
                TUTOR_SYSTEM_PROMPT
                + "\n\nI want to understand why 1 + 1 = 2. Can you just tell me?"
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
