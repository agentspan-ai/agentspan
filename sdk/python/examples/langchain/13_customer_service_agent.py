# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Customer Service Agent — empathetic customer support with policy tools.

Demonstrates:
    - Customer service persona with empathy guidelines in system prompt
    - Tools for order lookup, return policy, and issue escalation
    - Handling different types of customer inquiries gracefully
    - Practical use case: Tier-1 customer support automation

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain_core.tools import tool
from agentspan.agents.langchain import create_agent
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


# ── Mock order database ───────────────────────────────────────────────────────

ORDERS = {
    "ORD-1001": {"status": "Delivered", "item": "Wireless Headphones", "date": "2025-02-28", "total": 129.99},
    "ORD-1002": {"status": "In Transit", "item": "Mechanical Keyboard", "date": "2025-03-10", "total": 89.00},
    "ORD-1003": {"status": "Processing", "item": "USB-C Hub", "date": "2025-03-15", "total": 45.00},
    "ORD-1004": {"status": "Cancelled", "item": "Gaming Mouse", "date": "2025-03-01", "total": 67.50},
}


@tool
def lookup_order(order_id: str) -> str:
    """Look up the status and details of a customer order.

    Args:
        order_id: The order ID (format: ORD-XXXX).
    """
    order = ORDERS.get(order_id.upper())
    if not order:
        return f"Order {order_id} not found. Please check the order ID and try again."
    return (
        f"Order {order_id}:\n"
        f"  Item:   {order['item']}\n"
        f"  Status: {order['status']}\n"
        f"  Date:   {order['date']}\n"
        f"  Total:  ${order['total']:.2f}"
    )


@tool
def check_return_policy(order_id: str) -> str:
    """Check whether an order is eligible for return or refund.

    Args:
        order_id: The order ID to check return eligibility for.
    """
    order = ORDERS.get(order_id.upper())
    if not order:
        return f"Order {order_id} not found."

    if order["status"] == "Delivered":
        return (
            f"Order {order_id} ({order['item']}) is eligible for return within 30 days of delivery. "
            f"To initiate a return, visit our returns portal or reply here."
        )
    elif order["status"] == "In Transit":
        return f"Order {order_id} is currently in transit. You may request a return once delivered."
    elif order["status"] == "Processing":
        return f"Order {order_id} is still processing. You can cancel it now for a full refund."
    elif order["status"] == "Cancelled":
        return f"Order {order_id} was already cancelled. A full refund should appear within 5-7 business days."
    return "Return eligibility could not be determined. Please contact support."


@tool
def get_shipping_info(carrier: str = "standard") -> str:
    """Get shipping timeframes and carrier information.

    Args:
        carrier: Shipping tier — 'standard', 'express', or 'overnight'.
    """
    shipping = {
        "standard": "Standard shipping: 5-7 business days. Free on orders over $50.",
        "express": "Express shipping: 2-3 business days. $9.99 flat rate.",
        "overnight": "Overnight shipping: Next business day. $24.99 flat rate.",
    }
    return shipping.get(carrier.lower(), "Please contact support for shipping inquiries.")


@tool
def escalate_to_human(issue_summary: str, customer_sentiment: str = "neutral") -> str:
    """Escalate a complex issue to a human agent.

    Args:
        issue_summary: Brief description of the issue to escalate.
        customer_sentiment: Customer emotional state: 'frustrated', 'angry', 'neutral', 'satisfied'.
    """
    priority = "HIGH" if customer_sentiment in ("frustrated", "angry") else "NORMAL"
    return (
        f"[ESCALATION CREATED — Priority: {priority}]\n"
        f"Issue: {issue_summary}\n"
        f"A human agent will contact you within 2 hours (high priority) or 24 hours (normal).\n"
        f"Case reference: ESC-{hash(issue_summary) % 10000:04d}"
    )


CS_SYSTEM = """You are a friendly and empathetic customer service representative for TechShop.
Always:
- Acknowledge the customer's concern before looking up information
- Use the customer's name if provided
- Apologize for any inconvenience in a genuine, non-scripted way
- Offer concrete next steps after resolving the issue
- Escalate if you cannot resolve the issue with available tools
"""

graph = create_agent(
    llm,
    tools=[lookup_order, check_return_policy, get_shipping_info, escalate_to_human],
    name="customer_service_agent",
    system_prompt=CS_SYSTEM,
)

if __name__ == "__main__":
    queries = [
        "Hi, my order ORD-1002 still hasn't arrived. I ordered a week ago!",
        "I want to return my headphones from order ORD-1001. How do I do that?",
        "This is ridiculous! I've been waiting 3 weeks for order ORD-1003 and no one is helping me!",
    ]

    with AgentRuntime() as runtime:
        for query in queries:
            print(f"\nCustomer: {query}")
            result = runtime.run(graph, query)
            result.print_result()
            print("-" * 60)
