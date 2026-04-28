// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.annotations.Tool;
import dev.agentspan.internal.ToolRegistry;
import dev.agentspan.model.AgentResult;
import dev.agentspan.model.ToolDef;

import java.util.List;
import java.util.Map;

/**
 * Example 47 — Callbacks
 *
 * <p>Demonstrates lifecycle hooks that intercept LLM interactions:
 * <ul>
 *   <li>{@code beforeModelCallback} — runs before each LLM call; can log the
 *       messages list or short-circuit by returning a non-empty map with
 *       {@code "response"}</li>
 *   <li>{@code afterModelCallback} — runs after each LLM call; can inspect
 *       or replace the response</li>
 * </ul>
 *
 * <p>Callbacks are registered as Conductor worker tasks
 * ({@code {agentName}_before_model} / {@code {agentName}_after_model}).
 */
public class Example47Callbacks {

    static class FactTools {
        @Tool(name = "get_facts_47", description = "Get interesting facts about a topic")
        public Map<String, Object> getFacts(String topic) {
            Map<String, List<String>> facts = Map.of(
                "ai", List.of("AI was coined in 1956", "GPT-4 has ~1.7T parameters"),
                "space", List.of("The ISS orbits at 17,500 mph", "Mars has the tallest volcano")
            );
            String key = topic.toLowerCase();
            for (Map.Entry<String, List<String>> e : facts.entrySet()) {
                if (key.contains(e.getKey())) {
                    return Map.of("topic", topic, "facts", e.getValue());
                }
            }
            return Map.of("topic", topic, "facts", List.of("No specific facts found."));
        }
    }

    public static void main(String[] args) {
        List<ToolDef> tools = ToolRegistry.fromInstance(new FactTools());

        Agent agent = Agent.builder()
            .name("monitored_agent_47")
            .model(Settings.LLM_MODEL)
            .instructions("You are a helpful assistant. Use get_facts_47 when asked about topics.")
            .tools(tools)
            .beforeModelCallback(inputData -> {
                Object messages = inputData.get("messages");
                int count = messages instanceof List ? ((List<?>) messages).size() : 0;
                System.out.println("  [before_model] Sending " + count + " messages to LLM");
                return Map.of(); // Continue normally
            })
            .afterModelCallback(inputData -> {
                Object result = inputData.get("llm_result");
                int length = result instanceof String ? ((String) result).length() : 0;
                System.out.println("  [after_model] LLM returned " + length + " characters");
                return Map.of(); // Keep original response
            })
            .build();

        AgentResult agentResult = Agentspan.run(agent,
            "Tell me interesting facts about AI and space.");
        agentResult.printResult();

        Agentspan.shutdown();
    }
}
