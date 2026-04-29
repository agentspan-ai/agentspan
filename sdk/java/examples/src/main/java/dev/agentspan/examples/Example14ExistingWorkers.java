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
 * Example 14 — Existing Workers as Agent Tools
 *
 * <p>Demonstrates using multiple {@code @Tool}-annotated methods alongside
 * each other in a single agent — exactly how existing worker functions
 * plug into the agent loop.
 *
 * <p>Shows:
 * <ul>
 *   <li>get_customer_data — look up a customer by ID</li>
 *   <li>get_order_history — fetch recent orders for a customer</li>
 *   <li>create_support_ticket — open a new ticket</li>
 * </ul>
 */
public class Example14ExistingWorkers {

    static class CustomerSupportTools {

        @Tool(name = "get_customer_data", description = "Fetch customer data by customer ID")
        public Map<String, Object> getCustomerData(String customerId) {
            Map<String, Object> customers = Map.of(
                "C001", Map.of("name", "Alice", "plan", "Enterprise", "since", "2021-03"),
                "C002", Map.of("name", "Bob", "plan", "Starter", "since", "2023-11")
            );
            Object found = customers.get(customerId);
            if (found != null) {
                @SuppressWarnings("unchecked")
                Map<String, Object> result = (Map<String, Object>) found;
                return result;
            }
            return Map.of("error", "Customer not found");
        }

        @Tool(name = "get_order_history", description = "Retrieve recent order history for a customer")
        public Map<String, Object> getOrderHistory(String customerId, int limit) {
            Map<String, List<Map<String, Object>>> orders = Map.of(
                "C001", List.of(
                    Map.of("id", "ORD-101", "amount", 250.00, "status", "delivered"),
                    Map.of("id", "ORD-098", "amount", 89.99, "status", "delivered")
                ),
                "C002", List.of(
                    Map.of("id", "ORD-110", "amount", 45.00, "status", "shipped")
                )
            );
            List<Map<String, Object>> customerOrders = orders.getOrDefault(customerId, List.of());
            int n = Math.min(limit > 0 ? limit : customerOrders.size(), customerOrders.size());
            return Map.of("customer_id", customerId, "orders", customerOrders.subList(0, n));
        }

        @Tool(name = "create_support_ticket", description = "Create a support ticket for a customer")
        public Map<String, Object> createSupportTicket(String customerId, String issue, String priority) {
            return Map.of(
                "ticket_id", "TKT-999",
                "customer_id", customerId,
                "issue", issue,
                "priority", priority != null && !priority.isEmpty() ? priority : "medium"
            );
        }
    }

    public static void main(String[] args) {
        List<ToolDef> tools = ToolRegistry.fromInstance(new CustomerSupportTools());

        Agent agent = Agent.builder()
            .name("customer_support")
            .model(Settings.LLM_MODEL)
            .tools(tools)
            .instructions(
                "You are a customer support agent. Use the available tools to look up "
                + "customer information, check order history, and create support tickets.")
            .build();

        AgentResult result = Agentspan.run(agent,
            "Customer C001 is asking about their recent orders. Look them up and summarize.");
        result.printResult();

        Agentspan.shutdown();
    }
}
