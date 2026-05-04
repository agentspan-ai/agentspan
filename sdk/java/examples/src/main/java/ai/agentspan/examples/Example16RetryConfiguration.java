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
 * Example 16 — Retry Configuration
 *
 * <p>Demonstrates how to configure retry behaviour on tools using both
 * the {@code @Tool} annotation and the {@code ToolDef} builder pattern.
 *
 * <p>Three retry strategies are supported:
 * <ul>
 *   <li>FIXED — constant delay between retries (default)</li>
 *   <li>LINEAR_BACKOFF — delay increases linearly (delay × attempt)</li>
 *   <li>EXPONENTIAL_BACKOFF — delay increases exponentially (delay × 2^attempt)</li>
 * </ul>
 *
 * <p>Set {@code retryCount=0} to disable retries entirely.
 */
public class Example16RetryConfiguration {

    static class RetryTools {

        @Tool(
            name = "call_api",
            description = "Call external API with linear backoff",
            retryCount = 5,
            retryDelaySeconds = 2,
            retryLogic = "LINEAR_BACKOFF"
        )
        public Map<String, Object> callApi(String endpoint) {
            return Map.of("endpoint", endpoint, "status", "ok");
        }

        @Tool(
            name = "validate",
            description = "Validate input — no retries",
            retryCount = 0
        )
        public Map<String, Object> validate(String data) {
            return Map.of("data", data, "valid", true);
        }
    }

    public static void main(String[] args) {
        // ── @Tool annotation-based tools ──────────────────────────────────
        List<ToolDef> annotationTools = ToolRegistry.fromInstance(new RetryTools());

        // ── ToolDef builder-based tools ───────────────────────────────────

        // Custom retry with default FIXED strategy
        ToolDef fetchData = ToolDef.builder()
            .name("fetch_data")
            .description("Fetch data with default retry (FIXED strategy)")
            .retryCount(10)
            .retryDelaySeconds(5)
            .build();

        // Exponential backoff
        ToolDef processPayment = ToolDef.builder()
            .name("process_payment")
            .description("Process payment with exponential backoff")
            .retryCount(3)
            .retryDelaySeconds(1)
            .retryLogic("EXPONENTIAL_BACKOFF")
            .build();

        // Combine all tools
        List<ToolDef> allTools = new java.util.ArrayList<>();
        allTools.addAll(annotationTools);
        allTools.add(fetchData);
        allTools.add(processPayment);

        Agent agent = Agent.builder()
            .name("retry_demo")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a demo agent showcasing retry configuration. " +
                "Use the available tools to demonstrate different retry strategies."
            )
            .tools(allTools)
            .build();

        AgentResult result = Agentspan.run(agent, "Demo retry configuration");
        result.printResult();

        Agentspan.shutdown();
    }
}
