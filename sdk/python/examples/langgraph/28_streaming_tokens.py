# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Streaming Tokens — streaming intermediate LLM output token by token.

Demonstrates:
    - Using graph.stream() with stream_mode="messages" to receive tokens incrementally
    - Printing partial output as it arrives for a real-time feel
    - How LangGraph exposes AIMessageChunk events during generation
    - Practical use case: streaming a long-form answer to the terminal

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import sys

from langchain_core.messages import HumanMessage, AIMessageChunk, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, streaming=True)


def generate(state: dict) -> dict:
    messages = state.get("messages", [])
    response = llm.invoke(messages)
    return {"messages": messages + [response]}


builder = StateGraph(dict)
builder.add_node("generate", generate)
builder.add_edge(START, "generate")
builder.add_edge("generate", END)
graph = builder.compile(name="streaming_agent")


def stream_to_console(prompt: str):
    """Stream tokens to stdout in real time."""
    input_state = {
        "messages": [
            SystemMessage(content="You are a helpful assistant. Answer thoroughly."),
            HumanMessage(content=prompt),
        ]
    }
    print("Streaming response:\n")
    for event_type, chunk in graph.stream(input_state, stream_mode="messages"):
        if isinstance(chunk, AIMessageChunk) and chunk.content:
            print(chunk.content, end="", flush=True)
    print("\n")


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.langgraph.28_streaming_tokens
        runtime.deploy(graph)
        runtime.serve(graph)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # stream_to_console(
        #     "Explain the concept of gradient descent in machine learning in about 150 words."
        # )
