// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;
import com.google.adk.tools.Annotations.Schema;
import com.google.adk.tools.FunctionTool;

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

    @Schema(description = "Look up customer information by ID.")
    public static Map<String, Object> lookupCustomer(
            @Schema(name = "customer_id", description = "Customer ID") String customerId) {
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

    @Schema(description = "Apply a discount to a customer's account.")
    public static Map<String, Object> applyDiscount(
            @Schema(name = "customer_id", description = "Customer ID") String customerId,
            @Schema(name = "discount_percent", description = "Discount percent (max 50)") double discountPercent) {
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

    @Schema(description = "Check the status of an order.")
    public static Map<String, Object> checkOrderStatus(
            @Schema(name = "order_id", description = "Order ID") String orderId) {
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

    public static void main(String[] args) {
        LlmAgent calculator = LlmAgent.builder()
            .name("customer_service_agent")
            .description("Handles customer service lookups, order status checks, and discount application.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a helpful customer service calculator.
                Use the available tools to look up customer information,
                check order status, and apply discounts when requested.
                Always verify the customer exists before applying discounts.
                """)
            .tools(
                FunctionTool.create(Example14Callbacks.class, "lookupCustomer"),
                FunctionTool.create(Example14Callbacks.class, "applyDiscount"),
                FunctionTool.create(Example14Callbacks.class, "checkOrderStatus"))
            .build();

        AgentResult result = Agentspan.run(calculator,
            "Look up customer C001 and check if order ORD-1001 has shipped. "
            + "If the customer is gold tier, apply a 10% discount.");
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
