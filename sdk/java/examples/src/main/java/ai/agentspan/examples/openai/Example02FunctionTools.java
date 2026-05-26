// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.openai;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.annotations.Tool;
import ai.agentspan.frameworks.OpenAIAgent;
import ai.agentspan.model.AgentResult;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Example OpenAi 02 — Function Tools
 *
 * <p>Java port of <code>sdk/python/examples/openai/02_function_tools.py</code>.
 *
 * <p>Demonstrates: an OpenAI Agents SDK-style agent that calls multiple
 * function-tools (weather, calculator, population lookup). Each tool method
 * carries an Agentspan {@link Tool} annotation — the {@link OpenAIAgent}
 * reflection bridge wraps them as Agentspan worker tools.
 *
 * <p>Note on annotation choice: the Python example uses
 * {@code @function_tool}; in Java the {@code OpenAIAgent} factory accepts
 * both {@code @ai.agentspan.annotations.Tool} and
 * {@code @dev.langchain4j.agent.tool.Tool}. We use the Agentspan annotation
 * here because LangChain4j is only a {@code compileOnly} SDK dependency.
 *
 * <p>Requirements:
 * <ul>
 *   <li>AGENTSPAN_SERVER_URL=http://localhost:6767/api</li>
 *   <li>AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini</li>
 * </ul>
 */
public class Example02FunctionTools {

    static class WeatherTools {

        @Tool(name = "get_weather", description = "Get the current weather for a city.")
        public String getWeather(String city) {
            Map<String, String> weatherData = new LinkedHashMap<>();
            weatherData.put("new york", "72F, Partly Cloudy");
            weatherData.put("san francisco", "58F, Foggy");
            weatherData.put("miami", "85F, Sunny");
            weatherData.put("london", "55F, Rainy");
            String value = weatherData.get(city.toLowerCase());
            return value != null ? value : "Weather data not available for " + city;
        }

        @Tool(name = "calculate", description = "Evaluate a mathematical expression and return the result.")
        public String calculate(String expression) {
            // Java has no built-in safe eval; mirror Python's tool surface but
            // return a deterministic string for the limited set of inputs an LLM
            // is likely to hand us. The point of the example is tool wiring.
            try {
                String trimmed = expression.trim();
                // Very simple infix handling for + - * / on two numeric operands.
                String[] ops = {"+", "-", "*", "/"};
                for (String op : ops) {
                    int idx = trimmed.indexOf(op, 1);
                    if (idx > 0) {
                        double a = Double.parseDouble(trimmed.substring(0, idx).trim());
                        double b = Double.parseDouble(trimmed.substring(idx + 1).trim());
                        double r;
                        switch (op) {
                            case "+": r = a + b; break;
                            case "-": r = a - b; break;
                            case "*": r = a * b; break;
                            case "/": r = a / b; break;
                            default: r = 0;
                        }
                        if (r == (long) r) return String.valueOf((long) r);
                        return String.valueOf(r);
                    }
                }
                // Fallback: maybe it's a sqrt expression
                if (trimmed.startsWith("sqrt(") && trimmed.endsWith(")")) {
                    double v = Double.parseDouble(trimmed.substring(5, trimmed.length() - 1));
                    return String.valueOf(Math.sqrt(v));
                }
                return String.valueOf(Double.parseDouble(trimmed));
            } catch (Exception e) {
                return "Error: " + e.getMessage();
            }
        }

        @Tool(name = "lookup_population", description = "Look up the population of a city.")
        public String lookupPopulation(String city) {
            Map<String, String> populations = new LinkedHashMap<>();
            populations.put("new york", "8.3 million");
            populations.put("san francisco", "874,000");
            populations.put("miami", "442,000");
            populations.put("london", "8.8 million");
            String value = populations.get(city.toLowerCase());
            return value != null ? value : "Unknown";
        }
    }

    public static void main(String[] args) {
        Agent agent = OpenAIAgent.builder()
                .name("multi_tool_agent")
                .instructions(
                        "You are a helpful assistant with access to weather, calculator, "
                                + "and population lookup tools. Use them to answer questions accurately.")
                .model(Settings.LLM_MODEL)
                .tools(new WeatherTools())
                .build();

        AgentResult result = Agentspan.run(
                agent,
                "What's the weather in San Francisco? Also, what's the population there "
                        + "and what's the square root of that number (just the digits)?");
        result.printResult();

        Agentspan.shutdown();
    }
}
