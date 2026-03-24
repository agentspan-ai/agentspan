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
 * Example 03 — Structured Output
 *
 * <p>Demonstrates using outputType to get typed structured output from an agent.
 */
public class Example03StructuredOutput {

    /** Structured output type for weather data. */
    public static class WeatherReport {
        public String city;
        public double temperatureCelsius;
        public String conditions;
        public int humidity;
        public String windSpeed;
        public String recommendation;

        @Override
        public String toString() {
            return String.format(
                "WeatherReport{city=%s, temp=%.1f°C, conditions=%s, humidity=%d%%, wind=%s, rec=%s}",
                city, temperatureCelsius, conditions, humidity, windSpeed, recommendation);
        }
    }

    static class WeatherTools {
        @Tool(name = "get_weather_data", description = "Get detailed weather data for a city")
        public String getWeatherData(String city) {
            return String.format(
                "city=%s temperature=22.5 conditions=Partly Cloudy humidity=65 wind=15km/h NW",
                city);
        }
    }

    public static void main(String[] args) {
        WeatherTools weatherTools = new WeatherTools();
        List<ToolDef> tools = ToolRegistry.fromInstance(weatherTools);

        Agent agent = Agent.builder()
            .name("weather_structured")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a weather assistant. Use the get_weather_data tool and return a structured weather report. "
                + "Include a recommendation for what to wear or bring based on conditions.")
            .tools(tools)
            .outputType(WeatherReport.class)
            .build();

        AgentResult result = Agentspan.run(agent, "Get the weather report for Tokyo");
        result.printResult();

        // Get the typed output
        if (result.isSuccess()) {
            WeatherReport report = result.getOutput(WeatherReport.class);
            if (report != null) {
                System.out.println("\nTyped output:");
                System.out.println("  City: " + report.city);
                System.out.println("  Temperature: " + report.temperatureCelsius + "°C");
                System.out.println("  Conditions: " + report.conditions);
                System.out.println("  Recommendation: " + report.recommendation);
            }
        }

        Agentspan.shutdown();
    }
}
