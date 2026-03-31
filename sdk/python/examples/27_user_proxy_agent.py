# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""UserProxyAgent — human stand-in for interactive conversations.

Demonstrates ``UserProxyAgent`` which acts as a human proxy in
multi-agent conversations.  When it's the proxy's turn, the workflow
pauses for real human input.

Modes:
    - ALWAYS: always pause for human input
    - TERMINATE: pause only when conversation would end
    - NEVER: auto-respond (useful for testing)

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

import time

from agentspan.agents import Agent, AgentRuntime, Strategy
from settings import settings
from agentspan.agents.ext import UserProxyAgent

# ── Human proxy ──────────────────────────────────────────────────────

human = UserProxyAgent(
    name="human",
    human_input_mode="ALWAYS",
)

# ── AI assistant ─────────────────────────────────────────────────────

assistant = Agent(
    name="assistant",
    model=settings.llm_model,
    instructions=(
        "You are a helpful coding assistant. Help the user write Python code. "
        "Ask clarifying questions when needed."
    ),
)

# ── Round-robin conversation: human and assistant take turns ─────────

conversation = Agent(
    name="pair_programming",
    model=settings.llm_model,
    agents=[human, assistant],
    strategy=Strategy.ROUND_ROBIN,
    max_turns=4,  # 2 exchanges (human, assistant, human, assistant)
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.27_user_proxy_agent
        runtime.deploy(conversation)
        runtime.serve(conversation)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # # Start async to interact with human tasks
        # handle = runtime.start(
        #     conversation,
        #     "Let's write a Python function to sort a list of dictionaries by a key.",
        # )
        # print(f"Conversation started: {handle.execution_id}")

        # # Simulate human responses
        # human_messages = [
        #     "The function should accept a list of dicts and a key name. "
        #     "It should handle missing keys gracefully.",
        #     "Looks good! Can you add type hints and a docstring?",
        # ]

        # for i, msg in enumerate(human_messages):
        #     # Wait for human task
        #     for _ in range(30):
        #         status = handle.get_status()
        #         if status.is_waiting or status.is_complete:
        #             break
        #         time.sleep(1)

        #     if status.is_complete:
        #         break

        #     if status.is_waiting:
        #         print(f"\n[Human turn {i + 1}]: {msg}")
        #         handle.respond({"message": msg})

        # # Wait for completion
        # for _ in range(30):
        #     status = handle.get_status()
        #     if status.is_complete:
        #         print(f"\nFinal conversation:\n{status.output}")
        #         break
        #     time.sleep(1)

