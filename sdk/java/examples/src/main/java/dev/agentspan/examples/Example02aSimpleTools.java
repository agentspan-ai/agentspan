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
 * Example 02a — Simple Tool Calling
 *
 * <p>Two tools — weather and stock price. Based on the user's question,
 * the LLM decides which tool to call.
 *
 * <p>In the Conductor UI each tool call appears as a separate DynamicTask
 * with its inputs and outputs clearly visible.
 */
public class Example02aSimpleTools {

    static class AssistantTools {
        @Tool(name = "get_weather", description = "Get the current weather for a city")
        public Map<String, Object> getWeather(String city) {
            return Map.of("city", city, "temp_f", 72, "condition", "Sunny");
        }

        @Tool(name = "get_stock_price", description = "Get the current stock price for a ticker symbol")
        public Map<String, Object> getStockPrice(String symbol) {
            return Map.of("symbol", symbol, "price", 182.50, "change", "+1.2%");
        }
    }

    public static void main(String[] args) {
        List<ToolDef> tools = ToolRegistry.fromInstance(new AssistantTools());

        Agent agent = Agent.builder()
            .name("weather_stock_agent")
            .model(Settings.LLM_MODEL)
            .tools(tools)
            .instructions("You are a helpful assistant. Use tools to answer questions.")
            .build();

        // The LLM will call get_weather (not get_stock_price)
        AgentResult result = Agentspan.run(agent, "What's the weather like in San Francisco?");
        result.printResult();

        Agentspan.shutdown();
    }
}
