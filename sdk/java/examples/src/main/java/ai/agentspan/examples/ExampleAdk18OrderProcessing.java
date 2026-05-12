// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.GoogleADKAgent;
import ai.agentspan.model.AgentResult;
import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.Tool;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Example Adk 18 — Order Processing
 *
 * <p>Java port of <code>sdk/python/examples/adk/18_order_processing.py</code>.
 *
 * <p>Demonstrates: a single agent that handles the full order lifecycle:
 * search → check stock → calculate total → place order.
 */
public class ExampleAdk18OrderProcessing {

    static class OrderTools {

        @Tool(name = "search_catalog", value = "Search the product catalog.")
        public Map<String, Object> searchCatalog(
                @P("query") String query,
                @P("category") String category) {
            String cat = category == null || category.isEmpty() ? "all" : category;
            List<Map<String, Object>> catalog = List.of(
                Map.of("sku", "LAP-001", "name", "ProBook Laptop 15\"", "category", "laptops", "price", 1299.99, "stock", 23),
                Map.of("sku", "LAP-002", "name", "UltraSlim Notebook 13\"", "category", "laptops", "price", 899.99, "stock", 45),
                Map.of("sku", "ACC-001", "name", "Wireless Mouse", "category", "accessories", "price", 29.99, "stock", 200),
                Map.of("sku", "ACC-002", "name", "USB-C Dock", "category", "accessories", "price", 79.99, "stock", 67),
                Map.of("sku", "MON-001", "name", "4K Monitor 27\"", "category", "monitors", "price", 449.99, "stock", 12)
            );
            List<Map<String, Object>> results = new ArrayList<>();
            for (Map<String, Object> item : catalog) {
                String itemCat = (String) item.get("category");
                if (!"all".equals(cat) && !itemCat.equals(cat)) {
                    continue;
                }
                String name = ((String) item.get("name")).toLowerCase();
                String q = query.toLowerCase();
                if (name.contains(q) || itemCat.contains(q)) {
                    results.add(item);
                }
            }
            if (results.isEmpty()) {
                for (Map<String, Object> item : catalog) {
                    if ("all".equals(cat) || item.get("category").equals(cat)) {
                        results.add(item);
                    }
                }
            }
            return Map.of(
                "results", results.subList(0, Math.min(5, results.size())),
                "total_found", results.size()
            );
        }

        @Tool(name = "check_stock", value = "Check real-time stock availability for a SKU.")
        public Map<String, Object> checkStock(@P("sku") String sku) {
            Map<String, Map<String, Object>> stockData = new LinkedHashMap<>();
            stockData.put("LAP-001", Map.of("available", true, "quantity", 23, "warehouse", "West"));
            stockData.put("LAP-002", Map.of("available", true, "quantity", 45, "warehouse", "East"));
            stockData.put("ACC-001", Map.of("available", true, "quantity", 200, "warehouse", "Central"));
            stockData.put("ACC-002", Map.of("available", true, "quantity", 67, "warehouse", "Central"));
            stockData.put("MON-001", Map.of("available", true, "quantity", 12, "warehouse", "West"));
            return stockData.getOrDefault(sku.toUpperCase(),
                Map.of("available", false, "quantity", 0));
        }

        @Tool(name = "calculate_total", value = "Calculate order total with tax and shipping. item_skus is a comma-separated list of SKUs.")
        public Map<String, Object> calculateTotal(
                @P("item_skus") String itemSkus,
                @P("shipping_method") String shippingMethod) {
            List<String> items = new ArrayList<>();
            for (String s : itemSkus.split(",")) {
                items.add(s.trim());
            }
            Map<String, Double> prices = new LinkedHashMap<>();
            prices.put("LAP-001", 1299.99);
            prices.put("LAP-002", 899.99);
            prices.put("ACC-001", 29.99);
            prices.put("ACC-002", 79.99);
            prices.put("MON-001", 449.99);
            Map<String, Double> shippingRates = new LinkedHashMap<>();
            shippingRates.put("standard", 9.99);
            shippingRates.put("express", 24.99);
            shippingRates.put("overnight", 49.99);

            double subtotal = 0;
            for (String sku : items) {
                subtotal += prices.getOrDefault(sku, 0.0);
            }
            double tax = Math.round(subtotal * 0.085 * 100.0) / 100.0;
            String method = shippingMethod == null || shippingMethod.isEmpty() ? "standard" : shippingMethod;
            double shipping = shippingRates.getOrDefault(method, 9.99);
            double total = Math.round((subtotal + tax + shipping) * 100.0) / 100.0;
            return Map.of(
                "subtotal", subtotal,
                "tax", tax,
                "shipping", shipping,
                "shipping_method", method,
                "total", total
            );
        }

        @Tool(name = "place_order", value = "Place an order. item_skus is a comma-separated list of SKUs.")
        public Map<String, Object> placeOrder(
                @P("item_skus") String itemSkus,
                @P("shipping_method") String shippingMethod,
                @P("payment_method") String paymentMethod) {
            List<String> items = Arrays.stream(itemSkus.split(",")).map(String::trim).toList();
            String method = shippingMethod == null || shippingMethod.isEmpty() ? "standard" : shippingMethod;
            String pay = paymentMethod == null || paymentMethod.isEmpty() ? "credit_card" : paymentMethod;
            return Map.of(
                "order_id", "ORD-2025-0789",
                "status", "confirmed",
                "items", items,
                "shipping_method", method,
                "payment_method", pay,
                "estimated_delivery", "standard".equals(method) ? "2025-04-22" : "2025-04-18"
            );
        }
    }

    public static void main(String[] args) {
        Agent agent = GoogleADKAgent.builder()
            .name("order_processor")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are an order processing assistant for TechMart. "
                + "Help customers search products, check availability, calculate totals, and place orders. "
                + "Always verify stock before confirming an order. Provide clear pricing breakdowns.")
            .tools(new OrderTools())
            .build();

        AgentResult result = Agentspan.run(agent,
            "I need a laptop for work. Show me what's available, check stock for your recommendation, "
            + "and calculate the total with express shipping.");
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
