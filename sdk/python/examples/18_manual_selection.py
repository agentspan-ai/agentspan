# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Manual Selection — human picks which agent speaks next.

Demonstrates ``strategy="manual"`` where the workflow pauses each turn
to let a human select which agent should respond.  The human interacts
via the ``AgentHandle.respond()`` API.

Flow:
    1. Workflow pauses with a HumanTask showing available agents
    2. Human picks an agent (e.g. {"selected": "writer"})
    3. Selected agent responds
    4. Repeat until max_turns

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

import time

from agentspan.agents import Agent, AgentRuntime, Strategy
from settings import settings

writer = Agent(
    name="writer",
    model=settings.llm_model,
    instructions="You are a creative writer. Expand on ideas with vivid prose.",
)

editor = Agent(
    name="editor",
    model=settings.llm_model,
    instructions="You are a strict editor. Improve clarity, fix issues, tighten prose.",
)

fact_checker = Agent(
    name="fact_checker",
    model=settings.llm_model,
    instructions="You verify claims and flag anything inaccurate or unsupported.",
)

# Manual strategy: human picks who speaks each turn
team = Agent(
    name="editorial_team",
    model=settings.llm_model,
    agents=[writer, editor, fact_checker],
    strategy=Strategy.MANUAL,
    max_turns=3,
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.18_manual_selection
        runtime.deploy(team)
        runtime.serve(team)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # # Start async so we can interact with the human tasks
        # handle = runtime.start(
        #     team,
        #     "Write a short paragraph about the history of artificial intelligence.",
        # )
        # print(f"Started workflow: {handle.execution_id}")

        # # In a real app, a UI would show the agent options and the human would pick.
        # # Here we simulate by selecting agents programmatically:
        # selections = ["writer", "editor", "fact_checker"]

        # for i, agent_name in enumerate(selections):
        #     # Wait for the workflow to pause at the HumanTask
        #     for _ in range(30):
        #         status = handle.get_status()
        #         if status.is_waiting:
        #             break
        #         if status.is_complete:
        #             break
        #         time.sleep(1)

        #     if status.is_complete:
        #         print(f"Workflow completed after {i} turns")
        #         break

        #     if status.is_waiting:
        #         print(f"Turn {i + 1}: Selecting '{agent_name}'")
        #         handle.respond({"selected": agent_name})

        # # Wait for final completion
        # for _ in range(30):
        #     status = handle.get_status()
        #     if status.is_complete:
        #         print(f"\nFinal output:\n{status.output}")
        #         break
        #     time.sleep(1)

