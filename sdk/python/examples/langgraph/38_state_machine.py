# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""State Machine — order processing workflow as tools orchestrated by the agent.

Demonstrates:
    - Modelling an order processing pipeline as a sequence of tools
    - Each tool transitions the order to the next legal state
    - Status tracking via state in each tool's return value
    - Practical use case: e-commerce order processing pipeline

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import datetime
import json

from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from agentspan.agents.langchain import create_agent
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


def _timestamp() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


@tool
def validate_order(order_json: str) -> str:
    """Validate an order JSON and return status VALIDATED or VALIDATION_FAILED.

    Args:
        order_json: JSON string with order fields: order_id, items (list), customer.
    """
    try:
        order = json.loads(order_json)
    except json.JSONDecodeError:
        return json.dumps({"status": "VALIDATION_FAILED", "note": "Invalid JSON input", "timestamp": _timestamp()})

    if not order.get("items") or not order.get("customer"):
        return json.dumps({"status": "VALIDATION_FAILED", "note": "Missing items or customer", "timestamp": _timestamp()})

    return json.dumps({
        "status": "VALIDATED",
        "note": f"Order contains {len(order['items'])} item(s)",
        "order_id": order.get("order_id", "UNKNOWN"),
        "timestamp": _timestamp(),
    })


@tool
def process_payment(order_id: str, customer: str, items: str) -> str:
    """Simulate payment processing for an order. Returns PAYMENT_APPROVED or PAYMENT_FAILED.

    Args:
        order_id: The order identifier.
        customer: The customer name.
        items: Comma-separated list of ordered items.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Simulate a payment approval. Respond with APPROVED or DECLINED."),
        ("human", "Customer: {customer}, Items: {items}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"customer": customer, "items": items})

    if "DECLINED" in response.content.upper():
        return json.dumps({"order_id": order_id, "status": "PAYMENT_FAILED", "note": "Payment declined", "timestamp": _timestamp()})
    return json.dumps({"order_id": order_id, "status": "PAYMENT_APPROVED", "note": "Payment processed successfully", "timestamp": _timestamp()})


@tool
def ship_order(order_id: str, shipping_address: str) -> str:
    """Prepare and ship an approved order. Returns tracking number and SHIPPED status.

    Args:
        order_id: The order identifier.
        shipping_address: The delivery address.
    """
    tracking = f"TRK{hash(order_id) % 10_000_000:07d}"
    return json.dumps({
        "order_id": order_id,
        "status": "SHIPPED",
        "tracking_number": tracking,
        "note": f"Package dispatched to {shipping_address}",
        "timestamp": _timestamp(),
    })


@tool
def generate_order_summary(order_id: str, customer: str, items: str, status_history: str) -> str:
    """Generate a human-readable order summary from the processing history.

    Args:
        order_id: The order identifier.
        customer: The customer name.
        items: Comma-separated list of ordered items.
        status_history: JSON array of status log entries.
    """
    try:
        history = json.loads(status_history)
        history_text = "\n".join(
            f"  [{e.get('timestamp', '')}] {e.get('status', '')}: {e.get('note', '')}"
            for e in history
        )
    except (json.JSONDecodeError, TypeError):
        history_text = status_history

    final_status = history[-1].get("status", "UNKNOWN") if isinstance(history, list) and history else "UNKNOWN"
    tracking = next((e.get("tracking_number", "") for e in (history if isinstance(history, list) else []) if e.get("tracking_number")), "N/A")

    return (
        f"Order {order_id} — Final Status: {final_status}\n"
        f"Customer: {customer}\n"
        f"Items: {items}\n"
        f"Tracking: {tracking}\n\n"
        f"Status History:\n{history_text}"
    )


STATE_MACHINE_SYSTEM = """You are an order processing agent.

For each order, run the full processing pipeline:
1. Call validate_order with the order JSON
2. If status is VALIDATED → call process_payment with order_id, customer, and items
3. If status is PAYMENT_APPROVED → call ship_order with order_id and shipping_address
4. Collect all status results into a history list as a JSON array string
5. Call generate_order_summary with order_id, customer, items, and the JSON status history
6. Return the summary to the user

If validation or payment fails, still call generate_order_summary with the history up to that point.
"""

graph = create_agent(
    llm,
    tools=[validate_order, process_payment, ship_order, generate_order_summary],
    name="order_state_machine",
    system_prompt=STATE_MACHINE_SYSTEM,
)

if __name__ == "__main__":
    import json as _json
    initial_order = _json.dumps({
        "order_id": "ORD-2025-001",
        "items": ["Python Book", "Mechanical Keyboard", "USB-C Hub"],
        "customer": "Alice Smith",
        "shipping_address": "123 Main St, San Francisco, CA 94105",
    })

    with AgentRuntime() as runtime:
        result = runtime.run(graph, f"Process this order: {initial_order}")
        print(f"Status: {result.status}")
        result.print_result()
