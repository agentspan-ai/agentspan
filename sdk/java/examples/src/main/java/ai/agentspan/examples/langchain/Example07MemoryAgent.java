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
 * Example Lc4j 07 — Memory Agent (native LangChain4j SDK)
 *
 * <p>Java port of <code>sdk/python/examples/langchain/07_memory_agent.py</code>.
 * The Python version uses LangChain's <code>create_agent</code> with native
 * conversational context — the agent recalls information from earlier turns.
 *
 * <p><b>LangChain4j adaptation:</b> with the server-side LLM loop, there is
 * no client-side {@code MessageWindowChatMemory} that survives across
 * {@link Agentspan#run} calls. The closest semantically-equivalent shape is
 * to mark the agent as {@code stateful(true)} so that the server persists
 * conversation history across runs in a dedicated worker domain. Subsequent
 * runs against the same stateful agent then see prior exchanges. The
 * single-turn driver below mirrors the Python source. Because
 * {@code stateful(true)} is an Agentspan-side flag, we use the advanced
 * {@link LangChainBridge#agentBuilder} path so we can decorate the agent
 * before {@code .build()}.
 *
 * <p>Demonstrates:
 * <ul>
 *   <li>HR assistant with a user-profile lookup tool</li>
 *   <li>Marking the agent {@code stateful(true)} for cross-turn memory</li>
 *   <li>Running an HR-style query end-to-end</li>
 * </ul>
 *
 * <p>Requirements:
 * <ul>
 *   <li>{@code AGENTSPAN_SERVER_URL=http://localhost:6767/api}</li>
 *   <li>Agentspan server with OpenAI credentials configured server-side.</li>
 * </ul>
 */
public class Example07MemoryAgent {

    static class HrTools {

        private static final Map<String, String> PROFILES = Map.of(
            "alice", "Alice Chen, Software Engineer, 5 years experience, Python/Go specialist.",
            "bob",   "Bob Martinez, Data Scientist, PhD in Statistics, R/Python expert.",
            "carol", "Carol Williams, Product Manager, 8 years in B2B SaaS."
        );

        @Tool(
            name = "get_user_profile",
            value = "Fetch the profile for a given username. "
                  + "Args: username — the user's login name."
        )
        public String getUserProfile(@P("username") String username) {
            String key = username == null ? "" : username.toLowerCase(Locale.ROOT);
            return PROFILES.getOrDefault(key, "No profile found for '" + username + "'.");
        }
    }

    public static void main(String[] args) {
        String instructions =
            "You are a helpful HR assistant. Remember information from earlier in the conversation.";

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
            "memory_agent",
            model,
            instructions,
            new HrTools())
            .stateful(true)
            .build();

        AgentResult result = Agentspan.run(
            agent,
            "Look up the profile for alice and tell me about her skills."
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
