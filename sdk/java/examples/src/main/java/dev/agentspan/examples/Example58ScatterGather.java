// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.AgentTool;
import dev.agentspan.Agentspan;
import dev.agentspan.annotations.Tool;
import dev.agentspan.internal.AgentConfigSerializer;
import dev.agentspan.internal.ToolRegistry;
import dev.agentspan.model.AgentResult;
import dev.agentspan.model.ToolDef;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Example 58 — Scatter-Gather Pattern
 *
 * <p>Demonstrates a coordinator that fans out a research task to a worker agent
 * running in parallel for each country, then synthesizes the results.
 *
 * <p>Matches Python's {@code scatter_gather()} helper:
 * <ul>
 *   <li>Worker agent with {@code search_knowledge_base} tool and {@code max_turns=5}</li>
 *   <li>Tool-level {@code retryCount=3} and {@code retryDelaySeconds=5} for durability</li>
 *   <li>10-minute coordinator timeout (600s)</li>
 * </ul>
 */
public class Example58ScatterGather {

    static class ResearchTools {
        @Tool(name = "search_knowledge_base",
              description = "Search the knowledge base for information on a topic")
        public Map<String, Object> searchKnowledgeBase(String query) {
            return Map.of(
                "query", query,
                "results", List.of(
                    "Key finding about " + query + ": widely used in production systems",
                    "Community perspective on " + query + ": growing ecosystem",
                    "Performance benchmark for " + query + ": competitive in its niche"
                )
            );
        }
    }

    @SuppressWarnings("unchecked")
    public static void main(String[] args) {
        List<ToolDef> researchTools = ToolRegistry.fromInstance(new ResearchTools());

        // ── Worker: researches a single country ───────────────────────────────

        Agent researcher = Agent.builder()
            .name("researcher")
            .model("anthropic/claude-sonnet-4-20250514")
            .instructions(
                "You are a country analyst. You will be given the name of a country. "
                + "Use the search_knowledge_base tool ONCE to research that country, then "
                + "immediately write a brief 2-3 sentence profile covering: GDP ranking, "
                + "population, primary industries, and one unique fact. "
                + "Do NOT call the tool more than once — synthesize from the first result.")
            .tools(researchTools)
            .maxTurns(5)
            .build();

        // ── Build agent_tool with retryCount and retryDelaySeconds ────────────

        ToolDef baseAgentTool = AgentTool.from(researcher);
        Map<String, Object> toolConfig = new LinkedHashMap<>(
            (Map<String, Object>) baseAgentTool.getConfig());
        toolConfig.put("retryCount", 3);
        toolConfig.put("retryDelaySeconds", 5);

        ToolDef workerTool = ToolDef.builder()
            .name(baseAgentTool.getName())
            .description(baseAgentTool.getDescription())
            .toolType(baseAgentTool.getToolType())
            .inputSchema(baseAgentTool.getInputSchema())
            .config(toolConfig)
            .agentRef(researcher)
            .build();

        // ── Coordinator: scatters to worker, gathers results ─────────────────

        String workerName = researcher.getName();
        String instructions =
            "You are a scatter-gather coordinator. Your job is to:\n"
            + "1. Decompose the input into N independent sub-problems\n"
            + "2. Call the '" + workerName + "' tool MULTIPLE TIMES IN PARALLEL — once per sub-problem, "
            + "each with a clear, self-contained prompt\n"
            + "3. After all results return, synthesize them into a unified answer\n\n"
            + "IMPORTANT: Issue all '" + workerName + "' tool calls in a SINGLE response to maximize parallelism.\n\n"
            + "After gathering all country reports, compile a 'Global Country Profiles' report "
            + "organized by continent, with a brief summary table at the top showing the top 10 "
            + "countries by GDP.";

        Agent coordinator = Agent.builder()
            .name("coordinator")
            .model(Settings.SECONDARY_LLM_MODEL)
            .instructions(instructions)
            .tools(List.of(workerTool))
            .timeoutSeconds(600)
            .build();

        AgentResult result = Agentspan.run(coordinator,
            "Create a comprehensive profile for each of the 100 countries listed.");
        result.printResult();

        Agentspan.shutdown();
    }
}
