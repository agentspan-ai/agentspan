// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.Agentspan;
import ai.agentspan.examples.Settings;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;
import com.google.adk.tools.Annotations.Schema;
import com.google.adk.tools.FunctionTool;

import java.util.Map;

/**
 * Example Adk 02 — Native ADK {@link FunctionTool}s wired through Agentspan.
 *
 * <p>Tools are static methods annotated with {@code @Schema} — the idiomatic
 * ADK pattern — and packaged via {@code FunctionTool.create(Class, "methodName")}.
 * No Agentspan-specific annotations.
 */
public class Example02FunctionTools {

    @Schema(description = "Get the current weather for a city")
    public static Map<String, Object> getWeather(
            @Schema(name = "city", description = "Name of the city") String city) {
        Map<String, Map<String, Object>> data = Map.of(
                "tokyo",  Map.of("temp_c", 22, "condition", "Clear",         "humidity", 65),
                "paris",  Map.of("temp_c", 18, "condition", "Partly Cloudy", "humidity", 72),
                "sydney", Map.of("temp_c", 25, "condition", "Sunny",         "humidity", 58),
                "mumbai", Map.of("temp_c", 32, "condition", "Humid",         "humidity", 85)
        );
        Map<String, Object> row = data.getOrDefault(city.toLowerCase(),
                Map.of("temp_c", 20, "condition", "Unknown", "humidity", 50));
        return Map.of("city", city, "temp_c", row.get("temp_c"),
                "condition", row.get("condition"), "humidity", row.get("humidity"));
    }

    @Schema(description = "Convert temperature between Celsius and Fahrenheit")
    public static Map<String, Object> convertTemperature(
            @Schema(name = "temp_celsius", description = "Temperature in Celsius") double tempCelsius,
            @Schema(name = "to_unit",      description = "Target unit (fahrenheit or kelvin)") String toUnit) {
        if ("fahrenheit".equalsIgnoreCase(toUnit)) {
            double f = tempCelsius * 9 / 5 + 32;
            return Map.of("celsius", tempCelsius, "fahrenheit", Math.round(f * 10.0) / 10.0);
        }
        if ("kelvin".equalsIgnoreCase(toUnit)) {
            double k = tempCelsius + 273.15;
            return Map.of("celsius", tempCelsius, "kelvin", Math.round(k * 10.0) / 10.0);
        }
        return Map.of("error", "Unknown unit: " + toUnit);
    }

    public static void main(String[] args) {
        LlmAgent calculator = LlmAgent.builder()
                .name("travel_assistant")
                .description("Answers weather and temperature-conversion questions for travelers.")
                .model(Settings.LLM_MODEL)
                .instruction("You are a travel assistant. Help users with weather and temperature conversions. "
                        + "Be concise and accurate.")
                .tools(
                        FunctionTool.create(Example02FunctionTools.class, "getWeather"),
                        FunctionTool.create(Example02FunctionTools.class, "convertTemperature")
                )
                .build();

        AgentResult result = Agentspan.run(calculator,
                "What's the weather in Tokyo? Convert the temperature to Fahrenheit.");
        result.printResult();

        Agentspan.shutdown();
    }
}
