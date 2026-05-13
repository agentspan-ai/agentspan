// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.AgentRuntime;
import ai.agentspan.annotations.Tool;
import ai.agentspan.enums.EventType;
import ai.agentspan.internal.ToolRegistry;
import ai.agentspan.model.AgentEvent;
import ai.agentspan.model.AgentResult;
import ai.agentspan.model.AgentStream;
import ai.agentspan.model.ToolDef;

import java.util.List;

/**
 * Example 11 — Streaming
 *
 * <p>Demonstrates streaming agent events using {@link AgentRuntime#stream(Agent, String)}.
 * This allows real-time observation of agent thinking, tool calls, and output.
 */
public class Example11Streaming {

    static class ResearchTools {
        @Tool(name = "search_web", description = "Search the web for information")
        public String searchWeb(String query) {
            // Simulated search results
            return String.format(
                "Search results for '%s': " +
                "1. Article about %s from TechCrunch (2024). " +
                "2. Wikipedia overview of %s. " +
                "3. Recent research paper on %s applications.",
                query, query, query, query);
        }

        @Tool(name = "get_statistics", description = "Get current statistics and data for a topic")
        public String getStatistics(String topic) {
            return String.format(
                "Statistics for %s: Market size: $45B, Growth rate: 23%% YoY, " +
                "Key players: 15 major companies, Adoption rate: 34%% in enterprises",
                topic);
        }
    }

    public static void main(String[] args) throws Exception {
        ResearchTools tools = new ResearchTools();
        List<ToolDef> toolDefs = ToolRegistry.fromInstance(tools);

        Agent agent = Agent.builder()
            .name("research_agent")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a research assistant. Use the available tools to gather information "
                + "and provide comprehensive, data-backed answers.")
            .tools(toolDefs)
            .maxTurns(5)
            .build();

        System.out.println("Starting streaming agent execution...\n");

        int thinkingCount = 0;
        int toolCallCount = 0;

        try (AgentRuntime runtime = new AgentRuntime()) {
            AgentStream stream = runtime.stream(agent,
                "What are the latest trends in quantum computing and its business applications?");

            for (AgentEvent event : stream) {
                EventType type = event.getType();

                switch (type) {
                    case THINKING:
                        thinkingCount++;
                        System.out.println("[THINKING] " +
                            truncate(event.getContent(), 100));
                        break;

                    case TOOL_CALL:
                        toolCallCount++;
                        System.out.println("\n[TOOL_CALL] -> " + event.getToolName());
                        if (event.getArgs() != null) {
                            System.out.println("  Args: " + event.getArgs());
                        }
                        break;

                    case TOOL_RESULT:
                        System.out.println("[TOOL_RESULT] <- " + event.getToolName());
                        System.out.println("  Result: " + truncate(
                            event.getResult() != null ? event.getResult().toString() : "null", 150));
                        break;

                    case HANDOFF:
                        System.out.println("[HANDOFF] -> " + event.getTarget());
                        break;

                    case MESSAGE:
                        System.out.println("[MESSAGE] " + event.getContent());
                        break;

                    case GUARDRAIL_PASS:
                        System.out.println("[GUARDRAIL_PASS] " + event.getGuardrailName());
                        break;

                    case GUARDRAIL_FAIL:
                        System.out.println("[GUARDRAIL_FAIL] " + event.getGuardrailName()
                            + ": " + event.getContent());
                        break;

                    case ERROR:
                        System.err.println("[ERROR] " + event.getContent());
                        break;

                    case DONE:
                        System.out.println("\n[DONE] Agent completed");
                        break;

                    default:
                        System.out.println("[" + type + "] " + event.getContent());
                }
            }

            System.out.println("\n--- Summary ---");
            System.out.println("Thinking steps: " + thinkingCount);
            System.out.println("Tool calls: " + toolCallCount);

            AgentResult result = stream.getResult();
            System.out.println("\n=== Final Result ===");
            result.printResult();
        }
    }

    private static String truncate(String s, int maxLen) {
        if (s == null) return "null";
        if (s.length() <= maxLen) return s;
        return s.substring(0, maxLen) + "...";
    }
}
