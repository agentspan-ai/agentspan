#!/usr/bin/env python3

# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Callbacks — before_tool_callback and after_tool_callback for tool interception.

Mirrors the pattern from Google ADK samples (customer-service).
Callbacks can validate tool inputs, modify outputs, or short-circuit execution.

NOTE: ADK callbacks (before_tool_callback, after_tool_callback, before_model_callback,
after_model_callback) are Python-side hooks that run within the ADK framework.
When compiled to Conductor workflows, these callbacks are serialized but may not
execute server-side. This example demonstrates the ADK API pattern.
"""

from google.adk.agents import Agent

from agentspan.agents import AgentRuntime

from settings import settings


def main():
    # Tools
    def lookup_customer(customer_id: str) -> dict:
        """Look up customer information by ID."""
        customers = {
            "C001": {"name": "Alice Smith", "tier": "gold", "balance": 1500.00},
            "C002": {"name": "Bob Jones", "tier": "silver", "balance": 320.50},
            "C003": {"name": "Carol White", "tier": "bronze", "balance": 50.00},
        }
        customer = customers.get(customer_id.upper())
        if customer:
            return {"found": True, "customer_id": customer_id, **customer}
        return {"found": False, "error": f"Customer {customer_id} not found"}

    def apply_discount(customer_id: str, discount_percent: float) -> dict:
        """Apply a discount to a customer's account."""
        if discount_percent > 50:
            return {"error": "Discount cannot exceed 50%"}
        return {
            "status": "success",
            "customer_id": customer_id,
            "discount_applied": f"{discount_percent}%",
            "message": f"Applied {discount_percent}% discount to {customer_id}",
        }

    def check_order_status(order_id: str) -> dict:
        """Check the status of an order."""
        orders = {
            "ORD-1001": {"status": "shipped", "tracking": "TRK-98765", "eta": "2025-04-20"},
            "ORD-1002": {"status": "processing", "tracking": None, "eta": "2025-04-25"},
        }
        return orders.get(order_id.upper(), {"error": f"Order {order_id} not found"})

    agent = Agent(
        name="customer_service_agent",
        model=settings.llm_model,
        instruction=(
            "You are a helpful customer service agent. "
            "Use the available tools to look up customer information, "
            "check order status, and apply discounts when requested. "
            "Always verify the customer exists before applying discounts."
        ),
        tools=[lookup_customer, apply_discount, check_order_status],
    )

    with AgentRuntime() as runtime:
        result = runtime.run(
        agent,
        "Look up customer C001 and check if order ORD-1001 has shipped. "
        "If the customer is gold tier, apply a 10% discount.",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.adk.14_callbacks
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)



if __name__ == "__main__":
    main()
