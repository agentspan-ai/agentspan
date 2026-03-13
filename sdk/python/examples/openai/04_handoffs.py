# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""OpenAI Agent Handoffs — multi-agent orchestration with handoffs.

Demonstrates:
    - Defining specialist agents with handoff capability
    - A triage agent that routes to the correct specialist
    - The Conductor runtime maps OpenAI handoffs to strategy="handoff"
      with sub-agents, compiled into a multi-agent workflow.

Requirements:
    - pip install openai-agents
    - Conductor server with OpenAI LLM integration configured
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

from agents import Agent, function_tool

from agentspan.agents import AgentRuntime

from settings import settings


# ── Specialist tools ──────────────────────────────────────────────────

@function_tool
def check_order_status(order_id: str) -> str:
    """Check the status of a customer order."""
    orders = {
        "ORD-001": "Shipped — arriving tomorrow",
        "ORD-002": "Processing — estimated ship date: Friday",
        "ORD-003": "Delivered on Monday",
    }
    return orders.get(order_id, f"Order {order_id} not found")


@function_tool
def process_refund(order_id: str, reason: str) -> str:
    """Process a refund for an order."""
    return f"Refund initiated for {order_id}. Reason: {reason}. Expect 3-5 business days."


@function_tool
def get_product_info(product_name: str) -> str:
    """Get product information and pricing."""
    products = {
        "laptop pro": "Laptop Pro X1 — $1,299 — 16GB RAM, 512GB SSD, 14\" display",
        "wireless earbuds": "SoundMax Earbuds — $79 — ANC, 24hr battery, Bluetooth 5.3",
        "smart watch": "TimeSync Watch — $249 — GPS, health tracking, 5-day battery",
    }
    return products.get(product_name.lower(), f"Product '{product_name}' not found")


# ── Specialist agents ─────────────────────────────────────────────────

order_agent = Agent(
    name="order_specialist",
    instructions=(
        "You handle order-related inquiries. Use the check_order_status tool "
        "to look up orders. Be professional and concise."
    ),
    model=settings.llm_model,
    tools=[check_order_status],
)

refund_agent = Agent(
    name="refund_specialist",
    instructions=(
        "You handle refund requests. Use the process_refund tool to initiate "
        "refunds. Always confirm the order ID and reason before processing."
    ),
    model=settings.llm_model,
    tools=[process_refund],
)

sales_agent = Agent(
    name="sales_specialist",
    instructions=(
        "You handle product inquiries and sales. Use the get_product_info tool "
        "to look up products. Be enthusiastic but not pushy."
    ),
    model=settings.llm_model,
    tools=[get_product_info],
)

# ── Triage agent with handoffs ───────────────────────────────────────

triage_agent = Agent(
    name="customer_service_triage",
    instructions=(
        "You are a customer service triage agent. Determine the customer's need "
        "and hand off to the appropriate specialist:\n"
        "- Order status inquiries → order_specialist\n"
        "- Refund requests → refund_specialist\n"
        "- Product questions or purchases → sales_specialist\n"
        "Be brief in your initial response before handing off."
    ),
    model=settings.llm_model,
    handoffs=[order_agent, refund_agent, sales_agent],
)

with AgentRuntime() as runtime:
    result = runtime.run(
        triage_agent,
        "I'd like a refund for order ORD-002, the product arrived damaged.",
    )
    result.print_result()
