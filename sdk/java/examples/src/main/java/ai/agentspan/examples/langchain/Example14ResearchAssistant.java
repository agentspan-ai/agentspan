// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.langchain;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import dev.langchain4j.model.chat.ChatModel;
import dev.langchain4j.model.openai.OpenAiChatModel;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Example Lc4j 14 — Research Assistant (native LangChain4j SDK)
 *
 * <p>Java port of <code>sdk/python/examples/langchain/14_research_assistant.py</code>.
 *
 * <p>Demonstrates: cross-source research using three canned-knowledge tools
 * (academic papers, news, statistics) with citation tracking guidance in the
 * system prompt.
 */
public class Example14ResearchAssistant {

    static class ResearchTools {

        @dev.langchain4j.agent.tool.Tool(
            name = "search_academic",
            value = "Search academic papers and return relevant findings. "
                  + "Args: query: The research query or topic."
        )
        public String searchAcademic(@dev.langchain4j.agent.tool.P("query") String query) {
            Map<String, String> papers = new LinkedHashMap<>();
            papers.put("transformer",
                "Vaswani et al. (2017) 'Attention Is All You Need' introduced the Transformer architecture, "
                + "enabling modern LLMs. [arxiv:1706.03762]");
            papers.put("reinforcement learning",
                "Sutton & Barto (2018) 'Reinforcement Learning: An Introduction' is the foundational textbook. "
                + "Key concept: reward maximization via trial and error.");
            papers.put("neural network",
                "LeCun et al. (2015) 'Deep Learning' in Nature surveys convolutional and recurrent networks. "
                + "[DOI: 10.1038/nature14539]");
            papers.put("climate",
                "IPCC AR6 (2021) confirms 1.5°C warming is likely by 2040 without significant emissions reductions. "
                + "[ipcc.ch/report/ar6]");

            String q = query == null ? "" : query.toLowerCase();
            for (Map.Entry<String, String> e : papers.entrySet()) {
                if (q.contains(e.getKey())) return e.getValue();
            }
            return "No academic papers indexed for '" + query + "'. Recommend searching Google Scholar or arXiv.";
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "search_news",
            value = "Search recent news articles about a topic. "
                  + "Args: topic: The topic to search news for."
        )
        public String searchNews(@dev.langchain4j.agent.tool.P("topic") String topic) {
            Map<String, String> news = new LinkedHashMap<>();
            news.put("ai",
                "Recent: GPT-5 and Claude 4 compete on reasoning benchmarks (2025). "
                + "AI regulation bills passed in EU and California.");
            news.put("climate",
                "Recent: Record ocean temperatures in 2024. COP30 negotiations ongoing in Brazil.");
            news.put("quantum",
                "Recent: Google claims 'quantum supremacy' milestone with 1000-qubit processor (2025).");
            news.put("space",
                "Recent: SpaceX Starship completes first orbital mission. NASA Artemis III moon landing planned for 2026.");

            String t = topic == null ? "" : topic.toLowerCase();
            for (Map.Entry<String, String> e : news.entrySet()) {
                if (t.contains(e.getKey())) return e.getValue();
            }
            return "No recent news indexed for '" + topic + "'.";
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "get_statistics",
            value = "Retrieve key statistics and figures for a research domain. "
                  + "Args: domain: The domain to get statistics for (e.g., 'ai market', 'renewable energy')."
        )
        public String getStatistics(@dev.langchain4j.agent.tool.P("domain") String domain) {
            Map<String, String> stats = new LinkedHashMap<>();
            stats.put("ai market",
                "Global AI market size: $196B (2024), projected $1.8T by 2030. "
                + "CAGR: ~37%. Top players: Microsoft, Google, AWS.");
            stats.put("renewable energy",
                "Renewables supplied 30% of global electricity in 2023. "
                + "Solar capacity grew 45% YoY. Wind energy: 2,200 GW installed.");
            stats.put("global population",
                "World population: 8.1B (2024). Projected 9.7B by 2050. Fastest growth: Sub-Saharan Africa.");
            stats.put("internet",
                "Internet users: 5.4B (67% of world). Mobile internet: 92% of usage. "
                + "Data created daily: 2.5 quintillion bytes.");

            String d = domain == null ? "" : domain.toLowerCase();
            for (Map.Entry<String, String> e : stats.entrySet()) {
                if (d.contains(e.getKey())) return e.getValue();
            }
            return "No statistics indexed for '" + domain + "'.";
        }
    }

    public static void main(String[] args) {
        // apiKey is required by LangChain4j's builder but unused — Agentspan
        // runs the LLM call on the server with server-registered credentials.
        ChatModel model = OpenAiChatModel.builder()
            .apiKey("agentspan-server-handles-credentials")
            .modelName("gpt-4o-mini")
            .build();

        // Drop-in overload — fold the system prompt into the user message.
        AgentResult result = Agentspan.run(
            model,
            "You are a thorough research assistant. When answering questions, "
            + "search academic sources, recent news, and statistics to provide well-rounded answers. "
            + "Always cite your sources.\n\n"
            + "Research the current state of AI: what does academic literature say, "
            + "what are recent news developments, and what are the market statistics?",
            new ResearchTools()
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
