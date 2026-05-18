# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Classify and Route — LLM-based input classification with specialized routing.

Demonstrates:
    - Using an LLM to classify input into a discrete category
    - Conditional edges routing to specialized handler nodes
    - Each handler node is tailored to its domain
    - Practical use case: smart help desk that routes to the right department

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
    input: str
    category: str
    answer: str


def classify(state: State) -> State:
    response = llm.invoke([
        SystemMessage(
            content=(
                "Classify the input into exactly one category. "
                "Categories: science, history, sports, technology, cooking. "
                "Respond with the category name only."
            )
        ),
        HumanMessage(content=state["input"]),
    ])
    return {"category": response.content.strip().lower()}


def answer_science(state: State) -> State:
    response = llm.invoke([
        SystemMessage(content="You are a science expert. Answer precisely with relevant scientific context."),
        HumanMessage(content=state["input"]),
    ])
    return {"answer": f"[Science Expert] {response.content.strip()}"}


def answer_history(state: State) -> State:
    response = llm.invoke([
        SystemMessage(content="You are a history expert. Provide historical context and key dates."),
        HumanMessage(content=state["input"]),
    ])
    return {"answer": f"[History Expert] {response.content.strip()}"}


def answer_sports(state: State) -> State:
    response = llm.invoke([
        SystemMessage(content="You are a sports analyst. Give stats and context when relevant."),
        HumanMessage(content=state["input"]),
    ])
    return {"answer": f"[Sports Analyst] {response.content.strip()}"}


def answer_technology(state: State) -> State:
    response = llm.invoke([
        SystemMessage(content="You are a technology expert. Be clear and technically accurate."),
        HumanMessage(content=state["input"]),
    ])
    return {"answer": f"[Tech Expert] {response.content.strip()}"}


def answer_cooking(state: State) -> State:
    response = llm.invoke([
        SystemMessage(content="You are a professional chef. Give practical, delicious advice."),
        HumanMessage(content=state["input"]),
    ])
    return {"answer": f"[Chef] {response.content.strip()}"}


def route(state: State) -> str:
    cat = state.get("category", "")
    mapping = {
        "science": "science",
        "history": "history",
        "sports": "sports",
        "technology": "technology",
        "cooking": "cooking",
    }
    return mapping.get(cat, "technology")  # default to technology


builder = StateGraph(State)
builder.add_node("classify", classify)
builder.add_node("science", answer_science)
builder.add_node("history", answer_history)
builder.add_node("sports", answer_sports)
builder.add_node("technology", answer_technology)
builder.add_node("cooking", answer_cooking)

builder.add_edge(START, "classify")
builder.add_conditional_edges(
    "classify",
    route,
    {
        "science": "science",
        "history": "history",
        "sports": "sports",
        "technology": "technology",
        "cooking": "cooking",
    },
)
for node in ["science", "history", "sports", "technology", "cooking"]:
    builder.add_edge(node, END)

graph = builder.compile(name="classify_and_route_agent")

if __name__ == "__main__":
    questions = [
        "What causes a solar eclipse?",
        "Who won the FIFA World Cup in 2022?",
        "How do I make a simple pasta carbonara?",
    ]
    with AgentRuntime() as runtime:
        for q in questions:
            print(f"\nQ: {q}")
            result = runtime.run(graph, q)
            result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langgraph.31_classify_and_route
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
