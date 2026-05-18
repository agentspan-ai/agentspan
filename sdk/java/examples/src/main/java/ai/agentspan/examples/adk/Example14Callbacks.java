// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.GoogleADKAgent;
import ai.agentspan.model.AgentResult;
import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.Tool;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Example Adk 14 — Callbacks (customer service)
 *
 * <p>Java port of <code>sdk/python/examples/adk/14_callbacks.py</code>.
 *
 * <p>Demonstrates: a customer service agent with multiple tools. The Python
 * version documents that ADK callbacks (before/after_tool_callback,
 * before/after_model_callback) are Python-side hooks that may not execute
 * server-side when compiled to Conductor workflows; we preserve the tool
 * shapes and example flow.
 */
public class Example14Callbacks {

    static class CustomerTools {

        @Tool(name = "lookup_customer", value = "Look up customer information by ID.")
        public Map<String, Object> lookupCustomer(@P("customer_id") String customerId) {
            Map<String, Map<String, Object>> customers = new LinkedHashMap<>();
            customers.put("C001", Map.of("name", "Alice Smith", "tier", "gold", "balance", 1500.00));
            customers.put("C002", Map.of("name", "Bob Jones", "tier", "silver", "balance", 320.50));
            customers.put("C003", Map.of("name", "Carol White", "tier", "bronze", "balance", 50.00));
            Map<String, Object> customer = customers.get(customerId.toUpperCase());
            if (customer != null) {
                Map<String, Object> result = new LinkedHashMap<>();
                result.put("found", true);
                result.put("customer_id", customerId);
                result.putAll(customer);
                return result;
            }
            return Map.of("found", false, "error", "Customer " + customerId + " not found");
        }

        @Tool(name = "apply_discount", value = "Apply a discount to a customer's account.")
        public Map<String, Object> applyDiscount(
                @P("customer_id") String customerId,
                @P("discount_percent") double discountPercent) {
            if (discountPercent > 50) {
                return Map.of("error", "Discount cannot exceed 50%");
            }
            return Map.of(
                "status", "success",
                "customer_id", customerId,
                "discount_applied", discountPercent + "%",
                "message", "Applied " + discountPercent + "% discount to " + customerId
            );
        }

        @Tool(name = "check_order_status", value = "Check the status of an order.")
        public Map<String, Object> checkOrderStatus(@P("order_id") String orderId) {
            Map<String, Map<String, Object>> orders = new LinkedHashMap<>();
            Map<String, Object> ord1 = new LinkedHashMap<>();
            ord1.put("status", "shipped");
            ord1.put("tracking", "TRK-98765");
            ord1.put("eta", "2025-04-20");
            orders.put("ORD-1001", ord1);
            Map<String, Object> ord2 = new LinkedHashMap<>();
            ord2.put("status", "processing");
            ord2.put("tracking", null);
            ord2.put("eta", "2025-04-25");
            orders.put("ORD-1002", ord2);
            return orders.getOrDefault(orderId.toUpperCase(),
                Map.of("error", "Order " + orderId + " not found"));
        }
    }

    public static void main(String[] args) {
        Agent agent = GoogleADKAgent.builder()
            .name("customer_service_agent")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a helpful customer service agent. "
                + "Use the available tools to look up customer information, "
                + "check order status, and apply discounts when requested. "
                + "Always verify the customer exists before applying discounts.")
            .tools(new CustomerTools())
            .build();

        AgentResult result = Agentspan.run(agent,
            "Look up customer C001 and check if order ORD-1001 has shipped. "
            + "If the customer is gold tier, apply a 10% discount.");
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
