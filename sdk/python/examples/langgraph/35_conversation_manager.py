# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Conversation Manager — multi-turn conversation with session_id.

Demonstrates:
    - Using session_id to maintain sliding-window conversation history
    - Agentspan runtime handles session state server-side
    - A practical use case: long-running chatbot that handles context gracefully

    NOTE: Context window management (summarization of old messages) is handled
          server-side by Agentspan's session infrastructure. No local MemorySaver needed.

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain_openai import ChatOpenAI
from agentspan.agents.langchain import create_agent
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# Session-based memory is handled by Agentspan's session_id parameter — no local state needed
graph = create_agent(
    llm,
    tools=[],
    system_prompt="You are a helpful, friendly assistant. Remember context from earlier in the conversation.",
    name="conversation_manager",
)

if __name__ == "__main__":
    turns = [
        "Hi! I'm learning Python. Where should I start?",
        "What's the difference between a list and a tuple?",
        "Can you give me a quick example of a dictionary?",
        "How does exception handling work?",
        "What is a decorator in Python?",
    ]

    SESSION_ID = "python-learner-session"

    with AgentRuntime() as runtime:
        for turn in turns:
            result = runtime.run(graph, turn, session_id=SESSION_ID)
            print(f"You: {turn}")
            result.print_result()
            print()
