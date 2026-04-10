# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Credentials — Google ADK agent with credential injection.

Demonstrates:
    - runtime.run(adk_agent, credentials=["GITHUB_TOKEN"]) for Google ADK
    - Same pattern as other frameworks — credentials resolved from server
      and injected into os.environ before agent execution

Setup (one-time):
    agentspan credentials set GITHUB_TOKEN <your-github-token>
Requirements:
    - Agentspan server running at AGENTSPAN_SERVER_URL
    - AGENTSPAN_LLM_MODEL set (or defaults to openai/gpt-5.4)
    - GITHUB_TOKEN stored via `agentspan credentials set`
    - google-adk installed: pip install google-adk
"""

import os

from agentspan.agents import AgentRuntime


def create_adk_agent():
    """Create a Google ADK agent with a credential-aware tool."""
    from google.adk import Agent
    from google.adk.tools import FunctionTool

    def check_github_auth() -> str:
        """Check if GitHub authentication is available."""
        token = os.environ.get("GITHUB_TOKEN", "")
        if token:
            return f"GitHub token is set (starts with {token[:4]}...)"
        return "GitHub token is NOT set"

    agent = Agent(
        name="github_checker",
        model="gemini-2.5-flash",
        instruction="You check GitHub authentication status.",
        tools=[FunctionTool(check_github_auth)],
    )
    return agent


if __name__ == "__main__":
    agent = create_adk_agent()

    with AgentRuntime() as runtime:
        result = runtime.run(
            agent,
            "Is GitHub authentication available?",
            credentials=["GITHUB_TOKEN"],
        )
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.16k_credentials_google_adk
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)

