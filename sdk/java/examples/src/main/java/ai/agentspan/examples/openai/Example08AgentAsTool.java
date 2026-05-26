// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.openai;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.annotations.Tool;
import ai.agentspan.frameworks.OpenAIAgent;
import ai.agentspan.model.AgentResult;

import java.util.Arrays;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.Set;

/**
 * Example OpenAi 08 — Agent as Tool (manager pattern)
 *
 * <p>Java port of <code>sdk/python/examples/openai/08_agent_as_tool.py</code>.
 *
 * <p>Demonstrates: a manager agent that delegates to two specialist
 * sub-agents (sentiment analyzer + keyword extractor) to produce a unified
 * text analysis summary.
 *
 * <p>Python parity gap: the Python original uses {@code Agent.as_tool()} to
 * wrap each specialist as a callable tool so the manager retains control
 * and synthesises the results. The Java {@link OpenAIAgent} factory has
 * no {@code asTool()} equivalent, so we wire the specialists as
 * {@code handoffs(...)} instead — the LLM still routes to the right
 * specialist, but control is handed off rather than retained.
 *
 * <p>Requirements:
 * <ul>
 *   <li>AGENTSPAN_SERVER_URL=http://localhost:6767/api</li>
 *   <li>AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini</li>
 * </ul>
 */
public class Example08AgentAsTool {

    static class SentimentTools {
        private static final Set<String> POSITIVE = new HashSet<>(Arrays.asList(
                "great", "love", "excellent", "amazing", "wonderful", "best"));
        private static final Set<String> NEGATIVE = new HashSet<>(Arrays.asList(
                "bad", "terrible", "hate", "awful", "worst", "horrible"));

        @Tool(name = "analyze_sentiment",
                description = "Analyze the sentiment of text. Returns positive, negative, or neutral.")
        public String analyzeSentiment(String text) {
            Set<String> words = new HashSet<>(Arrays.asList(text.toLowerCase().split("\\s+")));
            Set<String> pos = new HashSet<>(words); pos.retainAll(POSITIVE);
            Set<String> neg = new HashSet<>(words); neg.retainAll(NEGATIVE);
            int p = pos.size();
            int n = neg.size();
            int total = p + n;
            if (p > n) return "Positive sentiment (score: " + p + "/" + total + ")";
            if (n > p) return "Negative sentiment (score: " + n + "/" + total + ")";
            return "Neutral sentiment";
        }
    }

    static class KeywordTools {
        private static final Set<String> STOP_WORDS = new HashSet<>(Arrays.asList(
                "the", "a", "an", "is", "are", "was", "were", "in", "on", "at",
                "to", "for", "of", "and", "or", "but", "with", "this", "that", "i"));

        @Tool(name = "extract_keywords", description = "Extract key topics and keywords from text.")
        public String extractKeywords(String text) {
            String[] tokens = text.toLowerCase().split("\\s+");
            Set<String> uniqueOrdered = new LinkedHashSet<>();
            for (String raw : tokens) {
                String w = raw.replaceAll("[.,!?]", "");
                if (w.length() > 3 && !STOP_WORDS.contains(w)) {
                    uniqueOrdered.add(w);
                }
                if (uniqueOrdered.size() >= 10) break;
            }
            return "Keywords: " + String.join(", ", uniqueOrdered);
        }
    }

    public static void main(String[] args) {
        Agent sentimentAgent = OpenAIAgent.builder()
                .name("sentiment_analyzer")
                .instructions(
                        "You analyze text sentiment. Use the analyze_sentiment tool and "
                                + "provide a brief interpretation.")
                .model(Settings.LLM_MODEL)
                .tools(new SentimentTools())
                .build();

        Agent keywordAgent = OpenAIAgent.builder()
                .name("keyword_extractor")
                .instructions(
                        "You extract keywords from text. Use the extract_keywords tool and "
                                + "categorize the results.")
                .model(Settings.LLM_MODEL)
                .tools(new KeywordTools())
                .build();

        Agent manager = OpenAIAgent.builder()
                .name("text_analysis_manager")
                .instructions(
                        "You are a text analysis manager. When given text to analyze:\n"
                                + "1. Use the sentiment analyzer to understand the tone\n"
                                + "2. Use the keyword extractor to identify key topics\n"
                                + "3. Synthesize the results into a concise summary\n\n"
                                + "Always use both tools before providing your summary.")
                .model(Settings.LLM_MODEL)
                .handoffs(sentimentAgent, keywordAgent)
                .build();

        AgentResult result = Agentspan.run(
                manager,
                "Analyze this review: 'The new laptop is excellent! The display is amazing "
                        + "and the battery life is wonderful. However, the keyboard feels terrible "
                        + "and the trackpad is the worst I've used.'");
        result.printResult();

        Agentspan.shutdown();
    }
}
