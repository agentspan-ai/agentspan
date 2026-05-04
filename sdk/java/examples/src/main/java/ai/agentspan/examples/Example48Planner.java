// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.annotations.Tool;
import ai.agentspan.internal.ToolRegistry;
import ai.agentspan.model.AgentResult;
import ai.agentspan.model.ToolDef;

import java.util.List;
import java.util.Map;

/**
 * Example 48 — Planner (agent that plans before executing)
 *
 * <p>When {@code planner(true)}, the server enhances the system prompt with
 * planning instructions so the agent creates a step-by-step plan before
 * executing tools. This improves performance on complex, multi-step tasks.
 */
public class Example48Planner {

    static class ResearchTools {
        @Tool(name = "search_web", description = "Search the web for information on a topic")
        public Map<String, Object> searchWeb(String query) {
            Map<String, List<String>> results = Map.of(
                "climate change", List.of(
                    "Solar energy costs dropped 89% since 2010",
                    "Wind power is cheapest electricity in many regions"
                ),
                "renewable energy", List.of(
                    "Renewables = 30% of global electricity (2023)",
                    "Solar capacity grew 50% year-over-year"
                )
            );
            String queryLower = query.toLowerCase();
            for (Map.Entry<String, List<String>> entry : results.entrySet()) {
                boolean matches = java.util.Arrays.stream(entry.getKey().split(" "))
                    .anyMatch(queryLower::contains);
                if (matches) {
                    return Map.of("query", query, "results", entry.getValue());
                }
            }
            return Map.of("query", query, "results", List.of("No specific results found."));
        }

        @Tool(name = "write_section", description = "Write a section of a report with a title and content")
        public Map<String, Object> writeSection(String title, String content) {
            return Map.of("section", "## " + title + "\n\n" + content);
        }
    }

    public static void main(String[] args) {
        List<ToolDef> tools = ToolRegistry.fromInstance(new ResearchTools());

        Agent agent = Agent.builder()
            .name("research_writer_48")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a research writer. Research topics thoroughly and "
                + "write structured reports with multiple sections.")
            .tools(tools)
            .planner(true)
            .build();

        AgentResult result = Agentspan.run(agent,
            "Write a brief report on renewable energy and climate change solutions.");
        result.printResult();

        Agentspan.shutdown();
    }
}
