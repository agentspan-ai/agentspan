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
 * Example Adk 15 — Global Instruction
 *
 * <p>Java port of <code>sdk/python/examples/adk/15_global_instruction.py</code>.
 *
 * <p>Demonstrates: ADK's native {@code globalInstruction} for system-wide
 * context. Native {@link LlmAgent} accepts a separate
 * {@code globalInstruction(...)} alongside the per-agent {@code instruction}.
 */
public class Example15GlobalInstruction {

    @Schema(description = "Look up product information.")
    public static Map<String, Object> getProductInfo(
            @Schema(name = "product_name", description = "Product name") String productName) {
        Map<String, Map<String, Object>> products = new LinkedHashMap<>();
        products.put("widget pro", Map.of(
            "name", "Widget Pro", "price", 49.99, "category", "electronics",
            "in_stock", true, "rating", 4.7));
        products.put("gadget max", Map.of(
            "name", "Gadget Max", "price", 89.99, "category", "electronics",
            "in_stock", false, "rating", 4.2));
        products.put("smart lamp", Map.of(
            "name", "Smart Lamp", "price", 34.99, "category", "home",
            "in_stock", true, "rating", 4.5));
        return products.getOrDefault(productName.toLowerCase(),
            Map.of("error", "Product '" + productName + "' not found"));
    }

    @Schema(description = "Get store hours for a location.")
    public static Map<String, Object> getStoreHours(
            @Schema(name = "location", description = "Store location") String location) {
        Map<String, Map<String, Object>> stores = new LinkedHashMap<>();
        stores.put("downtown", Map.of("hours", "9 AM - 9 PM", "open_today", true));
        stores.put("mall", Map.of("hours", "10 AM - 8 PM", "open_today", true));
        return stores.getOrDefault(location.toLowerCase(),
            Map.of("error", "Location '" + location + "' not found"));
    }

    public static void main(String[] args) {
        String globalInstruction =
            "You work for TechStore, a premium electronics retailer. "
            + "Always be professional and mention our satisfaction guarantee. "
            + "Current promotion: 15% off all electronics this week.";

        String perAgentInstruction =
            "You are a store assistant. Help customers find products, "
            + "check availability, and provide store hours. "
            + "Always mention the current promotion when discussing electronics.";

        LlmAgent supportAgent = LlmAgent.builder()
            .name("store_assistant")
            .description("In-store assistant for TechStore that finds products and looks up store hours.")
            .model(Settings.LLM_MODEL)
            .globalInstruction(globalInstruction)
            .instruction(perAgentInstruction)
            .tools(
                FunctionTool.create(Example15GlobalInstruction.class, "getProductInfo"),
                FunctionTool.create(Example15GlobalInstruction.class, "getStoreHours"))
            .build();

        AgentResult result = Agentspan.run(supportAgent,
            "I'm looking for the Widget Pro. Is it in stock? Also, what are the downtown store hours?");
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
