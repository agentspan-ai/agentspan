# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Customer Support Router — StateGraph with greet → classify → route → respond.

Demonstrates:
    - Multi-node StateGraph with conditional branching
    - Classifying user intent and routing to specialized handlers
    - Billing, technical, and general support branches

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from typing import TypedDict, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


class State(TypedDict):
    user_message: str
    greeting: str
    category: str
    response: str


def greet(state: State) -> State:
    """Greet the customer warmly before handling their request."""
    return {
        "greeting": (
            "Hello! Thank you for contacting our support team. "
            "I'm here to help you today."
        )
    }


def classify(state: State) -> State:
    """Classify the customer's issue into billing, technical, or general."""
    response = llm.invoke([
        SystemMessage(
            content=(
                "Classify the customer message into exactly one category: "
                "'billing', 'technical', or 'general'. "
                "Return only the single category word."
            )
        ),
        HumanMessage(content=state["user_message"]),
    ])
    category = response.content.strip().lower()
    if category not in ("billing", "technical", "general"):
        category = "general"
    return {"category": category}


def route_category(state: State) -> Literal["billing", "technical", "general"]:
    """Route based on the classified category."""
    return state["category"]


def handle_billing(state: State) -> State:
    """Handle billing-related inquiries."""
    response = llm.invoke([
        SystemMessage(
            content=(
                "You are a billing specialist. The customer has a billing question. "
                "Be empathetic, offer to review their account, and explain payment options clearly."
            )
        ),
        HumanMessage(content=state["user_message"]),
    ])
    return {"response": f"{state['greeting']}\n\n{response.content}"}


def handle_technical(state: State) -> State:
    """Handle technical support inquiries."""
    response = llm.invoke([
        SystemMessage(
            content=(
                "You are a technical support engineer. The customer has a technical issue. "
                "Provide step-by-step troubleshooting guidance. Be clear and concise."
            )
        ),
        HumanMessage(content=state["user_message"]),
    ])
    return {"response": f"{state['greeting']}\n\n{response.content}"}


def handle_general(state: State) -> State:
    """Handle general inquiries."""
    response = llm.invoke([
        SystemMessage(
            content=(
                "You are a helpful customer service agent handling general inquiries. "
                "Be friendly, informative, and direct. Offer additional help at the end."
            )
        ),
        HumanMessage(content=state["user_message"]),
    ])
    return {"response": f"{state['greeting']}\n\n{response.content}"}


builder = StateGraph(State)
builder.add_node("greet", greet)
builder.add_node("classify", classify)
builder.add_node("billing", handle_billing)
builder.add_node("technical", handle_technical)
builder.add_node("general", handle_general)

builder.add_edge(START, "greet")
builder.add_edge("greet", "classify")
builder.add_conditional_edges(
    "classify",
    route_category,
    {"billing": "billing", "technical": "technical", "general": "general"},
)
builder.add_edge("billing", END)
builder.add_edge("technical", END)
builder.add_edge("general", END)

graph = builder.compile(name="customer_support")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
        graph,
        "I was charged twice for my subscription this month and need a refund.",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langgraph.11_customer_support
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
