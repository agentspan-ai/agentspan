// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.examples;

import org.conductoross.conductor.ai.Agent;
import org.conductoross.conductor.ai.AgentRuntime;
import org.conductoross.conductor.ai.annotations.Tool;
import org.conductoross.conductor.ai.internal.ToolRegistry;
import org.conductoross.conductor.ai.model.AgentResult;
import org.conductoross.conductor.ai.model.ToolDef;

import java.util.List;
import java.util.Map;

/**
 * Example 02 — Tool-Using Agent
 *
 * <p>Demonstrates defining tools with the {@link Tool} annotation and
 * registering them with an agent via {@link ToolRegistry}.
 */
public class Example02Tools {

    static class AgentTools {

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
        AgentRuntime runtime = new AgentRuntime();
        List<ToolDef> tools = ToolRegistry.fromInstance(new AgentTools());

        Agent agent = Agent.builder()
            .name("weather_stock_agent")
            .model(Settings.LLM_MODEL)
            .tools(tools)
            .instructions("You are a helpful assistant. Use tools to answer questions.")
            .build();

        AgentResult result = runtime.run(agent, "What's the weather like in San Francisco?");
        result.printResult();

        runtime.shutdown();
    }
}
