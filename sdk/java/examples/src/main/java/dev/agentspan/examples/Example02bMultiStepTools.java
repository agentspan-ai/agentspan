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
 * Example 02b — Multi-Step Tool Calling
 *
 * <p>Demonstrates chained tool calls where the agent calls tools sequentially,
 * feeding each result into the next decision:
 * <ol>
 *   <li>lookup_customer — look up a customer by email</li>
 *   <li>get_transactions — fetch recent transactions for that customer</li>
 *   <li>calculate_total — sum the transaction amounts</li>
 *   <li>send_summary_email — send a summary (simulated)</li>
 * </ol>
 *
 * <p>In the Conductor UI each tool call appears as a separate DynamicTask with
 * clear inputs/outputs, making it easy to trace the reasoning chain.
 */
public class Example02bMultiStepTools {

    static class AccountTools {
        @Tool(name = "lookup_customer", description = "Look up a customer by email address")
        public Map<String, Object> lookupCustomer(String email) {
            Map<String, Object> customers = Map.of(
                "alice@example.com", Map.of("id", "CUST-001", "name", "Alice Johnson", "tier", "gold"),
                "bob@example.com", Map.of("id", "CUST-002", "name", "Bob Smith", "tier", "silver")
            );
            Object found = customers.get(email);
            if (found != null) {
                @SuppressWarnings("unchecked")
                Map<String, Object> result = (Map<String, Object>) found;
                return result;
            }
            return Map.of("error", "No customer found for " + email);
        }

        @Tool(name = "get_transactions", description = "Get recent transactions for a customer")
        public Map<String, Object> getTransactions(String customerId, int limit) {
            if ("CUST-001".equals(customerId)) {
                List<Map<String, Object>> txns = List.of(
                    Map.of("date", "2026-02-15", "amount", 120.00, "merchant", "Cloud Services Inc"),
                    Map.of("date", "2026-02-12", "amount", 45.50, "merchant", "Office Supplies Co"),
                    Map.of("date", "2026-02-10", "amount", 230.00, "merchant", "Dev Tools Ltd")
                );
                int n = Math.min(limit > 0 ? limit : txns.size(), txns.size());
                return Map.of("customer_id", customerId, "transactions", txns.subList(0, n));
            }
            return Map.of("customer_id", customerId, "transactions", List.of());
        }

        @Tool(name = "calculate_total", description = "Calculate the sum of amounts given as a comma-separated string, e.g. '120.0,45.5,230.0'")
        public Map<String, Object> calculateTotal(String amountsCsv) {
            String[] parts = amountsCsv.split(",");
            double total = 0;
            int count = 0;
            for (String part : parts) {
                String trimmed = part.trim();
                if (!trimmed.isEmpty()) {
                    total += Double.parseDouble(trimmed);
                    count++;
                }
            }
            return Map.of("total", Math.round(total * 100.0) / 100.0, "count", count);
        }

        @Tool(name = "send_summary_email", description = "Send a summary email to a customer")
        public Map<String, Object> sendSummaryEmail(String to, String subject, String body) {
            return Map.of("status", "sent", "to", to, "subject", subject);
        }
    }

    public static void main(String[] args) {
        List<ToolDef> tools = ToolRegistry.fromInstance(new AccountTools());

        Agent agent = Agent.builder()
            .name("account_analyst")
            .model(Settings.LLM_MODEL)
            .tools(tools)
            .instructions(
                "You are an account analyst. When asked about a customer, look them up, "
                + "fetch their transactions, calculate the total, and provide a summary. "
                + "Use the tools step by step.")
            .build();

        AgentResult result = Agentspan.run(agent,
            "How much has alice@example.com spent recently? "
            + "Get her last 3 transactions and give me the total.");
        result.printResult();

        Agentspan.shutdown();
    }
}
