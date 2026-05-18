// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.GoogleADKAgent;
import ai.agentspan.model.AgentResult;
import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.Tool;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Example Adk 02 — Function Tools
 *
 * <p>Java port of <code>sdk/python/examples/adk/02_function_tools.py</code>.
 *
 * <p>Demonstrates: multiple Google ADK tools with typed parameters. The
 * runtime reflects {@code @Tool}-annotated methods and registers them as
 * workers; the server normalizes them into worker tasks.
 */
public class Example02FunctionTools {

    static class TravelTools {

        @Tool(name = "get_weather", value = "Get the current weather for a city.")
        public Map<String, Object> getWeather(@P("city") String city) {
            Map<String, Map<String, Object>> weatherData = new LinkedHashMap<>();
            weatherData.put("tokyo", Map.of("temp_c", 22, "condition", "Clear", "humidity", 65));
            weatherData.put("paris", Map.of("temp_c", 18, "condition", "Partly Cloudy", "humidity", 72));
            weatherData.put("sydney", Map.of("temp_c", 25, "condition", "Sunny", "humidity", 58));
            weatherData.put("mumbai", Map.of("temp_c", 32, "condition", "Humid", "humidity", 85));
            Map<String, Object> data = weatherData.getOrDefault(city.toLowerCase(),
                Map.of("temp_c", 20, "condition", "Unknown", "humidity", 50));
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("city", city);
            result.putAll(data);
            return result;
        }

        @Tool(name = "convert_temperature", value = "Convert temperature between Celsius and Fahrenheit.")
        public Map<String, Object> convertTemperature(
                @P("temp_celsius") double tempCelsius,
                @P("to_unit") String toUnit) {
            String unit = toUnit == null ? "fahrenheit" : toUnit.toLowerCase();
            if ("fahrenheit".equals(unit)) {
                double converted = tempCelsius * 9.0 / 5.0 + 32;
                return Map.of("celsius", tempCelsius, "fahrenheit", Math.round(converted * 10.0) / 10.0);
            } else if ("kelvin".equals(unit)) {
                double converted = tempCelsius + 273.15;
                return Map.of("celsius", tempCelsius, "kelvin", Math.round(converted * 10.0) / 10.0);
            }
            return Map.of("error", "Unknown unit: " + toUnit);
        }

        @Tool(name = "get_time_zone", value = "Get the timezone for a city.")
        public Map<String, Object> getTimeZone(@P("city") String city) {
            Map<String, Map<String, Object>> timezones = new LinkedHashMap<>();
            timezones.put("tokyo", Map.of("timezone", "JST", "utc_offset", "+9:00"));
            timezones.put("paris", Map.of("timezone", "CET", "utc_offset", "+1:00"));
            timezones.put("sydney", Map.of("timezone", "AEST", "utc_offset", "+10:00"));
            timezones.put("mumbai", Map.of("timezone", "IST", "utc_offset", "+5:30"));
            return timezones.getOrDefault(city.toLowerCase(),
                Map.of("timezone", "Unknown", "utc_offset", "Unknown"));
        }
    }

    public static void main(String[] args) {
        Agent agent = GoogleADKAgent.builder()
            .name("travel_assistant")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a travel assistant. Help users with weather information, "
                + "temperature conversions, and timezone lookups. Be concise and accurate.")
            .tools(new TravelTools())
            .build();

        AgentResult result = Agentspan.run(agent,
            "What's the weather in Tokyo right now? Convert the temperature to "
            + "Fahrenheit and tell me what timezone they're in.");
        result.printResult();

        Agentspan.shutdown();
    }
}
