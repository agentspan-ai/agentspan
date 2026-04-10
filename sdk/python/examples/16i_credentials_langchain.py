# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Credentials — LangChain agent with credential injection.

Demonstrates:
    - runtime.run(agent, credentials=["GITHUB_TOKEN"]) for LangChain
    - Same pattern as LangGraph — credentials resolved from server
      and injected into os.environ before the agent runs

Setup (one-time):
    agentspan credentials set GITHUB_TOKEN <your-github-token>
Requirements:
    - Agentspan server running at AGENTSPAN_SERVER_URL
    - AGENTSPAN_LLM_MODEL set (or defaults to openai/gpt-5.4)
    - GITHUB_TOKEN stored via `agentspan credentials set`
    - langchain installed: pip install langchain langchain-openai
"""

import os

from agentspan.agents import AgentRuntime
from settings import settings


def create_langchain_agent():
    """Create a LangChain agent with a tool that uses GITHUB_TOKEN."""
    from langchain.agents import create_agent
    from langchain_core.tools import tool as lc_tool

    @lc_tool
    def check_github_token() -> str:
        """Check if GitHub token is available in the environment."""
        token = os.environ.get("GITHUB_TOKEN", "")
        if token:
            return f"GitHub token available (starts with {token[:4]}...)"
        return "GitHub token is NOT available"

    model_str = settings.llm_model
    # create_agent accepts "provider:model" format (e.g. "openai:gpt-4o")
    if "/" in model_str:
        provider, model = model_str.split("/", 1)
        model_str = f"{provider}:{model}"

    agent = create_agent(
        model_str,
        tools=[check_github_token],
        system_prompt="You are a helpful assistant. Use tools when asked.",
    )
    return agent


if __name__ == "__main__":
    agent = create_langchain_agent()

    with AgentRuntime() as runtime:
        result = runtime.run(
            agent,
            "Check if the GitHub token is set",
            credentials=["GITHUB_TOKEN"],
        )
        result.print_result()

        print('\nStarting another run passing the credentials')

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.16i_credentials_langchain
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)
