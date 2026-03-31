// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.annotations.Tool;
import dev.agentspan.internal.ToolRegistry;
import dev.agentspan.model.AgentResult;
import dev.agentspan.model.PromptTemplate;
import dev.agentspan.model.ToolDef;

import java.util.List;
import java.util.Map;

/**
 * Example 34 — Prompt Templates
 *
 * <p>Demonstrates using server-side prompt templates for agent instructions.
 * Templates are stored once on the Conductor server and referenced by name.
 * Variables substitute {@code ${var}} placeholders at execution time.
 *
 * <p>Requires a template named {@code "order-support"} to exist on the server.
 * Create it via the Conductor UI or API with a body like:
 * <pre>
 *   You are an order support specialist. Maximum refund authority: ${max_refund}.
 *   For issues beyond your authority, escalate to ${escalation_email}.
 * </pre>
 *
 * <p>If the template does not exist on the server, the agent will still run
 * with whatever fallback the server applies for missing templates.
 */
public class Example34PromptTemplates {

    static class OrderTools {
        @Tool(name = "lookup_order_34", description = "Look up an order by ID")
        public Map<String, Object> lookupOrder(String orderId) {
            return Map.of("order_id", orderId, "status", "shipped", "eta", "2 days");
        }

        @Tool(name = "lookup_customer_34", description = "Look up customer details by email")
        public Map<String, Object> lookupCustomer(String email) {
            return Map.of("email", email, "name", "Jane Doe", "tier", "premium");
        }
    }

    public static void main(String[] args) {
        List<ToolDef> tools = ToolRegistry.fromInstance(new OrderTools());

        // Agent using a server-side prompt template with variable substitution
        Agent orderAgent = Agent.builder()
            .name("order_assistant_34")
            .model(Settings.LLM_MODEL)
            .instructionsTemplate(new PromptTemplate(
                "order-support",
                Map.of("max_refund", "$500", "escalation_email", "help@acme.com")
            ))
            .tools(tools)
            .build();

        AgentResult result = Agentspan.run(orderAgent, "Can you check order #12345?");
        result.printResult();

        Agentspan.shutdown();
    }
}
