// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.openai;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.annotations.Tool;
import ai.agentspan.frameworks.OpenAIAgent;
import ai.agentspan.model.AgentResult;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Example OpenAi 04 — Handoffs
 *
 * <p>Java port of <code>sdk/python/examples/openai/04_handoffs.py</code>.
 *
 * <p>Demonstrates: an OpenAI Agents SDK triage agent that hands off control
 * to one of three specialist sub-agents (order / refund / sales). Each
 * specialist owns its own tool. The {@link OpenAIAgent} bridge maps
 * {@code handoffs} into the server's handoff strategy.
 *
 * <p>Requirements:
 * <ul>
 *   <li>AGENTSPAN_SERVER_URL=http://localhost:6767/api</li>
 *   <li>AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini</li>
 * </ul>
 */
public class Example04Handoffs {

    // ── Specialist tools ──────────────────────────────────────────────

    static class OrderTools {
        @Tool(name = "check_order_status", description = "Check the status of a customer order.")
        public String checkOrderStatus(String order_id) {
            Map<String, String> orders = new LinkedHashMap<>();
            orders.put("ORD-001", "Shipped - arriving tomorrow");
            orders.put("ORD-002", "Processing - estimated ship date: Friday");
            orders.put("ORD-003", "Delivered on Monday");
            String value = orders.get(order_id);
            return value != null ? value : "Order " + order_id + " not found";
        }
    }

    static class RefundTools {
        @Tool(name = "process_refund", description = "Process a refund for an order.")
        public String processRefund(String order_id, String reason) {
            return "Refund initiated for " + order_id + ". Reason: " + reason
                    + ". Expect 3-5 business days.";
        }
    }

    static class SalesTools {
        @Tool(name = "get_product_info", description = "Get product information and pricing.")
        public String getProductInfo(String product_name) {
            Map<String, String> products = new LinkedHashMap<>();
            products.put("laptop pro", "Laptop Pro X1 - $1,299 - 16GB RAM, 512GB SSD, 14\" display");
            products.put("wireless earbuds", "SoundMax Earbuds - $79 - ANC, 24hr battery, Bluetooth 5.3");
            products.put("smart watch", "TimeSync Watch - $249 - GPS, health tracking, 5-day battery");
            String value = products.get(product_name.toLowerCase());
            return value != null ? value : "Product '" + product_name + "' not found";
        }
    }

    public static void main(String[] args) {
        // ── Specialist agents ─────────────────────────────────────────
        Agent orderAgent = OpenAIAgent.builder()
                .name("order_specialist")
                .instructions(
                        "You handle order-related inquiries. Use the check_order_status tool "
                                + "to look up orders. Be professional and concise.")
                .model(Settings.LLM_MODEL)
                .tools(new OrderTools())
                .build();

        Agent refundAgent = OpenAIAgent.builder()
                .name("refund_specialist")
                .instructions(
                        "You handle refund requests. Use the process_refund tool to initiate "
                                + "refunds. Always confirm the order ID and reason before processing.")
                .model(Settings.LLM_MODEL)
                .tools(new RefundTools())
                .build();

        Agent salesAgent = OpenAIAgent.builder()
                .name("sales_specialist")
                .instructions(
                        "You handle product inquiries and sales. Use the get_product_info tool "
                                + "to look up products. Be enthusiastic but not pushy.")
                .model(Settings.LLM_MODEL)
                .tools(new SalesTools())
                .build();

        // ── Triage agent with handoffs ────────────────────────────────
        Agent triage = OpenAIAgent.builder()
                .name("customer_service_triage")
                .instructions(
                        "You are a customer service triage agent. Determine the customer's need "
                                + "and hand off to the appropriate specialist:\n"
                                + "- Order status inquiries -> order_specialist\n"
                                + "- Refund requests -> refund_specialist\n"
                                + "- Product questions or purchases -> sales_specialist\n"
                                + "Be brief in your initial response before handing off.")
                .model(Settings.LLM_MODEL)
                .handoffs(orderAgent, refundAgent, salesAgent)
                .build();

        AgentResult result = Agentspan.run(
                triage,
                "I'd like a refund for order ORD-002, the product arrived damaged.");
        result.printResult();

        Agentspan.shutdown();
    }
}
