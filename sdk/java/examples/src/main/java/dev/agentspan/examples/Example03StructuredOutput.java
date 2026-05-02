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
 * Example 03 — Structured Output
 *
 * <p>Demonstrates using outputType to get typed structured output from an agent.
 */
public class Example03StructuredOutput {

    /** Structured output type for weather data. */
    public static class WeatherReport {
        public String city;
        public double temperature;
        public String condition;
        public String recommendation;

        @Override
        public String toString() {
            return String.format(
                "WeatherReport{city=%s, temp=%.1f, condition=%s, rec=%s}",
                city, temperature, condition, recommendation);
        }
    }

    static class WeatherTools {
        @Tool(name = "get_weather", description = "Get current weather data for a city")
        public Map<String, Object> getWeather(String city) {
            return Map.of("city", city, "temp_f", 72, "condition", "Sunny", "humidity", 45);
        }
    }

    public static void main(String[] args) {
        WeatherTools weatherTools = new WeatherTools();
        List<ToolDef> tools = ToolRegistry.fromInstance(weatherTools);

        Agent agent = Agent.builder()
            .name("weather_reporter")
            .model(Settings.LLM_MODEL)
            .instructions("You are a weather reporter. Get the weather and provide a recommendation.")
            .tools(tools)
            .outputType(WeatherReport.class)
            .build();

        AgentResult result = Agentspan.run(agent, "What's the weather in NYC?");
        result.printResult();

        // Get the typed output
        if (result.isSuccess()) {
            WeatherReport report = result.getOutput(WeatherReport.class);
            if (report != null) {
                System.out.println("\nTyped output:");
                System.out.println("  City: " + report.city);
                System.out.println("  Temperature: " + report.temperature);
                System.out.println("  Condition: " + report.condition);
                System.out.println("  Recommendation: " + report.recommendation);
            }
        }

        Agentspan.shutdown();
    }
}
