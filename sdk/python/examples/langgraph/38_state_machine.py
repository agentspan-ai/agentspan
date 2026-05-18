# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""State Machine — order processing workflow as an explicit state machine.

Demonstrates:
    - Modeling a real-world process as a formal state machine
    - Each node transitions the entity to the next legal state
    - Status tracking in state with timestamps
    - Practical use case: e-commerce order processing pipeline

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import datetime
from typing import TypedDict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


class StatusLog(TypedDict):
    status: str
    timestamp: str
    note: str


class OrderState(TypedDict):
    order_id: str
    items: List[str]
    customer: str
    current_status: str
    status_history: List[StatusLog]
    shipping_address: str
    tracking_number: str
    summary: str


def _log(state: OrderState, status: str, note: str) -> dict:
    history = list(state.get("status_history", []))
    history.append({
        "status": status,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "note": note,
    })
    return {"current_status": status, "status_history": history}


def validate_order(state: OrderState) -> OrderState:
    items = state.get("items", [])
    if not items or not state.get("customer"):
        return {**_log(state, "VALIDATION_FAILED", "Missing items or customer"), "tracking_number": ""}
    return _log(state, "VALIDATED", f"Order contains {len(items)} item(s)")


def payment_processing(state: OrderState) -> OrderState:
    # Simulate payment check via LLM (would be a real payment gateway call)
    response = llm.invoke([
        SystemMessage(content="Simulate a payment approval. Respond with APPROVED or DECLINED."),
        HumanMessage(content=f"Customer: {state['customer']}, Items: {state['items']}"),
    ])
    if "DECLINED" in response.content.upper():
        return _log(state, "PAYMENT_FAILED", "Payment declined")
    return _log(state, "PAYMENT_APPROVED", "Payment processed successfully")


def prepare_shipment(state: OrderState) -> OrderState:
    tracking = f"TRK{hash(state['order_id']) % 10_000_000:07d}"
    return {
        **_log(state, "PREPARING_SHIPMENT", f"Assigned tracking: {tracking}"),
        "tracking_number": tracking,
    }


def ship_order(state: OrderState) -> OrderState:
    return _log(state, "SHIPPED", f"Package dispatched to {state.get('shipping_address', 'customer address')}")


def deliver_order(state: OrderState) -> OrderState:
    return _log(state, "DELIVERED", "Package delivered successfully")


def generate_summary(state: OrderState) -> OrderState:
    history_text = "\n".join(
        f"  [{e['timestamp']}] {e['status']}: {e['note']}"
        for e in state.get("status_history", [])
    )
    summary = (
        f"Order {state['order_id']} — Final Status: {state['current_status']}\n"
        f"Customer: {state['customer']}\n"
        f"Items: {', '.join(state.get('items', []))}\n"
        f"Tracking: {state.get('tracking_number', 'N/A')}\n\n"
        f"Status History:\n{history_text}"
    )
    return {"summary": summary}


def route_after_validation(state: OrderState) -> str:
    return "payment" if state["current_status"] == "VALIDATED" else "done"


def route_after_payment(state: OrderState) -> str:
    return "prepare" if state["current_status"] == "PAYMENT_APPROVED" else "done"


builder = StateGraph(OrderState)
builder.add_node("validate", validate_order)
builder.add_node("payment", payment_processing)
builder.add_node("prepare", prepare_shipment)
builder.add_node("ship", ship_order)
builder.add_node("deliver", deliver_order)
builder.add_node("summarize", generate_summary)

builder.add_edge(START, "validate")
builder.add_conditional_edges("validate", route_after_validation, {"payment": "payment", "done": "summarize"})
builder.add_conditional_edges("payment", route_after_payment, {"prepare": "prepare", "done": "summarize"})
builder.add_edge("prepare", "ship")
builder.add_edge("ship", "deliver")
builder.add_edge("deliver", "summarize")
builder.add_edge("summarize", END)

graph = builder.compile(name="order_state_machine")

if __name__ == "__main__":
    initial_state = {
        "order_id": "ORD-2025-001",
        "items": ["Widget A", "Gadget B"],
        "customer": "Alice Johnson",
        "current_status": "pending",
        "status_history": [],
        "shipping_address": "123 Main St, Springfield",
        "tracking_number": "",
        "summary": "",
    }
    with AgentRuntime() as runtime:
        result = runtime.run(graph, str(initial_state))
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langgraph.38_state_machine
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
