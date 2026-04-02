# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Credentials — MCP tool with server-side credential resolution.

Demonstrates:
    - mcp_tool() with credentials=["MCP_API_KEY"]
    - ${MCP_API_KEY} in headers resolved server-side before MCP calls
    - MCP server authentication handled transparently

Setup (one-time):
    agentspan credentials set --name MCP_API_KEY

MCP Weather Server Setup:
    # Install and start the weather MCP server (runs on port 3001):
    npx -y @philschmid/weather-mcp

Requirements:
    - Agentspan server running at AGENTSPAN_SERVER_URL
    - AGENTSPAN_LLM_MODEL set (or defaults to openai/gpt-5.4)
    - MCP server running on http://localhost:3001/mcp (see setup above)
    - MCP_API_KEY stored via `agentspan credentials set`
"""

from agentspan.agents import Agent, AgentRuntime
from agentspan.agents.tool import mcp_tool
from settings import settings


# MCP tool with credential-bearing headers.
# ${MCP_API_KEY} is resolved server-side before each MCP call.
my_mcp_tools = mcp_tool(
    server_url="http://localhost:3001/mcp",
    headers={
        "Authorization": "Bearer ${MCP_API_KEY}",
    },
    credentials=["MCP_API_KEY"],
)

agent = Agent(
    name="mcp_cred_agent",
    model=settings.llm_model,
    tools=[my_mcp_tools],
    instructions="You have access to MCP tools. Use them to help the user.",
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(agent, "What tools are available?")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.16f_credentials_mcp_tool
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)

