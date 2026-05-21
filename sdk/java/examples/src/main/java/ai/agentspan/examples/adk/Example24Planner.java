// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;
import com.google.adk.tools.Annotations.Schema;
import com.google.adk.tools.FunctionTool;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Example Adk 24 — Planner
 *
 * <p>Java port of <code>sdk/python/examples/adk/24_planner.py</code>.
 *
 * <p>Demonstrates: ADK's planning phase via the native
 * {@code planning(true)} builder flag.
 */
public class Example24Planner {

    @Schema(description = "Search the web for information.")
    public static Map<String, Object> searchWeb(
            @Schema(name = "query", description = "Search query") String query) {
        Map<String, Map<String, Object>> results = new LinkedHashMap<>();
        results.put("climate change solutions", Map.of(
            "results", List.of(
                "Solar energy costs dropped 89% since 2010",
                "Wind power is now cheapest energy source in many regions",
                "Carbon capture technology advancing rapidly"
            )
        ));
        results.put("renewable energy statistics", Map.of(
            "results", List.of(
                "Renewables account for 30% of global electricity (2023)",
                "Solar capacity grew 50% year-over-year",
                "China leads in renewable energy investment"
            )
        ));
        String q = query.toLowerCase();
        for (Map.Entry<String, Map<String, Object>> entry : results.entrySet()) {
            for (String word : entry.getKey().split(" ")) {
                if (q.contains(word)) {
                    Map<String, Object> r = new LinkedHashMap<>();
                    r.put("query", query);
                    r.putAll(entry.getValue());
                    return r;
                }
            }
        }
        return Map.of("query", query, "results", List.of("No specific results found."));
    }

    @Schema(description = "Write a section of a report.")
    public static Map<String, Object> writeSection(
            @Schema(name = "title", description = "Section title") String title,
            @Schema(name = "content", description = "Section content") String content) {
        return Map.of("section", "## " + title + "\n\n" + content);
    }

    public static void main(String[] args) {
        LlmAgent planner = LlmAgent.builder()
            .name("research_writer")
            .description("Plans a report outline first, then executes the plan to write the report.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a research writer. When given a topic:
                1. First produce a brief step-by-step PLAN for the report.
                2. Then execute the plan: research the topic thoroughly and write a
                structured report with multiple sections.
                """)
            .planning(true)
            .tools(
                FunctionTool.create(Example24Planner.class, "searchWeb"),
                FunctionTool.create(Example24Planner.class, "writeSection"))
            .build();

        AgentResult result = Agentspan.run(planner,
            "Write a brief report on the current state of renewable energy "
            + "and climate change solutions.");
        result.printResult();

        Agentspan.shutdown();
    }
}
