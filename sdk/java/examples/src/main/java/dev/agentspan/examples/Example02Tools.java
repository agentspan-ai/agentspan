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

/**
 * Example 02 — Tool-Using Agent
 *
 * <p>Demonstrates defining tools with the {@link Tool} annotation and
 * registering them with an agent via {@link ToolRegistry}.
 */
public class Example02Tools {

    // Define tools in a class with @Tool annotations
    static class WeatherTools {

        @Tool(name = "get_weather", description = "Get the current weather for a city")
        public String getWeather(String city) {
            // In a real app, this would call a weather API
            return String.format("Weather in %s: Sunny, 72°F (22°C), Wind: 5mph NW", city);
        }

        @Tool(name = "get_forecast", description = "Get the 3-day weather forecast for a city")
        public String getForecast(String city, int days) {
            if (days < 1 || days > 7) {
                return "Error: days must be between 1 and 7";
            }
            StringBuilder forecast = new StringBuilder(String.format("Forecast for %s:\n", city));
            String[] conditions = {"Sunny", "Partly Cloudy", "Rainy", "Stormy", "Clear", "Foggy", "Windy"};
            for (int i = 1; i <= days; i++) {
                String condition = conditions[i % conditions.length];
                int temp = 65 + (i * 3);
                forecast.append(String.format("  Day %d: %s, %d°F\n", i, condition, temp));
            }
            return forecast.toString();
        }
    }

    public static void main(String[] args) {
        // Discover @Tool methods via reflection
        WeatherTools weatherTools = new WeatherTools();
        List<ToolDef> tools = ToolRegistry.fromInstance(weatherTools);

        Agent agent = Agent.builder()
            .name("weather_assistant")
            .model(Settings.LLM_MODEL)
            .instructions("You are a helpful weather assistant. Use the provided tools to answer weather questions.")
            .tools(tools)
            .build();

        AgentResult result = Agentspan.run(agent,
            "What's the weather like in San Francisco? Also get me a 3-day forecast.");
        result.printResult();

        Agentspan.shutdown();
    }
}
