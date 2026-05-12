// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.GoogleADKAgent;
import ai.agentspan.model.AgentResult;
import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.Tool;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Example Adk 24 — Planner
 *
 * <p>Java port of <code>sdk/python/examples/adk/24_planner.py</code>.
 *
 * <p>Demonstrates: ADK's {@code BuiltInPlanner} with
 * {@code ThinkingConfig(thinking_budget=1024)} for adding a planning phase.
 * The Java {@link GoogleADKAgent} builder does not expose planner config;
 * we encode the planning intent in the agent instruction.
 */
public class ExampleAdk24Planner {

    static class ResearchWriterTools {

        @Tool(name = "search_web", value = "Search the web for information.")
        public Map<String, Object> searchWeb(@P("query") String query) {
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

        @Tool(name = "write_section", value = "Write a section of a report.")
        public Map<String, Object> writeSection(
                @P("title") String title,
                @P("content") String content) {
            return Map.of("section", "## " + title + "\n\n" + content);
        }
    }

    public static void main(String[] args) {
        // Planner intent: encode the "plan first, then act" instruction inline.
        Agent agent = GoogleADKAgent.builder()
            .name("research_writer")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a research writer. When given a topic:\n"
                + "1. First produce a brief step-by-step PLAN for the report (act as a planner).\n"
                + "2. Then execute the plan: research the topic thoroughly and write a "
                + "structured report with multiple sections.")
            .tools(new ResearchWriterTools())
            .build();

        AgentResult result = Agentspan.run(agent,
            "Write a brief report on the current state of renewable energy "
            + "and climate change solutions.");
        result.printResult();

        Agentspan.shutdown();
    }
}
