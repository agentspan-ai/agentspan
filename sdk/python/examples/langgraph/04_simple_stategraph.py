# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Simple StateGraph — custom query → process → answer pipeline.

Demonstrates:
    - Defining a TypedDict state schema
    - Building a StateGraph with multiple sequential nodes
    - Connecting nodes with add_edge
    - Compiling and naming the graph

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
    query: str
    refined_query: str
    answer: str


def validate_query(state: State) -> State:
    """Ensure the query is not empty and trim whitespace."""
    query = state.get("query", "").strip()
    if not query:
        query = "What can you help me with?"
    return {"query": query, "refined_query": "", "answer": ""}


def refine_query(state: State) -> State:
    """Rewrite the query to be more precise using the LLM."""
    response = llm.invoke([
        SystemMessage(content="Rewrite the user query to be more specific and clear. Return only the rewritten query."),
        HumanMessage(content=state["query"]),
    ])
    return {"refined_query": response.content.strip()}


def generate_answer(state: State) -> State:
    """Generate a comprehensive answer to the refined query."""
    response = llm.invoke([
        SystemMessage(content="You are a knowledgeable assistant. Answer the question clearly and concisely."),
        HumanMessage(content=state["refined_query"] or state["query"]),
    ])
    return {"answer": response.content.strip()}


# Build the graph
builder = StateGraph(State)
builder.add_node("validate", validate_query)
builder.add_node("refine", refine_query)
builder.add_node("answer", generate_answer)

builder.add_edge(START, "validate")
builder.add_edge("validate", "refine")
builder.add_edge("refine", "answer")
builder.add_edge("answer", END)

graph = builder.compile(name="query_pipeline")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(graph, "Tell me about Python")
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langgraph.04_simple_stategraph
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
