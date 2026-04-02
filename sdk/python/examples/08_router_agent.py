# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Router Agent — LLM-based routing to specialists.

Demonstrates the router strategy where a parent agent routes
to the appropriate sub-agent based on the user's request.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import Agent, AgentRuntime, Strategy
from settings import settings

# ── Specialist agents ───────────────────────────────────────────────

planner = Agent(
    name="planner",
    model=settings.llm_model,
    instructions="You create implementation plans. Break down tasks into clear numbered steps.",
)

coder = Agent(
    name="coder",
    model=settings.llm_model,
    instructions="You write code. Output clean, well-documented Python code.",
)

reviewer = Agent(
    name="reviewer",
    model=settings.llm_model,
    instructions="You review code. Check for bugs, style issues, and suggest improvements.",
)

# ── Router (LLM decides who to use) ────────────────────────────────

team = Agent(
    name="dev_team",
    model=settings.llm_model,
    instructions=(
        "You are the tech lead. Route requests to the right team member: "
        "planner for design/architecture, coder for implementation, "
        "reviewer for code review."
    ),
    agents=[planner, coder, reviewer],
    strategy=Strategy.ROUTER,
    router=planner,  # Required for router strategy
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(team, "Write a Python function to validate email addresses using regex")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(team)
        # CLI alternative:
        # agentspan deploy --package examples.08_router_agent
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(team)

