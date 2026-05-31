# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Google ADK Agent with Multiple Specialized Tools — complex tool orchestration.

Demonstrates:
    - Multiple tools working together for a complex task
    - Tools with various parameter types and return structures
    - Detailed docstrings that ADK uses for tool schema generation
    - Best practice: dict returns with "status" field

Requirements:
    - pip install google-adk
    - Conductor server with Google Gemini LLM integration configured
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=google_gemini/gemini-2.0-flash as environment variable
"""

from typing import List

from google.adk.agents import Agent

from agentspan.agents import AgentRuntime

from settings import settings


def search_products(query: str, category: str = "all", max_results: int = 5) -> dict:
    """Search the product catalog.

    Args:
        query: Search query string.
        category: Product category filter — "electronics", "books", "clothing", or "all".
        max_results: Maximum number of results to return.

    Returns:
        Dictionary with search results including product details and prices.
    """
    products = [
        {"id": "P001", "name": "Wireless Mouse", "category": "electronics", "price": 29.99, "rating": 4.5},
        {"id": "P002", "name": "Python Cookbook", "category": "books", "price": 45.00, "rating": 4.8},
        {"id": "P003", "name": "USB-C Hub", "category": "electronics", "price": 39.99, "rating": 4.2},
        {"id": "P004", "name": "Ergonomic Keyboard", "category": "electronics", "price": 89.99, "rating": 4.7},
        {"id": "P005", "name": "Clean Code", "category": "books", "price": 35.00, "rating": 4.9},
    ]
    query_lower = query.lower()
    results = [
        p for p in products
        if query_lower in p["name"].lower()
        or (category != "all" and p["category"] == category)
    ]
    return {"status": "success", "results": results[:max_results], "total": len(results)}


def check_inventory(product_id: str) -> dict:
    """Check inventory availability for a product.

    Args:
        product_id: The product ID to check.

    Returns:
        Dictionary with availability status and stock count.
    """
    inventory = {
        "P001": {"in_stock": True, "quantity": 150, "warehouse": "West"},
        "P002": {"in_stock": True, "quantity": 45, "warehouse": "East"},
        "P003": {"in_stock": False, "quantity": 0, "restock_date": "2025-04-01"},
        "P004": {"in_stock": True, "quantity": 8, "warehouse": "West"},
        "P005": {"in_stock": True, "quantity": 200, "warehouse": "East"},
    }
    item = inventory.get(product_id)
    if item:
        return {"status": "success", "product_id": product_id, **item}
    return {"status": "error", "message": f"Product {product_id} not found"}


def calculate_shipping(product_ids: List[str], destination: str) -> dict:
    """Calculate shipping cost for a list of products.

    Args:
        product_ids: List of product IDs to ship.
        destination: Shipping destination (city or zip code).

    Returns:
        Dictionary with shipping options and costs.
    """
    base_cost = len(product_ids) * 5.99
    return {
        "status": "success",
        "destination": destination,
        "items": len(product_ids),
        "options": [
            {"method": "Standard (5-7 days)", "cost": f"${base_cost:.2f}"},
            {"method": "Express (2-3 days)", "cost": f"${base_cost * 1.8:.2f}"},
            {"method": "Overnight", "cost": f"${base_cost * 3:.2f}"},
        ],
    }


def apply_coupon(subtotal: float, coupon_code: str) -> dict:
    """Apply a coupon code to calculate the discount.

    Args:
        subtotal: The order subtotal before discount.
        coupon_code: The coupon code to apply.

    Returns:
        Dictionary with discount details and final price.
    """
    coupons = {
        "SAVE10": {"type": "percentage", "value": 10},
        "FLAT20": {"type": "fixed", "value": 20},
        "FREESHIP": {"type": "shipping", "value": 0},
    }
    coupon = coupons.get(coupon_code.upper())
    if not coupon:
        return {"status": "error", "message": f"Invalid coupon: {coupon_code}"}

    if coupon["type"] == "percentage":
        discount = subtotal * coupon["value"] / 100
    elif coupon["type"] == "fixed":
        discount = min(coupon["value"], subtotal)
    else:
        discount = 0

    return {
        "status": "success",
        "coupon": coupon_code,
        "discount": f"${discount:.2f}",
        "final_price": f"${subtotal - discount:.2f}",
    }


agent = Agent(
    name="shopping_assistant",
    model=settings.llm_model,
    instruction=(
        "You are a helpful shopping assistant. Help users find products, "
        "check availability, calculate shipping, and apply coupons. "
        "Always check inventory before recommending products. "
        "Present information in a clear, organized format."
    ),
    tools=[search_products, check_inventory, calculate_shipping, apply_coupon],
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
        agent,
        "I'm looking for electronics. Show me what you have, check if they're "
        "in stock, and calculate shipping to San Francisco. I have coupon code SAVE10.",
        )
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.adk.09_multi_tool_agent
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)
