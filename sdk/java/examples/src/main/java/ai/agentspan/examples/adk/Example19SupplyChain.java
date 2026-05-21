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
import java.util.List;
import java.util.Map;

/**
 * Example Adk 19 — Supply Chain
 *
 * <p>Java port of <code>sdk/python/examples/adk/19_supply_chain.py</code>.
 *
 * <p>Demonstrates: a coordinator delegating to inventory, logistics, and
 * demand forecasting specialists.
 */
public class Example19SupplyChain {

    @Schema(description = "Get current inventory levels at a warehouse.")
    public static Map<String, Object> getInventoryLevels(
            @Schema(name = "warehouse", description = "Warehouse name") String warehouse) {
        Map<String, Map<String, Object>> warehouses = new LinkedHashMap<>();
        warehouses.put("west", Map.of(
            "warehouse", "West Coast",
            "items", List.of(
                Map.of("sku", "WIDGET-A", "quantity", 5000, "reorder_point", 2000),
                Map.of("sku", "WIDGET-B", "quantity", 1200, "reorder_point", 1500),
                Map.of("sku", "GADGET-X", "quantity", 800, "reorder_point", 500)
            )
        ));
        warehouses.put("east", Map.of(
            "warehouse", "East Coast",
            "items", List.of(
                Map.of("sku", "WIDGET-A", "quantity", 3200, "reorder_point", 2000),
                Map.of("sku", "WIDGET-B", "quantity", 4500, "reorder_point", 1500),
                Map.of("sku", "GADGET-X", "quantity", 200, "reorder_point", 500)
            )
        ));
        return warehouses.getOrDefault(warehouse.toLowerCase(),
            Map.of("error", "Warehouse '" + warehouse + "' not found"));
    }

    @Schema(description = "Check supplier availability and lead times.")
    public static Map<String, Object> checkSupplierStatus(
            @Schema(name = "sku", description = "Product SKU") String sku) {
        Map<String, Map<String, Object>> suppliers = new LinkedHashMap<>();
        suppliers.put("WIDGET-A", Map.of("supplier", "WidgetCorp", "lead_time_days", 14, "min_order", 1000, "unit_cost", 2.50));
        suppliers.put("WIDGET-B", Map.of("supplier", "WidgetCorp", "lead_time_days", 21, "min_order", 500, "unit_cost", 4.75));
        suppliers.put("GADGET-X", Map.of("supplier", "GadgetWorks", "lead_time_days", 30, "min_order", 200, "unit_cost", 12.00));
        return suppliers.getOrDefault(sku.toUpperCase(),
            Map.of("error", "No supplier for SKU " + sku));
    }

    @Schema(description = "Get available shipping routes between warehouses.")
    public static Map<String, Object> getShippingRoutes(
            @Schema(name = "origin", description = "Origin location") String origin,
            @Schema(name = "destination", description = "Destination location") String destination) {
        return Map.of(
            "origin", origin,
            "destination", destination,
            "routes", List.of(
                Map.of("method", "Ground", "transit_days", 5, "cost_per_unit", 0.50),
                Map.of("method", "Rail", "transit_days", 3, "cost_per_unit", 0.75),
                Map.of("method", "Air", "transit_days", 1, "cost_per_unit", 2.00)
            )
        );
    }

    @Schema(description = "Get all pending shipments in the system.")
    public static Map<String, Object> getPendingShipments() {
        return Map.of(
            "shipments", List.of(
                Map.of("id", "SHP-001", "sku", "WIDGET-A", "qty", 2000, "status", "in_transit", "eta", "2025-04-18"),
                Map.of("id", "SHP-002", "sku", "GADGET-X", "qty", 500, "status", "processing", "eta", "2025-05-01")
            )
        );
    }

    @Schema(description = "Get demand forecast for a SKU.")
    public static Map<String, Object> getDemandForecast(
            @Schema(name = "sku", description = "Product SKU") String sku,
            @Schema(name = "weeks_ahead", description = "Forecast horizon in weeks") int weeksAhead) {
        Map<String, Map<String, Object>> forecasts = new LinkedHashMap<>();
        forecasts.put("WIDGET-A", Map.of("weekly_demand", 800, "trend", "increasing", "confidence", 0.85));
        forecasts.put("WIDGET-B", Map.of("weekly_demand", 300, "trend", "stable", "confidence", 0.90));
        forecasts.put("GADGET-X", Map.of("weekly_demand", 150, "trend", "decreasing", "confidence", 0.75));
        Map<String, Object> data = forecasts.getOrDefault(sku.toUpperCase(),
            Map.of("weekly_demand", 0, "trend", "unknown"));
        int weekly = ((Number) data.getOrDefault("weekly_demand", 0)).intValue();
        int wa = weeksAhead <= 0 ? 4 : weeksAhead;
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("sku", sku);
        result.put("weeks_ahead", wa);
        result.putAll(data);
        result.put("total_forecast", weekly * wa);
        return result;
    }

    public static void main(String[] args) {
        LlmAgent inventoryAgent = LlmAgent.builder()
            .name("inventory_manager")
            .description("Inspects inventory levels and supplier status, flagging items below reorder points.")
            .model(Settings.LLM_MODEL)
            .instruction("Check inventory levels and supplier status. Flag items below reorder points.")
            .tools(
                FunctionTool.create(Example19SupplyChain.class, "getInventoryLevels"),
                FunctionTool.create(Example19SupplyChain.class, "checkSupplierStatus"))
            .build();

        LlmAgent logisticsAgent = LlmAgent.builder()
            .name("logistics_coordinator")
            .description("Finds optimal shipping routes and tracks pending shipments.")
            .model(Settings.LLM_MODEL)
            .instruction("Find optimal shipping routes and track pending shipments.")
            .tools(
                FunctionTool.create(Example19SupplyChain.class, "getShippingRoutes"),
                FunctionTool.create(Example19SupplyChain.class, "getPendingShipments"))
            .build();

        LlmAgent demandAgent = LlmAgent.builder()
            .name("demand_planner")
            .description("Analyzes demand forecasts and identifies SKU-level trends.")
            .model(Settings.LLM_MODEL)
            .instruction("Analyze demand forecasts and identify trends.")
            .tools(FunctionTool.create(Example19SupplyChain.class, "getDemandForecast"))
            .build();

        LlmAgent coordinator = LlmAgent.builder()
            .name("supply_chain_coordinator")
            .description("Coordinates inventory, logistics, and demand specialists for supply-chain reports.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a supply chain coordinator. Analyze inventory, logistics, and demand.
                Identify items that need restocking, recommend optimal shipping, and provide
                an action plan. Delegate to the appropriate specialist.
                """)
            .subAgents(inventoryAgent, logisticsAgent, demandAgent)
            .build();

        AgentResult result = Agentspan.run(coordinator,
            "Give me a full supply chain status report. Check both warehouses, "
            + "identify any items below reorder points, and recommend restocking actions.");
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
