# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Multi-Turn Conversation — session_id for continuity across turns.

Demonstrates:
    - Using session_id to maintain persistent conversation history
    - How different session IDs maintain separate conversation threads
    - Agentspan runtime handles session state server-side (no local checkpointer needed)
    - A practical use case: interview preparation assistant

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
    system_prompt=(
        "You are an interview preparation coach. "
        "Remember what the user tells you about their background, skills, and target role. "
        "Build on previous messages to give increasingly personalized advice."
    ),
    name="interview_coach",
)

if __name__ == "__main__":
    SESSION_A = "candidate-alice"
    SESSION_B = "candidate-bob"

    with AgentRuntime() as runtime:
        print("=== Alice's session ===")
        r = runtime.run(
            graph,
            "I'm applying for a senior backend engineer role at a fintech startup. "
            "I have 5 years of Python experience.",
            session_id=SESSION_A,
        )
        r.print_result()

        print("\n=== Bob's session (separate memory) ===")
        r = runtime.run(
            graph,
            "I want to become a product manager. I have a marketing background.",
            session_id=SESSION_B,
        )
        r.print_result()

        print("\n=== Alice's session — follow-up (remembers context) ===")
        r = runtime.run(
            graph,
            "What technical topics should I review for my upcoming interviews?",
            session_id=SESSION_A,
        )
        r.print_result()

        print("\n=== Bob's session — follow-up (remembers context) ===")
        r = runtime.run(
            graph,
            "What skills gap should I address first?",
            session_id=SESSION_B,
        )
        r.print_result()
