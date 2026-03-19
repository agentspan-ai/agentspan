# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Persistent Memory — cross-session state via session_id.

Demonstrates:
    - Using session_id to maintain separate conversation histories per user
    - The graph accumulates conversation turns across multiple runtime.run() calls
    - Agentspan runtime handles session state server-side (no local checkpointer needed)
    - Practical use case: multi-turn chatbot that remembers earlier exchanges

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain_openai import ChatOpenAI
from agentspan.agents.langchain import create_agent
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# Session-based memory is handled by Agentspan's session_id parameter — no local checkpointer needed
graph = create_agent(
    llm,
    tools=[],
    system_prompt="You are a helpful assistant. Remember context from earlier in this conversation.",
    name="persistent_memory_chatbot",
)

if __name__ == "__main__":
    # Two separate users each have isolated history tracked by session_id
    with AgentRuntime() as runtime:
        print("=== Alice's conversation ===")
        for msg in ["Hi, my name is Alice!", "What's my name?", "What did I just tell you?"]:
            result = runtime.run(graph, msg, session_id="alice")
            print(f"Alice: {msg}")
            result.print_result()
            print()

        print("=== Bob's conversation (separate memory) ===")
        for msg in ["I'm Bob. I love hiking.", "What hobby did I mention?"]:
            result = runtime.run(graph, msg, session_id="bob")
            print(f"Bob:  {msg}")
            result.print_result()
            print()
