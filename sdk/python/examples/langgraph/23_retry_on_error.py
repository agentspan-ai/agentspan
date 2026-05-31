# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Retry on Error — automatic retry logic with exponential back-off.

Demonstrates:
    - Using node retry policies via add_node(..., retry=RetryPolicy(...))
    - Handling transient failures gracefully
    - Tracking retry attempts in state
    - Practical use case: calling an unreliable external API with retries

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import random
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.types import RetryPolicy
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

_call_count = 0


class State(TypedDict):
    query: str
    attempts: int
    result: str


def unreliable_api_call(state: State) -> State:
    """Simulates an external API that fails 50% of the time on first two calls."""
    global _call_count
    _call_count += 1
    attempt = state.get("attempts", 0) + 1

    if _call_count <= 2 and random.random() < 0.7:
        raise ConnectionError(f"Simulated transient network error on attempt {attempt}")

    # Succeed on this attempt
    response = llm.invoke([
        SystemMessage(content="Answer the question concisely."),
        HumanMessage(content=state["query"]),
    ])
    return {"attempts": attempt, "result": response.content.strip()}


def format_output(state: State) -> State:
    return {
        "result": f"[Succeeded after {state.get('attempts', 1)} attempt(s)]\n{state['result']}"
    }


builder = StateGraph(State)
builder.add_node(
    "api_call",
    unreliable_api_call,
    retry=RetryPolicy(max_attempts=5, initial_interval=0.1, backoff_factor=2.0),
)
builder.add_node("format", format_output)
builder.add_edge(START, "api_call")
builder.add_edge("api_call", "format")
builder.add_edge("format", END)

graph = builder.compile(name="retry_agent")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(graph, "What is the speed of light in meters per second?")
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langgraph.23_retry_on_error
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
