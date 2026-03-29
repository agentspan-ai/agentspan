# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Credentials — OpenAI Agent SDK with credential injection.

Demonstrates:
    - runtime.run(openai_agent, credentials=["GITHUB_TOKEN"]) for OpenAI agents
    - Credentials resolved from server and injected into os.environ
    - OpenAI agent tools can read credentials from os.environ

Setup (one-time):
    agentspan credentials set --name GITHUB_TOKEN

Requirements:
    - Agentspan server running at AGENTSPAN_SERVER_URL
    - AGENTSPAN_LLM_MODEL set (or defaults to openai/gpt-5.4)
    - GITHUB_TOKEN stored via `agentspan credentials set`
    - openai-agents installed: pip install openai-agents
"""

import os

from agentspan.agents import AgentRuntime


def create_openai_agent():
    """Create an OpenAI Agent SDK agent with a credential-aware tool."""
    from agents import Agent, function_tool

    @function_tool
    def check_github_auth() -> str:
        """Check if GitHub authentication is available."""
        token = os.environ.get("GITHUB_TOKEN", "")
        if token:
            return f"GitHub token is set (starts with {token[:4]}...)"
        return "GitHub token is NOT set"

    agent = Agent(
        name="github_checker",
        instructions="You check GitHub authentication status. Use the tool when asked.",
        tools=[check_github_auth],
    )
    return agent


if __name__ == "__main__":
    agent = create_openai_agent()


    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.16j_credentials_openai_sdk
        runtime.deploy(agent)
        runtime.serve(agent)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # # credentials=["GITHUB_TOKEN"] resolves from server credential store
        # # and injects into os.environ for the agent's tools
        # result = runtime.run(
        #     agent,
        #     "Is GitHub authentication available?",
        #     credentials=["GITHUB_TOKEN"],
        # )
        # result.print_result()

