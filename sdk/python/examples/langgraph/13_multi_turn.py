# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Multi-Turn Conversation — MemorySaver + session_id for continuity.

Demonstrates:
    - Using MemorySaver checkpointer for persistent conversation history
    - Passing session_id to runtime.run for scoped memory
    - How different session IDs maintain separate conversation threads
    - A practical use case: interview preparation assistant

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
checkpointer = MemorySaver()

graph = create_agent(
    llm,
    tools=[],
    checkpointer=checkpointer,
    system_prompt=(
        "You are an interview preparation coach. "
        "Remember what the user tells you about their background, skills, and target role. "
        "Build on previous messages to give increasingly personalized advice."
    ),
    name="interview_coach",
)

if __name__ == "__main__":
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

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langgraph.13_multi_turn
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
