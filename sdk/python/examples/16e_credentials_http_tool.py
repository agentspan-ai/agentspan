# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Credentials — HTTP tool with server-side credential resolution.

Demonstrates:
    - http_tool() with credentials=["GITHUB_TOKEN"]
    - ${GITHUB_TOKEN} in headers resolved server-side (not in Python)
    - No worker process needed — Conductor makes the HTTP call directly

The ${NAME} syntax in headers tells the server to substitute the credential
value from the store at execution time. The plaintext value never appears
in the workflow definition.

Setup (one-time):
    agentspan credentials set --name GITHUB_TOKEN

Requirements:
    - Agentspan server running at AGENTSPAN_SERVER_URL
    - AGENTSPAN_LLM_MODEL set (or defaults to openai/gpt-5.4)
    - GITHUB_TOKEN stored via `agentspan credentials set`
"""

from agentspan.agents import Agent, AgentRuntime
from agentspan.agents.tool import http_tool
from settings import settings


# HTTP tool with credential-bearing headers.
# ${GITHUB_TOKEN} is resolved server-side from the credential store.
list_repos = http_tool(
    name="list_github_repos",
    description="List public GitHub repositories for a user. Returns JSON array with name, url, and stars.",
    url="https://api.github.com/users/agentspan/repos?per_page=5&sort=updated",
    headers={
        "Authorization": "Bearer ${GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    },
    credentials=["GITHUB_TOKEN"],
)

agent = Agent(
    name="github_http_agent",
    model=settings.llm_model,
    tools=[list_repos],
    instructions="You list GitHub repos using the list_github_repos tool. Summarize the results.",
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(agent, "List the repos for agentspan")
        result.print_result()
