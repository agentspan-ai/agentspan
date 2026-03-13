#!/usr/bin/env python3

# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Supply Chain — Multi-agent supply chain management.

Mirrors the supply-chain ADK sample. A coordinator delegates to
inventory, logistics, and demand forecasting specialists.
"""

from google.adk.agents import Agent

from agentspan.agents import AgentRuntime

from settings import settings


def main():
    # ── Inventory tools ───────────────────────────────────────────

    def get_inventory_levels(warehouse: str) -> dict:
        """Get current inventory levels at a warehouse."""
        warehouses = {
            "west": {
                "warehouse": "West Coast",
                "items": [
                    {"sku": "WIDGET-A", "quantity": 5000, "reorder_point": 2000},
                    {"sku": "WIDGET-B", "quantity": 1200, "reorder_point": 1500},
                    {"sku": "GADGET-X", "quantity": 800, "reorder_point": 500},
                ],
            },
            "east": {
                "warehouse": "East Coast",
                "items": [
                    {"sku": "WIDGET-A", "quantity": 3200, "reorder_point": 2000},
                    {"sku": "WIDGET-B", "quantity": 4500, "reorder_point": 1500},
                    {"sku": "GADGET-X", "quantity": 200, "reorder_point": 500},
                ],
            },
        }
        return warehouses.get(warehouse.lower(), {"error": f"Warehouse '{warehouse}' not found"})

    def check_supplier_status(sku: str) -> dict:
        """Check supplier availability and lead times."""
        suppliers = {
            "WIDGET-A": {"supplier": "WidgetCorp", "lead_time_days": 14, "min_order": 1000, "unit_cost": 2.50},
            "WIDGET-B": {"supplier": "WidgetCorp", "lead_time_days": 21, "min_order": 500, "unit_cost": 4.75},
            "GADGET-X": {"supplier": "GadgetWorks", "lead_time_days": 30, "min_order": 200, "unit_cost": 12.00},
        }
        return suppliers.get(sku.upper(), {"error": f"No supplier for SKU {sku}"})

    # ── Logistics tools ───────────────────────────────────────────

    def get_shipping_routes(origin: str, destination: str) -> dict:
        """Get available shipping routes between warehouses."""
        return {
            "origin": origin,
            "destination": destination,
            "routes": [
                {"method": "Ground", "transit_days": 5, "cost_per_unit": 0.50},
                {"method": "Rail", "transit_days": 3, "cost_per_unit": 0.75},
                {"method": "Air", "transit_days": 1, "cost_per_unit": 2.00},
            ],
        }

    def get_pending_shipments() -> dict:
        """Get all pending shipments in the system."""
        return {
            "shipments": [
                {"id": "SHP-001", "sku": "WIDGET-A", "qty": 2000, "status": "in_transit", "eta": "2025-04-18"},
                {"id": "SHP-002", "sku": "GADGET-X", "qty": 500, "status": "processing", "eta": "2025-05-01"},
            ],
        }

    # ── Demand tools ──────────────────────────────────────────────

    def get_demand_forecast(sku: str, weeks_ahead: int = 4) -> dict:
        """Get demand forecast for a SKU."""
        forecasts = {
            "WIDGET-A": {"weekly_demand": 800, "trend": "increasing", "confidence": 0.85},
            "WIDGET-B": {"weekly_demand": 300, "trend": "stable", "confidence": 0.90},
            "GADGET-X": {"weekly_demand": 150, "trend": "decreasing", "confidence": 0.75},
        }
        data = forecasts.get(sku.upper(), {"weekly_demand": 0, "trend": "unknown"})
        data["total_forecast"] = data.get("weekly_demand", 0) * weeks_ahead
        return {"sku": sku, "weeks_ahead": weeks_ahead, **data}

    # ── Sub-agents ────────────────────────────────────────────────

    inventory_agent = Agent(
        name="inventory_manager",
        model=settings.llm_model,
        description="Manages inventory levels and supplier relationships.",
        instruction="Check inventory levels and supplier status. Flag items below reorder points.",
        tools=[get_inventory_levels, check_supplier_status],
    )

    logistics_agent = Agent(
        name="logistics_coordinator",
        model=settings.llm_model,
        description="Handles shipping routes and shipment tracking.",
        instruction="Find optimal shipping routes and track pending shipments.",
        tools=[get_shipping_routes, get_pending_shipments],
    )

    demand_agent = Agent(
        name="demand_planner",
        model=settings.llm_model,
        description="Forecasts product demand.",
        instruction="Analyze demand forecasts and identify trends.",
        tools=[get_demand_forecast],
    )

    coordinator = Agent(
        name="supply_chain_coordinator",
        model=settings.llm_model,
        instruction=(
            "You are a supply chain coordinator. Analyze inventory, logistics, and demand. "
            "Identify items that need restocking, recommend optimal shipping, and provide "
            "an action plan. Delegate to the appropriate specialist."
        ),
        sub_agents=[inventory_agent, logistics_agent, demand_agent],
    )

    with AgentRuntime() as runtime:
        result = runtime.run(
            coordinator,
            "Give me a full supply chain status report. Check both warehouses, "
            "identify any items below reorder points, and recommend restocking actions.",
        )
        print(f"Status: {result.status}")
        print(f"Output: {result.output}")


if __name__ == "__main__":
    main()
