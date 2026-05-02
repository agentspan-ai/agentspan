// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.annotations.Tool;
import dev.agentspan.internal.ToolRegistry;
import dev.agentspan.model.AgentResult;
import dev.agentspan.termination.MaxMessageTermination;
import dev.agentspan.termination.TextMentionTermination;
import dev.agentspan.termination.TokenUsageTermination;

import java.util.List;

/**
 * Example 19 — Composable Termination Conditions (AND / OR rules)
 *
 * <p>Demonstrates combining termination conditions using {@code .and()} and {@code .or()}.
 *
 * <ul>
 *   <li>TextMentionTermination — stop when output contains specific text</li>
 *   <li>MaxMessageTermination — stop after N messages</li>
 *   <li>TokenUsageTermination — stop when token budget exceeded</li>
 *   <li>AND / OR composition for complex stop rules</li>
 * </ul>
 */
public class Example19ComposableTermination {

    static class SearchTools {
        @Tool(name = "search", description = "Search for information on a topic")
        public String search(String query) {
            return "Results for '" + query + "': AI agents are autonomous software programs "
                + "that perceive, reason, and act to achieve goals.";
        }
    }

    public static void main(String[] args) {
        List<dev.agentspan.model.ToolDef> searchTools =
            ToolRegistry.fromInstance(new SearchTools());

        // ── Example 1: Simple text mention ────────────────────────────────

        Agent researcher = Agent.builder()
            .name("researcher")
            .model(Settings.LLM_MODEL)
            .instructions("Research the topic and say DONE when you have enough information.")
            .tools(searchTools)
            .termination(TextMentionTermination.of("DONE"))
            .build();

        System.out.println("=== Example 1: TextMentionTermination (stop on DONE) ===");
        AgentResult r1 = Agentspan.run(researcher, "What are AI agents?");
        r1.printResult();

        // ── Example 2: OR — stop on text OR after 5 messages ─────────────

        Agent chatbot = Agent.builder()
            .name("chatbot")
            .model(Settings.LLM_MODEL)
            .instructions("Answer the question. Say GOODBYE when you are finished.")
            .termination(
                TextMentionTermination.of("GOODBYE").or(MaxMessageTermination.of(5))
            )
            .build();

        System.out.println("\n=== Example 2: OR termination (GOODBYE or 5 messages) ===");
        AgentResult r2 = Agentspan.run(chatbot, "Tell me a short fun fact about space.");
        r2.printResult();

        // ── Example 3: AND — stop when BOTH conditions met ────────────────
        // Only terminate when the agent says "FINAL ANSWER" AND we've had at least 3 messages

        Agent deliberator = Agent.builder()
            .name("deliberator")
            .model(Settings.LLM_MODEL)
            .instructions(
                "Research thoroughly. Only provide your FINAL ANSWER after "
                + "using the search tool at least once.")
            .tools(searchTools)
            .termination(
                TextMentionTermination.of("FINAL ANSWER").and(MaxMessageTermination.of(3))
            )
            .build();

        System.out.println("\n=== Example 3: AND termination (FINAL ANSWER + 3 messages) ===");
        AgentResult r3 = Agentspan.run(deliberator, "What are the main types of AI agents?");
        r3.printResult();

        // ── Example 4: Complex composition ────────────────────────────────
        // Stop when: (TERMINATE) OR (DONE + at least 5 messages) OR (token budget exceeded)

        Agent complexAgent = Agent.builder()
            .name("complex_agent")
            .model(Settings.LLM_MODEL)
            .instructions("Research and provide a comprehensive answer. Say DONE when finished.")
            .tools(searchTools)
            .termination(
                TextMentionTermination.of("TERMINATE")
                    .or(TextMentionTermination.of("DONE").and(MaxMessageTermination.of(5)))
                    .or(TokenUsageTermination.ofTotal(10000))
            )
            .build();

        System.out.println("\n=== Example 4: Complex composition (TERMINATE | (DONE & 5msg) | tokens) ===");
        AgentResult r4 = Agentspan.run(complexAgent,
            "Summarize the key benefits of multi-agent AI systems.");
        r4.printResult();

        Agentspan.shutdown();
    }
}
