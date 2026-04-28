// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.annotations.Tool;
import dev.agentspan.internal.ToolRegistry;
import dev.agentspan.model.AgentResult;
import dev.agentspan.model.ToolDef;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Example 33 — Mixed Local and "External" Worker Tools
 *
 * <p>Demonstrates combining local Conductor workers (running in this JVM)
 * with tools that simulate what external workers from another service would do.
 * In production the {@code process_order} and {@code get_customer} workers would
 * live in a separate microservice; here they are registered locally to keep the
 * example self-contained.
 *
 * <p>The LLM sees all tools uniformly — it doesn't know which run locally vs.
 * in a remote service. The agent mixes local and "remote" tools seamlessly.
 */
public class Example33ExternalWorkers {

    // ── All tools as a single annotated class ────────────────────────────────

    static class SupportTools {

        @Tool(name = "format_response",
              description = "Format a data map into a human-readable string")
        public String formatResponse(String data) {
            return "Formatted: " + data;
        }

        @Tool(name = "get_customer",
              description = "Look up customer details from the CRM system")
        public Map<String, Object> getCustomer(String customerId) {
            // In production this worker runs in the CRM microservice
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("customer_id", customerId != null ? customerId : "unknown");
            result.put("name", "Alice Johnson");
            result.put("email", "alice@example.com");
            result.put("status", "active");
            result.put("since", "2022-03-15");
            return result;
        }

        @Tool(name = "process_order",
              description = "Process a customer order. Actions: refund, cancel, update.")
        public Map<String, Object> processOrder(String orderId, String action) {
            // In production this worker runs in the Order Service
            String id = orderId != null ? orderId : "unknown";
            String act = action != null ? action : "process";
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("order_id", id);
            result.put("action", act);
            result.put("status", "success");
            result.put("message", "Order " + id + " has been " + act + "led.");
            return result;
        }
    }

    public static void main(String[] args) {
        List<ToolDef> tools = ToolRegistry.fromInstance(new SupportTools());

        Agent supportAgent = Agent.builder()
            .name("support_agent_33")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a customer support agent. Use the available tools to "
                + "look up customers, process orders, and format responses. "
                + "Always look up the customer first before processing any order.")
            .tools(tools)
            .build();

        System.out.println("=== Mixed Local + External Worker Tools ===");
        System.out.println("(In production, get_customer and process_order run in separate services)\n");

        AgentResult result = Agentspan.run(supportAgent,
            "Customer C-1234 wants to cancel order ORD-5678. "
            + "Look up the customer, process the cancellation, and give me a formatted summary.");
        result.printResult();

        Agentspan.shutdown();
    }
}
