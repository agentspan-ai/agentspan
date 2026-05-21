// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.openai;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.annotations.Tool;
import ai.agentspan.frameworks.OpenAIAgent;
import ai.agentspan.model.AgentResult;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Example OpenAi 07 — Streaming
 *
 * <p>Java port of <code>sdk/python/examples/openai/07_streaming.py</code>.
 *
 * <p>Demonstrates: an OpenAI Agents SDK support agent backed by a single
 * knowledge-base tool. The Python original is named "streaming" because it
 * is meant to be invoked via {@code runtime.stream(...)}, but its actual
 * call site uses {@code runtime.run(...)}; we mirror the run path here.
 *
 * <p>Requirements:
 * <ul>
 *   <li>AGENTSPAN_SERVER_URL=http://localhost:6767/api</li>
 *   <li>AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini</li>
 * </ul>
 */
public class Example07Streaming {

    static class KnowledgeBaseTools {

        @Tool(name = "search_knowledge_base", description = "Search the knowledge base for relevant information.")
        public String searchKnowledgeBase(String query) {
            Map<String, String> knowledge = new LinkedHashMap<>();
            knowledge.put("return policy",
                    "Returns accepted within 30 days with receipt. "
                            + "Electronics have a 15-day return window.");
            knowledge.put("shipping",
                    "Free shipping on orders over $50. "
                            + "Standard delivery: 3-5 business days.");
            knowledge.put("warranty",
                    "All products come with a 1-year manufacturer warranty. "
                            + "Extended warranty available for electronics.");

            String queryLower = query.toLowerCase();
            for (Map.Entry<String, String> entry : knowledge.entrySet()) {
                if (queryLower.contains(entry.getKey())) {
                    return entry.getValue();
                }
            }
            return "No relevant information found for your query.";
        }
    }

    public static void main(String[] args) {
        Agent agent = OpenAIAgent.builder()
                .name("support_agent")
                .instructions(
                        "You are a customer support agent. Use the knowledge base to answer "
                                + "questions accurately. If you can't find the answer, say so honestly.")
                .model(Settings.LLM_MODEL)
                .tools(new KnowledgeBaseTools())
                .build();

        AgentResult result = Agentspan.run(agent, "What's your return policy for electronics?");
        result.printResult();

        Agentspan.shutdown();
    }
}
