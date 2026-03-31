// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import com.fasterxml.jackson.databind.ObjectMapper;
import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.annotations.Tool;
import dev.agentspan.internal.AgentConfigSerializer;
import dev.agentspan.internal.ToolRegistry;
import dev.agentspan.model.AgentResult;

import java.util.List;
import java.util.Map;

/**
 * Example 57 — Plan Dry Run
 *
 * <p>Demonstrates inspecting the serialized agent configuration (the workflow plan)
 * before actually executing the agent. This is useful for:
 * <ul>
 *   <li>Debugging agent setup without consuming LLM credits</li>
 *   <li>Validating tool schemas and guardrail definitions</li>
 *   <li>Understanding exactly what gets sent to the Agentspan server</li>
 * </ul>
 *
 * <p>The {@link AgentConfigSerializer} converts the in-memory {@link Agent} into
 * the camelCase JSON map that is POSTed to {@code /agent/start}.
 */
public class Example57PlanDryRun {

    static class ResearchTools {

        @Tool(name = "search_web_57", description = "Search the web for information on a topic")
        public Map<String, Object> searchWeb(String query) {
            return Map.of(
                "query", query,
                "results", List.of(
                    "Result 1: Overview of " + query,
                    "Result 2: History and background of " + query,
                    "Result 3: Recent developments in " + query
                )
            );
        }

        @Tool(name = "write_report_57", description = "Write a formatted report section")
        public Map<String, Object> writeReport(String title, String content) {
            return Map.of(
                "section", "## " + title + "\n\n" + content
            );
        }
    }

    public static void main(String[] args) throws Exception {
        Agent agent = Agent.builder()
            .name("research_writer_57")
            .model(Settings.LLM_MODEL)
            .tools(ToolRegistry.fromInstance(new ResearchTools()))
            .maxTurns(10)
            .instructions(
                "You are a research writer. Research topics and write reports.")
            .build();

        // ── Dry run: inspect the agent config before execution ─────────────
        AgentConfigSerializer serializer = new AgentConfigSerializer();
        Map<String, Object> configMap = serializer.serialize(agent);

        ObjectMapper mapper = new ObjectMapper();
        String prettyJson = mapper.writerWithDefaultPrettyPrinter().writeValueAsString(configMap);

        System.out.println("=== Agent Plan (Dry Run) ===");
        System.out.println("Agent name : " + configMap.get("name"));

        @SuppressWarnings("unchecked")
        List<Map<String, Object>> tools = (List<Map<String, Object>>) configMap.get("tools");
        int toolCount = (tools != null) ? tools.size() : 0;
        System.out.println("Tools      : " + toolCount);
        if (tools != null) {
            for (Map<String, Object> tool : tools) {
                System.out.println("  - " + tool.get("name") + ": " + tool.get("description"));
            }
        }

        System.out.println("Max turns  : " + configMap.get("maxTurns"));

        System.out.println("\n--- Full Agent Config JSON ---");
        System.out.println(prettyJson);

        // ── Now actually run the agent ─────────────────────────────────────
        System.out.println("\n=== Running Agent ===");
        AgentResult result = Agentspan.run(agent,
            "Research the history of the internet and write a brief report.");
        result.printResult();

        Agentspan.shutdown();
    }
}
