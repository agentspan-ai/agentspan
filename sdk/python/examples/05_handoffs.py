# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Handoffs — agent delegating to sub-agents.

Demonstrates the handoff strategy where the parent agent's LLM decides
which sub-agent to delegate to. Sub-agents appear as callable tools.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import Agent, AgentRuntime, Strategy, tool
from settings import settings


# ── Sub-agent tools ─────────────────────────────────────────────────

@tool
def check_balance(account_id: str) -> dict:
    """Check the balance of a bank account."""
    return {"account_id": account_id, "balance": 5432.10, "currency": "USD"}


@tool
def lookup_order(order_id: str) -> dict:
    """Look up the status of an order."""
    return {"order_id": order_id, "status": "shipped", "eta": "2 days"}


@tool
def get_pricing(product: str) -> dict:
    """Get pricing information for a product."""
    return {"product": product, "price": 99.99, "discount": "10% off"}


# ── Specialist agents ───────────────────────────────────────────────

billing_agent = Agent(
    name="billing",
    model=settings.llm_model,
    instructions="You handle billing questions: balances, payments, invoices.",
    tools=[check_balance],
)

technical_agent = Agent(
    name="technical",
    model=settings.llm_model,
    instructions="You handle technical questions: order status, shipping, returns.",
    tools=[lookup_order],
)

sales_agent = Agent(
    name="sales",
    model=settings.llm_model,
    instructions="You handle sales questions: pricing, products, promotions.",
    tools=[get_pricing],
)

# ── Orchestrator with handoffs ──────────────────────────────────────

support = Agent(
    name="support",
    model=settings.llm_model,
    instructions="Route customer requests to the right specialist: billing, technical, or sales.",
    agents=[billing_agent, technical_agent, sales_agent],
    strategy=Strategy.HANDOFF,
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(support, "What's the balance on account ACC-123?")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(support)
        # CLI alternative:
        # agentspan deploy --package examples.05_handoffs
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(support)

