# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Chat History — maintaining conversation history across multiple turns.

Demonstrates:
    - Passing prior conversation turns via the messages list in input_data
    - Using session_id to maintain separate conversations per user
    - How AgentRuntime maps session_id to LangGraph thread_id
    - Practical use case: persistent multi-turn conversation with context

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from agentspan.agents.langchain import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


@tool
def remember_fact(fact: str) -> str:
    """Store a fact that the user wants to remember."""
    return f"I'll remember that: {fact}"


@tool
def recall_topic(topic: str) -> str:
    """Try to recall what was previously discussed about a topic."""
    return f"Based on our conversation, I recall discussing: {topic}"


graph = create_agent(
    llm,
    tools=[remember_fact, recall_topic],
    name="chat_history_agent",
)

if __name__ == "__main__":
    # Each runtime.run() with the same session_id continues the same conversation
    session = "user-session-001"

    turns = [
        "Hi! My name is Alex and I work in data science.",
        "I'm learning LangGraph for building AI agents.",
        "What's my name and what am I learning about?",
    ]

    with AgentRuntime() as runtime:
        for i, message in enumerate(turns, 1):
            print(f"\n--- Turn {i} ---")
            print(f"User: {message}")
            result = runtime.run(graph, message, session_id=session)
            print(f"Status: {result.status}")
            result.print_result()
