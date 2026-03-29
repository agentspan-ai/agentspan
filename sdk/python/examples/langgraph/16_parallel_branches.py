# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Parallel Branches — StateGraph with two concurrent paths that merge.

Demonstrates:
    - Fan-out from a single node to two parallel branches
    - Using Annotated list reducers to safely merge messages
    - Fan-in merge node that combines results from both branches
    - Practical use case: parallel pros/cons analysis

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import operator
from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


class State(TypedDict):
    topic: str
    pros: str
    cons: str
    # Annotated with operator.add so both branches can append messages safely
    branch_outputs: Annotated[list, operator.add]
    final_summary: str


def analyze_pros(state: State) -> State:
    """Analyze the advantages/pros of the topic."""
    response = llm.invoke([
        SystemMessage(content="List 3 clear advantages or pros. Be concise and specific."),
        HumanMessage(content=f"Topic: {state['topic']}"),
    ])
    return {
        "pros": response.content,
        "branch_outputs": [f"PROS:\n{response.content}"],
    }


def analyze_cons(state: State) -> State:
    """Analyze the disadvantages/cons of the topic."""
    response = llm.invoke([
        SystemMessage(content="List 3 clear disadvantages or cons. Be concise and specific."),
        HumanMessage(content=f"Topic: {state['topic']}"),
    ])
    return {
        "cons": response.content,
        "branch_outputs": [f"CONS:\n{response.content}"],
    }


def merge_and_summarize(state: State) -> State:
    """Merge results from both branches and write a balanced conclusion."""
    combined = "\n\n".join(state["branch_outputs"])
    response = llm.invoke([
        SystemMessage(
            content=(
                "You have received a pros and cons analysis. "
                "Write a balanced, one-paragraph conclusion with a clear recommendation."
            )
        ),
        HumanMessage(content=f"Topic: {state['topic']}\n\n{combined}"),
    ])
    return {"final_summary": response.content}


builder = StateGraph(State)
builder.add_node("pros", analyze_pros)
builder.add_node("cons", analyze_cons)
builder.add_node("merge", merge_and_summarize)

# Fan-out: both branches run in parallel from START
builder.add_edge(START, "pros")
builder.add_edge(START, "cons")

# Fan-in: both branches feed into merge
builder.add_edge("pros", "merge")
builder.add_edge("cons", "merge")
builder.add_edge("merge", END)

graph = builder.compile(name="parallel_analysis")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.langgraph.16_parallel_branches
        runtime.deploy(graph)
        runtime.serve(graph)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(graph, "remote work for software engineers")
        # print(f"Status: {result.status}")
        # result.print_result()
