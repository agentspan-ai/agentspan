# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Persistent Memory — cross-session state via checkpointing.

Demonstrates:
    - MemorySaver for in-process cross-turn state (simulates database-backed persistence)
    - Configuring thread_id to maintain separate conversation histories per user
    - The graph accumulates conversation turns across multiple runtime.run() calls
    - Practical use case: multi-turn chatbot that remembers earlier exchanges

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
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
    with AgentRuntime() as runtime:
        print("=== Alice's conversation ===")
        for msg in ["Hi, my name is Alice!", "What's my name?", "What did I just tell you?"]:
            result = runtime.run(graph, msg, session_id="alice")
            print(f"Alice: {msg}")
            result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langgraph.27_persistent_memory
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)

            print()

        print("=== Bob's conversation (separate session) ===")
        for msg in ["I'm Bob. I love hiking.", "What hobby did I mention?"]:
            result = runtime.run(graph, msg, session_id="bob")
            print(f"Bob:  {msg}")
            result.print_result()
            print()
