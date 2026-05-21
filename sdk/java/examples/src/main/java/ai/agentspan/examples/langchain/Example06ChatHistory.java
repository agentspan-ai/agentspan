// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.langchain;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;
import ai.agentspan.frameworks.LangChainBridge;

import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.Tool;
import dev.langchain4j.model.chat.ChatModel;
import dev.langchain4j.model.openai.OpenAiChatModel;

import java.util.Locale;
import java.util.Map;

/**
 * Example Lc4j 06 — Chat History (native LangChain4j SDK)
 *
 * <p>Java port of <code>sdk/python/examples/langchain/06_chat_history.py</code>.
 * The Python version uses LangChain's <code>create_agent</code>, which natively
 * carries chat history between turns when re-invoked. The example itself only
 * runs one turn, but the underlying agent is conversational.
 *
 * <p><b>LangChain4j adaptation:</b> with the server-side LLM loop, there is
 * no client-side {@code MessageWindowChatMemory} that survives across
 * {@link Agentspan#run} invocations. The closest semantically-equivalent
 * shape is to mark the agent as {@code stateful(true)} so that the server
 * persists conversation history across runs in a dedicated worker domain —
 * multi-turn calls against the same stateful agent will see prior exchanges.
 * The single-turn driver below mirrors the Python source exactly; toggling
 * stateful demonstrates how the Java SDK surfaces persistent context. Because
 * {@code stateful(true)} is an Agentspan-side flag rather than a LangChain4j
 * one, we use the advanced {@link LangChainBridge#agentBuilder} path so we
 * can decorate the agent before {@code .build()}.
 *
 * <p>Demonstrates:
 * <ul>
 *   <li>Defining a fact-lookup {@link Tool @Tool}</li>
 *   <li>Marking the agent {@code stateful(true)} for cross-turn persistence</li>
 *   <li>Running a single-turn query while keeping the agent conversational</li>
 * </ul>
 *
 * <p>Requirements:
 * <ul>
 *   <li>{@code AGENTSPAN_SERVER_URL=http://localhost:6767/api}</li>
 *   <li>Agentspan server with OpenAI credentials configured server-side.</li>
 * </ul>
 */
public class Example06ChatHistory {

    static class FactTools {

        private static final Map<String, String> FACTS = Map.of(
            "solar system", "The Solar System has 8 planets. Neptune is the farthest from the Sun.",
            "python",       "Python was created by Guido van Rossum and first released in 1991.",
            "mars",         "Mars is the fourth planet from the Sun and has two moons: Phobos and Deimos.",
            "earth",        "Earth is the third planet from the Sun and the only known planet to harbor life."
        );

        @Tool(
            name = "recall_fact",
            value = "Retrieve a stored fact about the given topic. "
                  + "Args: topic — the topic to look up (e.g., 'solar system', 'python')."
        )
        public String recallFact(@P("topic") String topic) {
            String key = topic == null ? "" : topic.toLowerCase(Locale.ROOT);
            return FACTS.getOrDefault(key, "No facts stored for '" + topic + "'.");
        }
    }

    public static void main(String[] args) {
        // apiKey is required by LangChain4j's builder but unused — Agentspan
        // runs the LLM call on the server with server-registered credentials.
        ChatModel model = OpenAiChatModel.builder()
            .apiKey("agentspan-server-handles-credentials")
            .modelName("gpt-4o-mini")
            .build();

        // Use the advanced LangChainBridge.agentBuilder(...) path so we can
        // mark the agent stateful(true) — server-side cross-run conversation
        // persistence is an Agentspan feature on top of LangChain4j.
        Agent agent = LangChainBridge.agentBuilder(
            "chat_history_agent",
            model,
            "You are a helpful science assistant. Use tools to look up facts when needed.",
            new FactTools())
            .stateful(true)
            .build();

        AgentResult result = Agentspan.run(
            agent,
            "Which planet in the solar system is farthest from the Sun?"
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
