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

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Example Adk 09 — Multi-Tool Agent
 *
 * <p>Java port of <code>sdk/python/examples/adk/09_multi_tool_agent.py</code>.
 *
 * <p>Demonstrates: complex tool orchestration with multiple specialized tools
 * working together for an e-commerce shopping flow.
 */
public class Example09MultiToolAgent {

    static class ShopTools {

        @Tool(name = "search_products", value = "Search the product catalog.")
        public Map<String, Object> searchProducts(
                @P("query") String query,
                @P("category") String category,
                @P("max_results") int maxResults) {
            String cat = category == null || category.isEmpty() ? "all" : category;
            int max = maxResults <= 0 ? 5 : maxResults;
            List<Map<String, Object>> products = List.of(
                Map.of("id", "P001", "name", "Wireless Mouse", "category", "electronics", "price", 29.99, "rating", 4.5),
                Map.of("id", "P002", "name", "Python Cookbook", "category", "books", "price", 45.00, "rating", 4.8),
                Map.of("id", "P003", "name", "USB-C Hub", "category", "electronics", "price", 39.99, "rating", 4.2),
                Map.of("id", "P004", "name", "Ergonomic Keyboard", "category", "electronics", "price", 89.99, "rating", 4.7),
                Map.of("id", "P005", "name", "Clean Code", "category", "books", "price", 35.00, "rating", 4.9)
            );
            String q = query.toLowerCase();
            List<Map<String, Object>> results = new ArrayList<>();
            for (Map<String, Object> p : products) {
                String name = ((String) p.get("name")).toLowerCase();
                String pcat = (String) p.get("category");
                if (name.contains(q) || (!"all".equals(cat) && pcat.equals(cat))) {
                    results.add(p);
                }
            }
            return Map.of("status", "success",
                "results", results.subList(0, Math.min(max, results.size())),
                "total", results.size());
        }

        @Tool(name = "check_inventory", value = "Check inventory availability for a product.")
        public Map<String, Object> checkInventory(@P("product_id") String productId) {
            Map<String, Map<String, Object>> inventory = new LinkedHashMap<>();
            inventory.put("P001", Map.of("in_stock", true, "quantity", 150, "warehouse", "West"));
            inventory.put("P002", Map.of("in_stock", true, "quantity", 45, "warehouse", "East"));
            inventory.put("P003", Map.of("in_stock", false, "quantity", 0, "restock_date", "2025-04-01"));
            inventory.put("P004", Map.of("in_stock", true, "quantity", 8, "warehouse", "West"));
            inventory.put("P005", Map.of("in_stock", true, "quantity", 200, "warehouse", "East"));
            Map<String, Object> item = inventory.get(productId);
            if (item != null) {
                Map<String, Object> result = new LinkedHashMap<>();
                result.put("status", "success");
                result.put("product_id", productId);
                result.putAll(item);
                return result;
            }
            return Map.of("status", "error", "message", "Product " + productId + " not found");
        }

        @Tool(name = "calculate_shipping", value = "Calculate shipping cost for a list of products.")
        public Map<String, Object> calculateShipping(
                @P("product_ids") List<String> productIds,
                @P("destination") String destination) {
            double baseCost = productIds.size() * 5.99;
            return Map.of(
                "status", "success",
                "destination", destination,
                "items", productIds.size(),
                "options", List.of(
                    Map.of("method", "Standard (5-7 days)", "cost", String.format("$%.2f", baseCost)),
                    Map.of("method", "Express (2-3 days)", "cost", String.format("$%.2f", baseCost * 1.8)),
                    Map.of("method", "Overnight", "cost", String.format("$%.2f", baseCost * 3))
                )
            );
        }

        @Tool(name = "apply_coupon", value = "Apply a coupon code to calculate the discount.")
        public Map<String, Object> applyCoupon(
                @P("subtotal") double subtotal,
                @P("coupon_code") String couponCode) {
            Map<String, Map<String, Object>> coupons = new LinkedHashMap<>();
            coupons.put("SAVE10", Map.of("type", "percentage", "value", 10));
            coupons.put("FLAT20", Map.of("type", "fixed", "value", 20));
            coupons.put("FREESHIP", Map.of("type", "shipping", "value", 0));
            Map<String, Object> coupon = coupons.get(couponCode.toUpperCase());
            if (coupon == null) {
                return Map.of("status", "error", "message", "Invalid coupon: " + couponCode);
            }
            String type = (String) coupon.get("type");
            double value = ((Number) coupon.get("value")).doubleValue();
            double discount;
            if ("percentage".equals(type)) {
                discount = subtotal * value / 100.0;
            } else if ("fixed".equals(type)) {
                discount = Math.min(value, subtotal);
            } else {
                discount = 0;
            }
            return Map.of(
                "status", "success",
                "coupon", couponCode,
                "discount", String.format("$%.2f", discount),
                "final_price", String.format("$%.2f", subtotal - discount)
            );
        }
    }

    public static void main(String[] args) {
        Agent agent = GoogleADKAgent.builder()
            .name("shopping_assistant")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a helpful shopping assistant. Help users find products, "
                + "check availability, calculate shipping, and apply coupons. "
                + "Always check inventory before recommending products. "
                + "Present information in a clear, organized format.")
            .tools(new ShopTools())
            .build();

        AgentResult result = Agentspan.run(agent,
            "I'm looking for electronics. Show me what you have, check if they're "
            + "in stock, and calculate shipping to San Francisco. I have coupon code SAVE10.");
        result.printResult();

        Agentspan.shutdown();
    }
}
