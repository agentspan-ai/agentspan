#!/usr/bin/env python3

# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Global Instruction — global_instruction for system-wide context.

Mirrors the pattern from Google ADK samples (data-science, customer-service).
global_instruction provides context shared across all agents, while
instruction is specific to each agent.
"""

from google.adk.agents import Agent

from agentspan.agents import AgentRuntime

from settings import settings


def main():
    def get_product_info(product_name: str) -> dict:
        """Look up product information."""
        products = {
            "widget pro": {
                "name": "Widget Pro",
                "price": 49.99,
                "category": "electronics",
                "in_stock": True,
                "rating": 4.7,
            },
            "gadget max": {
                "name": "Gadget Max",
                "price": 89.99,
                "category": "electronics",
                "in_stock": False,
                "rating": 4.2,
            },
            "smart lamp": {
                "name": "Smart Lamp",
                "price": 34.99,
                "category": "home",
                "in_stock": True,
                "rating": 4.5,
            },
        }
        return products.get(product_name.lower(), {"error": f"Product '{product_name}' not found"})

    def get_store_hours(location: str) -> dict:
        """Get store hours for a location."""
        stores = {
            "downtown": {"hours": "9 AM - 9 PM", "open_today": True},
            "mall": {"hours": "10 AM - 8 PM", "open_today": True},
        }
        return stores.get(location.lower(), {"error": f"Location '{location}' not found"})

    agent = Agent(
        name="store_assistant",
        model=settings.llm_model,
        global_instruction=(
            "You work for TechStore, a premium electronics retailer. "
            "Always be professional and mention our satisfaction guarantee. "
            "Current promotion: 15% off all electronics this week."
        ),
        instruction=(
            "You are a store assistant. Help customers find products, "
            "check availability, and provide store hours. "
            "Always mention the current promotion when discussing electronics."
        ),
        tools=[get_product_info, get_store_hours],
    )

    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.adk.15_global_instruction
        runtime.deploy(agent)
        runtime.serve(agent)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(
        # agent,
        # "I'm looking for the Widget Pro. Is it in stock? Also, what are the downtown store hours?",
        # )
        # print(f"Status: {result.status}")
        # print(f"Output: {result.output}")



if __name__ == "__main__":
    main()
