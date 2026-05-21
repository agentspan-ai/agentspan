// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.langgraph;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.Tool;
import dev.langchain4j.model.chat.ChatModel;
import dev.langchain4j.model.openai.OpenAiChatModel;

import org.bsc.langgraph4j.agentexecutor.AgentExecutor;

import java.util.HashMap;
import java.util.Map;

/**
 * Example LangGraph 05 — Tool node (multiple tools dispatched through the ReAct loop).
 *
 * <p>Mirrors <code>sdk/python/examples/langgraph/05_tool_node.py</code> which
 * manually wires {@code agent -> tools_condition -> tool_node -> agent}.
 * LangGraph4j's prebuilt {@code AgentExecutor} provides this exact loop out
 * of the box — the example author just supplies the tools and the LLM drives
 * selection.
 *
 * <p>Demonstrates:
 * <ul>
 *   <li>Two related but distinct tools (capital + population)</li>
 *   <li>The LLM choosing each tool independently per question</li>
 *   <li>Iterative ReAct loop dispatching multiple tool calls in one run</li>
 * </ul>
 */
public class Example05ToolNode {

    static class GeoTools {
        private static final Map<String, String> CAPITALS = new HashMap<>();
        private static final Map<String, String> POPULATIONS = new HashMap<>();
        static {
            CAPITALS.put("france", "Paris");
            CAPITALS.put("germany", "Berlin");
            CAPITALS.put("japan", "Tokyo");
            CAPITALS.put("brazil", "Brasilia");
            CAPITALS.put("india", "New Delhi");
            CAPITALS.put("usa", "Washington D.C.");

            POPULATIONS.put("france", "68 million");
            POPULATIONS.put("germany", "84 million");
            POPULATIONS.put("japan", "125 million");
            POPULATIONS.put("brazil", "215 million");
            POPULATIONS.put("india", "1.4 billion");
            POPULATIONS.put("usa", "335 million");
        }

        @Tool("Look up the capital city of a country.")
        public String lookupCapital(@P("country") String country) {
            String key = country == null ? "" : country.toLowerCase().trim();
            return CAPITALS.getOrDefault(key, "Capital of " + country + " is not in my database.");
        }

        @Tool("Return the approximate population of a country.")
        public String lookupPopulation(@P("country") String country) {
            String key = country == null ? "" : country.toLowerCase().trim();
            return POPULATIONS.getOrDefault(key, "Population data for " + country + " is not available.");
        }
    }

    public static void main(String[] args) {
        // apiKey is required by LangChain4j's builder but unused — Agentspan
        // runs the LLM call on the server with server-registered credentials.
        ChatModel model = OpenAiChatModel.builder()
                .apiKey("agentspan-server-handles-credentials")
                .modelName("gpt-4o-mini")
                .build();

        GeoTools tools = new GeoTools();
        AgentExecutor.Builder agent = AgentExecutor.builder().chatModel(model);
        agent.toolsFromObject(tools);

        // Drop-in overload — fold the system prompt into the user message.
        AgentResult result = Agentspan.run(
                agent,
                "You are a helpful geography assistant. Use the available tools to look up facts.\n\n"
                + "What is the capital and population of Japan and Brazil?",
                tools
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
