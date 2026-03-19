# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Memory — multi-turn conversation via session_id.

Demonstrates:
    - Using session_id to maintain conversation state across multiple turns
    - How the agent remembers context from earlier messages
    - Agentspan runtime handles session state server-side (no local checkpointer needed)

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
    name="memory_agent",
)

if __name__ == "__main__":
    # Use a fixed session_id so the agent remembers across turns
    SESSION_ID = "user-session-001"

    with AgentRuntime() as runtime:
        print("=== Turn 1: Introduce a name ===")
        result1 = runtime.run(
            graph,
            "My name is Alice. Please remember that.",
            session_id=SESSION_ID,
        )
        result1.print_result()

        print("\n=== Turn 2: Ask the agent to recall ===")
        result2 = runtime.run(
            graph,
            "What is my name?",
            session_id=SESSION_ID,
        )
        result2.print_result()

        print("\n=== Turn 3: Continue the conversation ===")
        result3 = runtime.run(
            graph,
            "Give me a fun fact about the name Alice.",
            session_id=SESSION_ID,
        )
        result3.print_result()
