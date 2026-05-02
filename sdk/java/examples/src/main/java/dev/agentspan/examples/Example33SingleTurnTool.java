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
 * Example 33 (Single Turn) — Single-Turn Tool Call
 *
 * <p>The simplest tool-calling pattern: the user asks a question, the LLM
 * calls a tool to get data, then responds with the answer. No iterative
 * loop — the agent runs for exactly one exchange.
 *
 * <pre>
 * LLM(prompt, tools) → tool executes → LLM sees result → answer
 * </pre>
 *
 * <p>{@code maxTurns(2)} = 1 turn to call the tool + 1 turn to answer.
 */
public class Example33SingleTurnTool {

    static class WeatherTools {
        @Tool(name = "get_weather_single", description = "Get the current weather for a city")
        public Map<String, Object> getWeather(String city) {
            return Map.of("city", city, "temp_f", 72, "condition", "Sunny");
        }
    }

    public static void main(String[] args) {
        List<ToolDef> tools = ToolRegistry.fromInstance(new WeatherTools());

        Agent agent = Agent.builder()
            .name("weather_agent_single")
            .model(Settings.LLM_MODEL)
            .instructions("You are a weather assistant. Use the get_weather_single tool to answer.")
            .tools(tools)
            .maxTurns(2)
            .build();

        AgentResult result = Agentspan.run(agent, "What's the weather in San Francisco?");
        result.printResult();

        Agentspan.shutdown();
    }
}
