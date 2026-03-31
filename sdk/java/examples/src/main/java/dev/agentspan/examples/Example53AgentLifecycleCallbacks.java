// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.CallbackHandler;
import dev.agentspan.annotations.Tool;
import dev.agentspan.internal.ToolRegistry;
import dev.agentspan.model.AgentResult;
import dev.agentspan.model.ToolDef;

import java.util.List;
import java.util.Map;

/**
 * Example 53 — Agent Lifecycle Callbacks (composable handler classes)
 *
 * <p>Demonstrates using {@link CallbackHandler} subclasses to hook into agent
 * and model lifecycle events. Multiple handlers chain in list order — each one
 * does a single concern (timing, logging, etc.).
 *
 * <p>Registered as Conductor workers:
 * <ul>
 *   <li>{@code lifecycle_agent_53_before_model} — fires before each LLM call</li>
 *   <li>{@code lifecycle_agent_53_after_model} — fires after each LLM call</li>
 * </ul>
 */
public class Example53AgentLifecycleCallbacks {

    // ── Handler 1: Timing ─────────────────────────────────────────────

    static class TimingHandler extends CallbackHandler {
        private long t0;

        @Override
        public Map<String, Object> onModelStart(Map<String, Object> kwargs) {
            t0 = System.currentTimeMillis();
            System.out.println("  [timing] LLM call started");
            return null;
        }

        @Override
        public Map<String, Object> onModelEnd(Map<String, Object> kwargs) {
            long elapsed = System.currentTimeMillis() - t0;
            System.out.println("  [timing] LLM call finished — " + elapsed + "ms");
            return null;
        }
    }

    // ── Handler 2: Logging ─────────────────────────────────────────────

    static class LoggingHandler extends CallbackHandler {

        @Override
        public Map<String, Object> onModelStart(Map<String, Object> kwargs) {
            Object messages = kwargs.get("messages");
            int count = messages instanceof List ? ((List<?>) messages).size() : 0;
            System.out.println("  [log] Sending " + count + " messages to LLM");
            return null;
        }

        @Override
        public Map<String, Object> onModelEnd(Map<String, Object> kwargs) {
            Object result = kwargs.get("llm_result");
            String snippet = result instanceof String
                ? ((String) result).substring(0, Math.min(80, ((String) result).length()))
                : "";
            System.out.println("  [log] LLM responded: " + snippet);
            return null;
        }
    }

    // ── Tool ──────────────────────────────────────────────────────────

    static class WeatherTools {
        @Tool(name = "lookup_weather_53", description = "Get the current weather for a city")
        public Map<String, Object> lookupWeather(String city) {
            return Map.of("city", city, "temperature", "22C", "condition", "sunny");
        }
    }

    public static void main(String[] args) {
        List<ToolDef> tools = ToolRegistry.fromInstance(new WeatherTools());

        Agent agent = Agent.builder()
            .name("lifecycle_agent_53")
            .model(Settings.LLM_MODEL)
            .instructions("You are a helpful assistant. Use lookup_weather_53 for weather queries.")
            .tools(tools)
            .callbacks(new TimingHandler(), new LoggingHandler())
            .build();

        AgentResult result = Agentspan.run(agent, "What's the weather like in Tokyo?");
        result.printResult();

        Agentspan.shutdown();
    }
}
