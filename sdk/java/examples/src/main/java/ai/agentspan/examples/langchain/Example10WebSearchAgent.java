// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.langchain;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import dev.langchain4j.model.chat.ChatModel;
import dev.langchain4j.model.openai.OpenAiChatModel;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Example Lc4j 10 — Web Search Agent (native LangChain4j SDK)
 *
 * <p>Java port of <code>sdk/python/examples/langchain/10_web_search_agent.py</code>.
 *
 * <p>Demonstrates: simulated search-and-retrieval research workflow using
 * three LangChain4j tools backed by canned data identical to the Python sample.
 */
public class Example10WebSearchAgent {

    static class WebSearchTools {

        @dev.langchain4j.agent.tool.Tool(
            name = "web_search",
            value = "Search the web and return top 3 result summaries. "
                  + "Args: query: The search query string."
        )
        public String webSearch(@dev.langchain4j.agent.tool.P("query") String query) {
            Map<String, List<String>> results = new LinkedHashMap<>();
            results.put("python history", List.of(
                "Python was created by Guido van Rossum in 1989 and first released in 1991.",
                "Python 2.0 introduced list comprehensions and garbage collection (2000).",
                "Python 3.0, a major breaking change, was released in December 2008."
            ));
            results.put("machine learning", List.of(
                "Machine learning is a branch of AI that enables systems to learn from data.",
                "Supervised learning uses labeled data; unsupervised learning finds hidden patterns.",
                "Deep learning uses neural networks with many layers for complex pattern recognition."
            ));
            results.put("climate change", List.of(
                "Global average temperature has risen ~1.1°C above pre-industrial levels.",
                "CO2 levels reached 421 ppm in 2023, the highest in 3.6 million years.",
                "The Paris Agreement aims to limit warming to 1.5°C by reducing emissions."
            ));

            String q = query.toLowerCase();
            for (Map.Entry<String, List<String>> entry : results.entrySet()) {
                if (q.contains(entry.getKey())) {
                    StringBuilder sb = new StringBuilder();
                    List<String> items = entry.getValue();
                    for (int i = 0; i < items.size(); i++) {
                        if (i > 0) sb.append("\n");
                        sb.append(i + 1).append(". ").append(items.get(i));
                    }
                    return sb.toString();
                }
            }
            return "Search results for '" + query + "': No cached results. (Demo mode — add more entries to results dict.)";
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "get_page_content",
            value = "Retrieve the main content of a web page by URL. "
                  + "Args: url: The page URL to retrieve content from."
        )
        public String getPageContent(@dev.langchain4j.agent.tool.P("url") String url) {
            Map<String, String> pages = new LinkedHashMap<>();
            pages.put("python.org",
                "Python is a versatile, high-level programming language emphasizing readability. "
                + "Used in web development, data science, AI, automation, and more.");
            pages.put("wikipedia.org/ml",
                "Machine learning (ML) is a field of AI research dedicated to developing systems "
                + "that learn from data. Key techniques include regression, classification, "
                + "clustering, and neural networks.");

            String lower = url.toLowerCase();
            for (Map.Entry<String, String> entry : pages.entrySet()) {
                if (lower.contains(entry.getKey())) {
                    return entry.getValue();
                }
            }
            return "Content from " + url + ": (Demo mode — page content not cached.)";
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "summarize_results",
            value = "Summarize a block of text into 2-3 key bullet points. "
                  + "Args: text: The text to summarize."
        )
        public String summarizeResults(@dev.langchain4j.agent.tool.P("text") String text) {
            String[] raw = text.split("\\.");
            java.util.List<String> sentences = new java.util.ArrayList<>();
            for (String s : raw) {
                String t = s.trim();
                if (t.length() > 20) sentences.add(t);
            }
            int limit = Math.min(3, sentences.size());
            if (limit == 0) return "No content to summarize.";
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < limit; i++) {
                if (i > 0) sb.append("\n");
                sb.append("• ").append(sentences.get(i)).append(".");
            }
            return sb.toString();
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
            "You are a research assistant. Use search and retrieval tools to answer questions thoroughly.\n\n"
                + "Research the history of Python programming language and give me a brief summary.",
            new WebSearchTools()
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
