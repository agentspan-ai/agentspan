# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Persistent Memory — cross-session state via checkpointing.

Demonstrates:
    - MemorySaver for in-process cross-turn state (simulates database-backed persistence)
    - Configuring thread_id to maintain separate conversation histories per user
    - The graph accumulates conversation turns across multiple runtime.run() calls
    - Practical use case: multi-turn chatbot that remembers earlier exchanges

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from typing import TypedDict, List

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


class State(TypedDict):
    messages: List[dict]
    user_name: str


def chat(state: State) -> State:
    messages = state.get("messages", [])
    lc_messages = [SystemMessage(content="You are a helpful assistant. Remember context from earlier in this conversation.")]
    for m in messages:
        if m.get("role") == "user":
            lc_messages.append(HumanMessage(content=m["content"]))
        elif m.get("role") == "assistant":
            lc_messages.append(AIMessage(content=m["content"]))
    response = llm.invoke(lc_messages)
    new_messages = list(messages) + [{"role": "assistant", "content": response.content}]
    return {"messages": new_messages}


builder = StateGraph(State)
builder.add_node("chat", chat)
builder.add_edge(START, "chat")
builder.add_edge("chat", END)

checkpointer = MemorySaver()
graph = builder.compile(name="persistent_memory_chatbot", checkpointer=checkpointer)

if __name__ == "__main__":
    # Each turn runs as a Conductor workflow. The graph (chat node with LLM)
    # is compiled into prep/LLM_CHAT_COMPLETE/finish tasks.
    # session_id provides per-user isolation on the server side.
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.langgraph.27_persistent_memory
        runtime.deploy(graph)
        runtime.serve(graph)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # print("=== Alice's conversation ===")
        # for msg in ["Hi, my name is Alice!", "What's my name?", "What did I just tell you?"]:
        # result = runtime.run(graph, msg, session_id="alice")
        # print(f"Alice: {msg}")
        # result.print_result()
        # print()

        # print("=== Bob's conversation (separate session) ===")
        # for msg in ["I'm Bob. I love hiking.", "What hobby did I mention?"]:
        # result = runtime.run(graph, msg, session_id="bob")
        # print(f"Bob:  {msg}")
        # result.print_result()
        # print()
