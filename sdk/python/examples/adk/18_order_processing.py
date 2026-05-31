#!/usr/bin/env python3

# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Order Processing — End-to-end order management agent.

Mirrors the order-processing ADK sample. A single agent handles the
complete order lifecycle: search, cart, pricing, and order placement.
"""

from google.adk.agents import Agent

from agentspan.agents import AgentRuntime

from settings import settings


def main():
    def search_catalog(query: str, category: str = "all") -> dict:
        """Search the product catalog."""
        catalog = [
            {"sku": "LAP-001", "name": "ProBook Laptop 15\"", "category": "laptops", "price": 1299.99, "stock": 23},
            {"sku": "LAP-002", "name": "UltraSlim Notebook 13\"", "category": "laptops", "price": 899.99, "stock": 45},
            {"sku": "ACC-001", "name": "Wireless Mouse", "category": "accessories", "price": 29.99, "stock": 200},
            {"sku": "ACC-002", "name": "USB-C Dock", "category": "accessories", "price": 79.99, "stock": 67},
            {"sku": "MON-001", "name": "4K Monitor 27\"", "category": "monitors", "price": 449.99, "stock": 12},
        ]
        results = []
        for item in catalog:
            if category != "all" and item["category"] != category:
                continue
            if query.lower() in item["name"].lower() or query.lower() in item["category"]:
                results.append(item)
        if not results:
            results = [item for item in catalog if category == "all" or item["category"] == category]
        return {"results": results[:5], "total_found": len(results)}

    def check_stock(sku: str) -> dict:
        """Check real-time stock availability for a SKU."""
        stock_data = {
            "LAP-001": {"available": True, "quantity": 23, "warehouse": "West"},
            "LAP-002": {"available": True, "quantity": 45, "warehouse": "East"},
            "ACC-001": {"available": True, "quantity": 200, "warehouse": "Central"},
            "ACC-002": {"available": True, "quantity": 67, "warehouse": "Central"},
            "MON-001": {"available": True, "quantity": 12, "warehouse": "West"},
        }
        return stock_data.get(sku.upper(), {"available": False, "quantity": 0})

    def calculate_total(item_skus: str, shipping_method: str = "standard") -> dict:
        """Calculate order total with tax and shipping. item_skus is a comma-separated list of SKUs."""
        items = [s.strip() for s in item_skus.split(",")]
        prices = {"LAP-001": 1299.99, "LAP-002": 899.99, "ACC-001": 29.99, "ACC-002": 79.99, "MON-001": 449.99}
        shipping_rates = {"standard": 9.99, "express": 24.99, "overnight": 49.99}

        subtotal = sum(prices.get(sku, 0) for sku in items)
        tax = round(subtotal * 0.085, 2)  # 8.5% tax
        shipping = shipping_rates.get(shipping_method, 9.99)
        total = round(subtotal + tax + shipping, 2)

        return {
            "subtotal": subtotal,
            "tax": tax,
            "shipping": shipping,
            "shipping_method": shipping_method,
            "total": total,
        }

    def place_order(item_skus: str, shipping_method: str = "standard", payment_method: str = "credit_card") -> dict:
        """Place an order. item_skus is a comma-separated list of SKUs."""
        items = [s.strip() for s in item_skus.split(",")]
        return {
            "order_id": "ORD-2025-0789",
            "status": "confirmed",
            "items": items,
            "shipping_method": shipping_method,
            "payment_method": payment_method,
            "estimated_delivery": "2025-04-22" if shipping_method == "standard" else "2025-04-18",
        }

    agent = Agent(
        name="order_processor",
        model=settings.llm_model,
        instruction=(
            "You are an order processing assistant for TechMart. "
            "Help customers search products, check availability, calculate totals, and place orders. "
            "Always verify stock before confirming an order. Provide clear pricing breakdowns."
        ),
        tools=[search_catalog, check_stock, calculate_total, place_order],
    )

    with AgentRuntime() as runtime:
        result = runtime.run(
        agent,
        "I need a laptop for work. Show me what's available, check stock for your recommendation, "
        "and calculate the total with express shipping.",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.adk.18_order_processing
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)



if __name__ == "__main__":
    main()
