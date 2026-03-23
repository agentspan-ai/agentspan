# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Credentials — GitHub CLI (gh) with automatic credential injection.

Demonstrates:
    - cli_allowed_commands=["gh"] gives the agent a run_command tool
    - credentials=["GH_TOKEN"] auto-injects the token into the tool env
    - The agent calls `gh` commands directly — no subprocess boilerplate needed

Setup (one-time, via CLI):
    agentspan login
    agentspan credentials set --name GH_TOKEN

Requirements:
    - Agentspan server running at AGENTSPAN_SERVER_URL
    - AGENTSPAN_LLM_MODEL set (or defaults to openai/gpt-5.4)
    - `gh` CLI installed (https://cli.github.com)
    - GH_TOKEN stored via `agentspan credentials set`
"""

from agentspan.agents import Agent, AgentRuntime
from settings import settings

agent = Agent(
    name="github_cli_agent",
    model=settings.llm_model,
    cli_allowed_commands=["gh"],
    credentials=["GH_TOKEN"],
    instructions=(
        "You are a GitHub assistant that uses the `gh` CLI tool. "
        "GH_TOKEN is already set in the environment — gh will use it automatically. "
        "Use --json for structured output when listing repos, issues, or PRs. "
        "Always confirm with the user before creating issues or PRs."
    ),
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            agent,
            "List the 5 most recently updated repos for the 'agentspan'",
        )
        result.print_result()
