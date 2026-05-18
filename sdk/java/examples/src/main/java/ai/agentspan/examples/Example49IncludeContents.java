// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.annotations.Tool;
import ai.agentspan.enums.Strategy;
import ai.agentspan.internal.ToolRegistry;
import ai.agentspan.model.AgentResult;
import ai.agentspan.model.ToolDef;

import java.util.List;
import java.util.Map;

/**
 * Example 49 — Include Contents (control context passed to sub-agents)
 *
 * <p>When {@code includeContents("none")} is set, a sub-agent starts with a
 * clean slate and does NOT see the parent agent's conversation history. This
 * is useful for sub-agents that should work independently.
 *
 * <p>Two sub-agents:
 * <ul>
 *   <li>independent_summarizer: {@code includeContents("none")} — clean slate</li>
 *   <li>context_aware_helper: default — sees full conversation history</li>
 * </ul>
 */
public class Example49IncludeContents {

    static class SummaryTools {
        @Tool(name = "summarize_text", description = "Summarize a piece of text to its first 20 words")
        public Map<String, Object> summarizeText(String text) {
            String[] words = text.split("\\s+");
            int count = Math.min(words.length, 20);
            String summary = String.join(" ", java.util.Arrays.copyOf(words, count));
            if (words.length > 20) summary += "...";
            return Map.of("summary", summary, "word_count", words.length);
        }
    }

    public static void main(String[] args) {
        List<ToolDef> summaryTools = ToolRegistry.fromInstance(new SummaryTools());

        // This sub-agent starts with a clean slate — no parent conversation history
        Agent independentSummarizer = Agent.builder()
            .name("independent_summarizer_49")
            .model(Settings.LLM_MODEL)
            .instructions("You are a summarizer. Summarize any text given to you concisely.")
            .tools(summaryTools)
            .includeContents("none")
            .build();

        // This sub-agent sees the parent's full conversation history (default)
        Agent contextAwareHelper = Agent.builder()
            .name("context_aware_helper_49")
            .model(Settings.LLM_MODEL)
            .instructions("You are a helpful assistant that builds on prior conversation context.")
            .build();

        Agent coordinator = Agent.builder()
            .name("coordinator_49")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You coordinate tasks. Route summarization requests to "
                + "independent_summarizer_49 and general questions to context_aware_helper_49.")
            .agents(independentSummarizer, contextAwareHelper)
            .strategy(Strategy.HANDOFF)
            .build();

        System.out.println("=== Scenario 1: Summarization (independent sub-agent, no parent context) ===");
        AgentResult r1 = Agentspan.run(coordinator,
            "Summarize this: Artificial intelligence is transforming industries by automating "
            + "repetitive tasks, improving decision-making, and enabling new capabilities. "
            + "Companies are investing heavily in AI to gain competitive advantages.");
        r1.printResult();

        System.out.println("=== Scenario 2: General question (context-aware sub-agent) ===");
        AgentResult r2 = Agentspan.run(coordinator,
            "What are the key benefits of AI in business?");
        r2.printResult();

        Agentspan.shutdown();
    }
}
