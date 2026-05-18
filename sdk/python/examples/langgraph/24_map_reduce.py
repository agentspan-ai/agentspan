# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Map-Reduce — fan-out to parallel workers then aggregate results.

Demonstrates:
    - Sending operator for fan-out (parallel list accumulation)
    - Processing multiple items concurrently via Send API
    - Reducing parallel results into a single final answer
    - Practical use case: analyzing multiple documents simultaneously

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import operator
from typing import TypedDict, List, Annotated

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


# ── State definitions ─────────────────────────────────────────────────────────

class OverallState(TypedDict):
    topic: str
    documents: List[str]
    summaries: Annotated[List[str], operator.add]  # accumulate via fan-out
    final_report: str


class DocumentState(TypedDict):
    document: str
    topic: str
    summaries: Annotated[List[str], operator.add]


# ── Nodes ──────────────────────────────────────────────────────────────────────

def generate_documents(state: OverallState) -> OverallState:
    """Generate 3 short document snippets about the topic."""
    response = llm.invoke([
        SystemMessage(
            content=(
                "Generate 3 short text snippets (each 2-3 sentences) about the given topic. "
                "Format as a numbered list:\n1. ...\n2. ...\n3. ..."
            )
        ),
        HumanMessage(content=f"Topic: {state['topic']}"),
    ])
    lines = [l.strip() for l in response.content.strip().split("\n") if l.strip()]
    docs = [l.lstrip("0123456789. ") for l in lines if l[0].isdigit()][:3]
    return {"documents": docs or [response.content.strip()]}


def fan_out(state: OverallState):
    """Send each document to a parallel worker."""
    return [
        Send("summarize_doc", {"document": doc, "topic": state["topic"], "summaries": []})
        for doc in state["documents"]
    ]


def summarize_doc(state: DocumentState) -> dict:
    """Summarize a single document."""
    response = llm.invoke([
        SystemMessage(content="Summarize this text in one concise sentence."),
        HumanMessage(content=f"Topic: {state['topic']}\n\nText: {state['document']}"),
    ])
    return {"summaries": [response.content.strip()]}


def reduce_summaries(state: OverallState) -> OverallState:
    """Combine all summaries into a final report."""
    bullet_points = "\n".join(f"• {s}" for s in state["summaries"])
    response = llm.invoke([
        SystemMessage(
            content=(
                "You are a report writer. Given the topic and a list of summaries, "
                "write a cohesive 2-3 sentence final report."
            )
        ),
        HumanMessage(
            content=f"Topic: {state['topic']}\n\nSummaries:\n{bullet_points}"
        ),
    ])
    return {"final_report": response.content.strip()}


# ── Graph ──────────────────────────────────────────────────────────────────────

builder = StateGraph(OverallState)
builder.add_node("generate_documents", generate_documents)
builder.add_node("summarize_doc", summarize_doc)
builder.add_node("reduce", reduce_summaries)

builder.add_edge(START, "generate_documents")
builder.add_conditional_edges("generate_documents", fan_out, ["summarize_doc"])
builder.add_edge("summarize_doc", "reduce")
builder.add_edge("reduce", END)

graph = builder.compile(name="map_reduce_agent")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(graph, "renewable energy breakthroughs in 2024")
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langgraph.24_map_reduce
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
