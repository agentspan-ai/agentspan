# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Credentials — Framework passthrough with credential injection.

Demonstrates:
    - runtime.run(graph, credentials=["GITHUB_TOKEN"]) for LangGraph agents
    - Credentials resolved from the server and injected into os.environ
      before the graph executes
    - Works the same for LangChain, OpenAI Agent SDK, and Google ADK

This pattern is used when you run a foreign framework agent (LangGraph,
LangChain, OpenAI, ADK) through Agentspan and need tools inside the
graph to access credentials from the credential store.

Setup (one-time):
    agentspan credentials set GITHUB_TOKEN <your-github-token>
Requirements:
    - Agentspan server running at AGENTSPAN_SERVER_URL
    - AGENTSPAN_LLM_MODEL set (or defaults to openai/gpt-5.4)
    - GITHUB_TOKEN stored via `agentspan credentials set`
    - langgraph installed: pip install langgraph langchain-openai
"""

import os

from agentspan.agents import AgentRuntime
from settings import settings


def create_langgraph_agent():
    """Create a simple LangGraph agent with a tool that uses GITHUB_TOKEN."""
    from langchain_core.tools import tool as lc_tool
    from langchain_openai import ChatOpenAI
    from langgraph.prebuilt import create_react_agent

    @lc_tool
    def check_github_auth() -> str:
        """Check if GitHub authentication is available."""
        token = os.environ.get("GITHUB_TOKEN", "")
        if token:
            return f"GitHub token is set (starts with {token[:4]}...)"
        return "GitHub token is NOT set"

    # Parse provider/model format
    model_str = settings.llm_model
    if "/" in model_str:
        model_str = model_str.split("/", 1)[1]

    model = ChatOpenAI(model=model_str)
    graph = create_react_agent(model, [check_github_auth])
    return graph


if __name__ == "__main__":
    graph = create_langgraph_agent()

    with AgentRuntime() as runtime:
        # credentials=["GITHUB_TOKEN"] tells the runtime to resolve
        # GITHUB_TOKEN from the server and inject it into os.environ
        # before the graph executes.
        result = runtime.run(
            graph,
            "Check if GitHub authentication is available",
            credentials=["GITHUB_TOKEN"],
        )
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.16g_credentials_framework_passthrough
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)

