# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Agent Handoff — transferring control between specialized agents.

Demonstrates:
    - Explicit handoff from a triage agent to a specialist
    - Using state flags to control which agent is active
    - Each specialist has its own focused prompt and tools
    - Practical use case: customer service triage → billing / technical / general routing

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


class State(TypedDict):
    user_message: str
    category: str
    response: str


def triage(state: State) -> State:
    """Classify the user message and decide which specialist should handle it."""
    response = llm.invoke([
        SystemMessage(
            content=(
                "Classify the customer message into exactly one category. "
                "Respond with a single word: billing, technical, or general."
            )
        ),
        HumanMessage(content=state["user_message"]),
    ])
    return {"category": response.content.strip().lower()}


def billing_agent(state: State) -> State:
    response = llm.invoke([
        SystemMessage(
            content=(
                "You are a billing specialist. Answer the customer's billing question "
                "professionally and helpfully. Keep it under 3 sentences."
            )
        ),
        HumanMessage(content=state["user_message"]),
    ])
    return {"response": f"[Billing Agent] {response.content.strip()}"}


def technical_agent(state: State) -> State:
    response = llm.invoke([
        SystemMessage(
            content=(
                "You are a technical support specialist. Troubleshoot the issue step by step. "
                "Provide clear, actionable guidance in under 4 sentences."
            )
        ),
        HumanMessage(content=state["user_message"]),
    ])
    return {"response": f"[Technical Support] {response.content.strip()}"}


def general_agent(state: State) -> State:
    response = llm.invoke([
        SystemMessage(
            content=(
                "You are a friendly general customer service agent. "
                "Help the customer with their question warmly and concisely."
            )
        ),
        HumanMessage(content=state["user_message"]),
    ])
    return {"response": f"[General Support] {response.content.strip()}"}


def route_to_specialist(state: State) -> str:
    category = state.get("category", "general")
    if "billing" in category:
        return "billing"
    if "technical" in category or "tech" in category:
        return "technical"
    return "general"


builder = StateGraph(State)
builder.add_node("triage", triage)
builder.add_node("billing", billing_agent)
builder.add_node("technical", technical_agent)
builder.add_node("general", general_agent)

builder.add_edge(START, "triage")
builder.add_conditional_edges(
    "triage",
    route_to_specialist,
    {"billing": "billing", "technical": "technical", "general": "general"},
)
builder.add_edge("billing", END)
builder.add_edge("technical", END)
builder.add_edge("general", END)

graph = builder.compile(name="agent_handoff")

if __name__ == "__main__":
    queries = [
        "I was charged twice for my subscription last month.",
        "My app keeps crashing after the latest update.",
        "What are your business hours?",
    ]
    with AgentRuntime() as runtime:
        for query in queries:
            print(f"\nQuery: {query}")
            result = runtime.run(graph, query)
            print(f"Status: {result.status}")
            result.print_result()
            print("-" * 60)

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langgraph.26_agent_handoff
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
