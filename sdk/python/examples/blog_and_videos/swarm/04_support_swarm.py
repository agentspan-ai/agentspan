"""Support Swarm — peer-to-peer agent transfers via auto-generated tools.

A front-line support agent triages customer requests and transfers
to specialists. Specialists can transfer to each other — not just
back to the front-line. Peer-to-peer, not top-down.

Setup:
    pip install agentspan
    agentspan server start

    python 05_support_swarm.py
"""

from agentspan.agents import Agent, AgentRuntime, Strategy, tool
from agentspan.agents.handoff import OnTextMention


# ── Tools ────────────────────────────────────────────────────────────

@tool
def lookup_order(order_id: str) -> dict:
    """Look up order details and status."""
    return {
        "order_id": order_id,
        "status": "delivered",
        "delivered_date": "2026-04-10",
        "item": "Wireless Headphones (Model WH-1000)",
        "amount": 249.99,
        "payment_method": "Visa ending 4242",
    }


@tool
def check_refund_eligibility(order_id: str) -> dict:
    """Check if an order is eligible for a refund."""
    return {
        "order_id": order_id,
        "eligible": True,
        "reason": "Within 30-day return window",
        "refund_amount": 249.99,
        "refund_method": "Original payment method (Visa ending 4242)",
        "processing_time": "3-5 business days",
    }


@tool
def process_refund(order_id: str, amount: float, reason: str) -> dict:
    """Process a refund for an order."""
    return {
        "order_id": order_id,
        "refund_id": "RF-88431",
        "amount": amount,
        "status": "processed",
        "eta": "3-5 business days",
    }


@tool
def check_warranty(order_id: str) -> dict:
    """Check warranty status for a product."""
    return {
        "order_id": order_id,
        "warranty_status": "active",
        "warranty_expiry": "2027-04-10",
        "coverage": "Manufacturing defects, battery failure",
        "claim_options": ["replacement", "repair"],
    }


@tool
def create_warranty_claim(order_id: str, issue: str) -> dict:
    """Create a warranty claim."""
    return {
        "order_id": order_id,
        "claim_id": "WC-55102",
        "issue": issue,
        "status": "created",
        "next_step": "Customer will receive a prepaid shipping label via email within 24 hours",
    }


# ── Specialist Agents ────────────────────────────────────────────────

refund_specialist = Agent(
    name="refund_specialist",
    model="openai/gpt-4o",
    instructions=(
        "You are a refund specialist. Handle refund requests.\n\n"
        "1. Use check_refund_eligibility to verify the order qualifies.\n"
        "2. If eligible, use process_refund to issue the refund.\n"
        "3. Confirm the refund amount, method, and timeline to the customer.\n\n"
        "If the customer's issue is actually a product defect (not a return), "
        "transfer to tech_support — they handle warranty claims.\n\n"
        "Be empathetic. Keep it concise."
    ),
    tools=[check_refund_eligibility, process_refund],
)

tech_support = Agent(
    name="tech_support",
    model="openai/gpt-4o",
    instructions=(
        "You are technical support. Handle product issues and warranty claims.\n\n"
        "1. Use check_warranty to verify warranty status.\n"
        "2. If under warranty, use create_warranty_claim.\n"
        "3. Explain next steps to the customer.\n\n"
        "If the customer just wants their money back (not a replacement/repair), "
        "transfer to refund_specialist.\n\n"
        "Be helpful and clear about the options."
    ),
    tools=[check_warranty, create_warranty_claim],
)

# ── Front-line Support (Swarm) ──────────────────────────────────────

support = Agent(
    name="support",
    model="openai/gpt-4o",
    instructions=(
        "You are front-line customer support. Triage the request.\n\n"
        "- If the customer wants a refund or return, transfer to refund_specialist.\n"
        "- If the customer has a product issue or defect, transfer to tech_support.\n\n"
        "Use the transfer tools to hand off. Do NOT try to handle refunds "
        "or technical issues yourself."
    ),
    agents=[refund_specialist, tech_support],
    strategy=Strategy.SWARM,
    tools=[lookup_order],
    handoffs=[
        OnTextMention(text="refund", target="refund_specialist"),
        OnTextMention(text="defect", target="tech_support"),
    ],
    max_turns=5,
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            support,
            "I bought wireless headphones (order ORD-7821) last week and "
            "the left ear cup stopped working after 3 days. I want my money back.",
        )
        result.print_result()
