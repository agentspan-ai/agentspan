# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Swarm with Tools — sub-agents have their own domain tools.

Extends the basic swarm pattern (example 17) by giving each specialist
its own tools. The swarm transfer mechanism works alongside the tools:
the LLM can call domain tools AND transfer tools in the same turn.

Flow:
    1. Front-line support triages the request
    2. Calls transfer_to_billing_specialist or transfer_to_order_specialist
    3. Specialist uses its domain tool (check_balance / lookup_order)
    4. Specialist responds with the result

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

from agentspan.agents import Agent, AgentRuntime, Strategy, tool
from agentspan.agents.handoff import OnTextMention
from settings import settings


# ── Domain tools ────────────────────────────────────────────────────

@tool
def check_balance(account_id: str) -> dict:
    """Check the balance of a bank account."""
    return {"account_id": account_id, "balance": 5432.10, "currency": "USD"}


@tool
def lookup_order(order_id: str) -> dict:
    """Look up the status of an order."""
    return {"order_id": order_id, "status": "shipped", "eta": "2 days"}


# ── Specialist agents with tools ────────────────────────────────────

billing_specialist = Agent(
    name="billing_specialist",
    model=settings.llm_model,
    instructions=(
        "You are a billing specialist. Use the check_balance tool to look up "
        "account balances. Include the balance amount in your response."
    ),
    tools=[check_balance],
)

order_specialist = Agent(
    name="order_specialist",
    model=settings.llm_model,
    instructions=(
        "You are an order specialist. Use the lookup_order tool to check "
        "order status. Include the shipping status and ETA in your response."
    ),
    tools=[lookup_order],
)

# ── Front-line support with swarm handoffs ──────────────────────────

support = Agent(
    name="support",
    model=settings.llm_model,
    instructions=(
        "You are front-line customer support. Triage customer requests. "
        "Transfer to billing_specialist for account/payment questions, "
        "order_specialist for shipping/order questions."
    ),
    agents=[billing_specialist, order_specialist],
    strategy=Strategy.SWARM,
    handoffs=[
        OnTextMention(text="billing", target="billing_specialist"),
        OnTextMention(text="order", target="order_specialist"),
    ],
    max_turns=3,
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.64_swarm_with_tools
        runtime.deploy(support)
        runtime.serve(support)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # # ── Scenario 1: Billing question → billing specialist uses check_balance
        # print("=" * 60)
        # print("  Scenario 1: Billing question (swarm → billing + tool)")
        # print("=" * 60)
        # result = runtime.run(support, "What's the balance on account ACC-456?")
        # result.print_result()

        # output = str(result.output)
        # if "5432" in output:
        #     print("[OK] Billing specialist used check_balance tool")
        # else:
        #     print("[WARN] Expected balance amount in output")

        # # ── Scenario 2: Order question → order specialist uses lookup_order
        # print("\n" + "=" * 60)
        # print("  Scenario 2: Order question (swarm → order + tool)")
        # print("=" * 60)
        # result2 = runtime.run(support, "Where is my order ORD-789?")
        # result2.print_result()

        # output2 = str(result2.output)
        # if "shipped" in output2.lower():
        #     print("[OK] Order specialist used lookup_order tool")
        # else:
        #     print("[WARN] Expected shipping status in output")

