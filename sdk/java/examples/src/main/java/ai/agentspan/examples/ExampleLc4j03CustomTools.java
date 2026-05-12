// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.LangChain4jAgent;
import ai.agentspan.model.AgentResult;

import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.Tool;

import java.util.Locale;

/**
 * Example Lc4j 03 — Custom Tools
 *
 * <p>Java port of <code>sdk/python/examples/langchain/03_custom_tools.py</code>.
 * Multi-argument tools with typed parameters — unit conversion and formatting
 * utilities. The Python version uses {@code StructuredTool.from_function}; the
 * Java port uses {@link Tool @Tool}-annotated methods, which give LangChain4j
 * an equivalent typed-argument schema.
 *
 * <p>Demonstrates:
 * <ul>
 *   <li>Tools with multiple typed parameters</li>
 *   <li>Mapping LangChain4j {@code @P} parameter names into the tool's JSON schema</li>
 *   <li>Temperature conversion and number formatting</li>
 * </ul>
 *
 * <p>Requirements:
 * <ul>
 *   <li>{@code AGENTSPAN_SERVER_URL=http://localhost:6767/api}</li>
 *   <li>{@code AGENTSPAN_LLM_MODEL=openai/gpt-4o} (or any provider supported by the server)</li>
 *   <li>OpenAI/provider key configured in server credentials</li>
 * </ul>
 */
public class ExampleLc4j03CustomTools {

    static class CustomTools {

        @Tool(
            name = "convert_temperature",
            value = "Convert temperature between Celsius (C), Fahrenheit (F), and Kelvin (K)."
        )
        public String convertTemperature(
                @P("value") double value,
                @P("from_unit") String fromUnit,
                @P("to_unit") String toUnit) {
            String from = fromUnit.toUpperCase(Locale.ROOT);
            String to = toUnit.toUpperCase(Locale.ROOT);
            if (from.equals(to)) {
                return value + " " + to;
            }
            double celsius;
            if (from.equals("C")) {
                celsius = value;
            } else if (from.equals("F")) {
                celsius = (value - 32) * 5.0 / 9.0;
            } else if (from.equals("K")) {
                celsius = value - 273.15;
            } else {
                return "Unknown unit: " + from;
            }
            double result;
            if (to.equals("C")) {
                result = celsius;
            } else if (to.equals("F")) {
                result = celsius * 9.0 / 5.0 + 32;
            } else if (to.equals("K")) {
                result = celsius + 273.15;
            } else {
                return "Unknown unit: " + to;
            }
            return String.format(Locale.ROOT, "%s°%s = %.2f°%s", trimNumber(value), from, result, to);
        }

        @Tool(
            name = "format_number",
            value = "Format a number with decimal places and optional comma separators."
        )
        public String formatNumber(
                @P("value") double value,
                @P("decimals") int decimals,
                @P("use_commas") boolean useCommas) {
            String pattern = useCommas ? ("%,." + decimals + "f") : ("%." + decimals + "f");
            return String.format(Locale.ROOT, pattern, value);
        }

        /** Render a numeric value the way Python's f"{value}" would (drop ".0" for ints). */
        private static String trimNumber(double v) {
            if (v == Math.floor(v) && !Double.isInfinite(v)) {
                return Long.toString((long) v);
            }
            return Double.toString(v);
        }
    }

    public static void main(String[] args) {
        // Python's create_agent(llm, tools=[...]) sends no system prompt unless
        // the caller provides one — match that by passing null instructions.
        Agent agent = LangChain4jAgent.from(
            "custom_tools_agent",
            Settings.LLM_MODEL,
            null,
            new CustomTools()
        );

        AgentResult result = Agentspan.run(
            agent,
            "Convert 100°C to Fahrenheit and Kelvin. Also format 1234567.891 with 2 decimal places."
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
