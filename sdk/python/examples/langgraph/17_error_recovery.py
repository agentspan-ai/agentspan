# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Error Recovery — StateGraph with try/except in nodes for graceful degradation.

Demonstrates:
    - Catching exceptions within StateGraph nodes
    - Storing error information in state for downstream handling
    - A fallback node that generates a graceful response on failure
    - Conditional routing based on whether an error occurred

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from typing import TypedDict, Literal, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


class State(TypedDict):
    query: str
    data: Optional[str]
    error: Optional[str]
    response: str


def fetch_data(state: State) -> State:
    """Attempt to fetch data; may fail for certain query patterns."""
    query = state["query"]
    try:
        # Simulate a failure for queries containing 'fail' or 'error'
        if "fail" in query.lower() or "error" in query.lower():
            raise ValueError(f"Simulated fetch failure for query: '{query}'")

        # Simulate successful data fetch
        data = (
            f"Fetched data for '{query}': "
            "Sample dataset with 100 records, avg value 42.5, max 99, min 1."
        )
        return {"data": data, "error": None}

    except Exception as exc:
        # Capture the error in state instead of crashing the graph
        return {"data": None, "error": str(exc)}


def should_recover(state: State) -> Literal["process", "recover"]:
    """Route to recovery path if an error was captured."""
    return "recover" if state.get("error") else "process"


def process_data(state: State) -> State:
    """Process the fetched data with LLM analysis (happy path)."""
    response = llm.invoke([
        SystemMessage(content="You are a data analyst. Summarize the following data in one sentence."),
        HumanMessage(content=state["data"]),
    ])
    return {"response": response.content}


def recover_from_error(state: State) -> State:
    """Generate a helpful error message and suggest alternatives (recovery path)."""
    response = llm.invoke([
        SystemMessage(
            content=(
                "A data fetch error occurred. Apologize briefly, explain what may have gone wrong, "
                "and suggest 2 alternative approaches the user could try. Be concise."
            )
        ),
        HumanMessage(content=f"Error: {state['error']}\nOriginal query: {state['query']}"),
    ])
    return {"response": f"[RECOVERED FROM ERROR]\n{response.content}"}


builder = StateGraph(State)
builder.add_node("fetch", fetch_data)
builder.add_node("process", process_data)
builder.add_node("recover", recover_from_error)

builder.add_edge(START, "fetch")
builder.add_conditional_edges(
    "fetch",
    should_recover,
    {"process": "process", "recover": "recover"},
)
builder.add_edge("process", END)
builder.add_edge("recover", END)

graph = builder.compile(name="error_recovery_agent")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.langgraph.17_error_recovery
        runtime.deploy(graph)
        runtime.serve(graph)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # print("=== Happy path ===")
        # result = runtime.run(graph, "sales data for Q4")
        # print(f"Status: {result.status}")
        # result.print_result()

        # print("\n=== Error recovery path ===")
        # result = runtime.run(graph, "intentionally fail this query")
        # print(f"Status: {result.status}")
        # result.print_result()
