# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Credentials — LangChain AgentExecutor with credential injection.

Demonstrates:
    - runtime.run(executor, credentials=["GITHUB_TOKEN"]) for LangChain
    - Same pattern as LangGraph — credentials resolved from server
      and injected into os.environ before the executor runs

Setup (one-time):
    agentspan credentials set --name GITHUB_TOKEN

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
    """Create a LangChain AgentExecutor with a tool that uses GITHUB_TOKEN."""
    from langchain.agents import AgentExecutor, create_openai_tools_agent
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    from langchain_core.tools import tool as lc_tool
    from langchain_openai import ChatOpenAI

    @lc_tool
    def check_github_token() -> str:
        """Check if GitHub token is available in the environment."""
        token = os.environ.get("GITHUB_TOKEN", "")
        if token:
            return f"GitHub token available (starts with {token[:4]}...)"
        return "GitHub token is NOT available"

    model_str = settings.llm_model
    if "/" in model_str:
        model_str = model_str.split("/", 1)[1]

    llm = ChatOpenAI(model=model_str)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful assistant. Use tools when asked."),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])
    agent = create_openai_tools_agent(llm, [check_github_token], prompt)
    executor = AgentExecutor(agent=agent, tools=[check_github_token])
    return executor


if __name__ == "__main__":
    executor = create_langchain_agent()


    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.16i_credentials_langchain
        runtime.deploy(executor)
        runtime.serve(executor)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(
        #     executor,
        #     "Check if the GitHub token is set",
        #     credentials=["GITHUB_TOKEN"],
        # )
        # result.print_result()

