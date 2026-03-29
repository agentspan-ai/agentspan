# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Conditional Routing — StateGraph with add_conditional_edges.

Demonstrates:
    - Using add_conditional_edges to branch based on state content
    - A sentiment classifier that routes to positive, negative, or neutral handlers
    - Multiple terminal nodes converging to END

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from typing import TypedDict, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


class State(TypedDict):
    text: str
    sentiment: str
    response: str


def classify_sentiment(state: State) -> State:
    """Classify the sentiment of the input text."""
    response = llm.invoke([
        SystemMessage(
            content="Classify the sentiment of the text as exactly one word: "
                    "'positive', 'negative', or 'neutral'. Return only that word."
        ),
        HumanMessage(content=state["text"]),
    ])
    sentiment = response.content.strip().lower()
    if sentiment not in ("positive", "negative", "neutral"):
        sentiment = "neutral"
    return {"sentiment": sentiment}


def route_sentiment(state: State) -> Literal["positive", "negative", "neutral"]:
    """Route to the correct handler based on classified sentiment."""
    return state["sentiment"]


def handle_positive(state: State) -> State:
    """Craft an enthusiastic reply for positive sentiment."""
    response = llm.invoke([
        SystemMessage(content="The user expressed something positive. Respond warmly and encouragingly."),
        HumanMessage(content=state["text"]),
    ])
    return {"response": response.content}


def handle_negative(state: State) -> State:
    """Craft an empathetic reply for negative sentiment."""
    response = llm.invoke([
        SystemMessage(content="The user expressed something negative. Respond with empathy and offer support."),
        HumanMessage(content=state["text"]),
    ])
    return {"response": response.content}


def handle_neutral(state: State) -> State:
    """Craft an informative reply for neutral sentiment."""
    response = llm.invoke([
        SystemMessage(content="The user expressed something neutral. Respond helpfully and informatively."),
        HumanMessage(content=state["text"]),
    ])
    return {"response": response.content}


builder = StateGraph(State)
builder.add_node("classify", classify_sentiment)
builder.add_node("positive", handle_positive)
builder.add_node("negative", handle_negative)
builder.add_node("neutral", handle_neutral)

builder.add_edge(START, "classify")
builder.add_conditional_edges(
    "classify",
    route_sentiment,
    {"positive": "positive", "negative": "negative", "neutral": "neutral"},
)
builder.add_edge("positive", END)
builder.add_edge("negative", END)
builder.add_edge("neutral", END)

graph = builder.compile(name="sentiment_router")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.langgraph.06_conditional_routing
        runtime.deploy(graph)
        runtime.serve(graph)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(graph, "I just got promoted at work and I'm thrilled!")
        # print(f"Status: {result.status}")
        # result.print_result()
