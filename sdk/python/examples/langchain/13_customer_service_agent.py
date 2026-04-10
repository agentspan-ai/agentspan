# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Customer Service Agent — order lookup, FAQ, and escalation handling.

Demonstrates:
    - Domain-specific tools (order status, FAQ, escalation)
    - System prompt that defines service persona and constraints
    - Realistic customer service workflow

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime


@tool
def lookup_order(order_id: str) -> str:
    """Look up the status and details of a customer order.

    Args:
        order_id: The order ID (e.g., 'ORD-12345').
    """
    orders = {
        "ORD-12345": "Status: Shipped. Carrier: FedEx. Tracking: 9612345. Expected delivery: 2 days.",
        "ORD-67890": "Status: Processing. Payment confirmed. Estimated ship date: tomorrow.",
        "ORD-11111": "Status: Delivered. Delivered on 2025-03-15 at 2:34 PM. Signed by: J. Smith.",
        "ORD-99999": "Status: Cancelled. Refund of $49.99 issued on 2025-03-10.",
    }
    return orders.get(order_id.upper(), f"Order '{order_id}' not found. Please verify the order ID.")


@tool
def search_faq(question: str) -> str:
    """Search the FAQ knowledge base for answers to common questions.

    Args:
        question: The customer's question or keyword.
    """
    faq = {
        "return": "Returns are accepted within 30 days of delivery. Items must be unused and in original packaging. Start a return at returns.example.com.",
        "refund": "Refunds are processed within 5-7 business days after we receive the returned item.",
        "shipping": "Standard shipping: 3-5 days ($4.99). Express: 1-2 days ($12.99). Free standard shipping on orders over $50.",
        "cancel": "Orders can be cancelled within 1 hour of placement. After that, please wait for delivery and then initiate a return.",
        "warranty": "All products carry a 1-year manufacturer warranty. Extended warranty plans are available for electronics.",
    }
    for key, answer in faq.items():
        if key in question.lower():
            return answer
    return "No FAQ entry matched your question. A support representative will follow up within 24 hours."


@tool
def create_support_ticket(issue: str, priority: str = "normal") -> str:
    """Create a support ticket for issues requiring human review.

    Args:
        issue: Description of the customer's issue.
        priority: Ticket priority — 'low', 'normal', or 'high'.
    """
    import random
    ticket_id = f"TKT-{random.randint(10000, 99999)}"
    return (
        f"Support ticket {ticket_id} created (priority: {priority}). "
        f"A representative will contact you within "
        f"{'4 hours' if priority == 'high' else '24 hours'}. "
        f"Issue: {issue[:100]}"
    )


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [lookup_order, search_faq, create_support_ticket]

graph = create_agent(
    llm,
    tools=tools,
    name="customer_service_agent",
    system_prompt=(
        "You are Alex, a friendly and professional customer service agent for ShopEasy. "
        "Always greet the customer warmly. Use tools to look up orders and answer questions. "
        "If you cannot resolve the issue, escalate by creating a support ticket. "
        "Keep responses concise and empathetic."
    ),
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "Hi, I ordered something 5 days ago. My order ID is ORD-12345. Where is my package?",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.13_customer_service_agent
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
