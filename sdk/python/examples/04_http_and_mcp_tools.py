# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""HTTP and MCP Tools — server-side tools (no workers needed).

Demonstrates:
    - http_tool: HTTP endpoints as tools (Conductor HttpTask)
    - mcp_tool: MCP server tools (Conductor ListMcpTools + CallMcpTool)
    - Mixing Python tools with server-side tools

These tools execute entirely server-side — no Python worker process needed.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

from agentspan.agents import Agent, AgentRuntime, tool, http_tool, mcp_tool
from settings import settings


# Python tool (needs a worker)
@tool
def format_report(data: dict) -> str:
    """Format raw data into a readable report."""
    return f"Report: {data}"


# HTTP tool (pure server-side, no worker needed)
weather_api = http_tool(
    name="get_current_weather",
    description="Get current weather for a city from the weather API",
    url="http://localhost:3001/mcp",
    method="POST",
    accept= ["text/event-stream", "application/json"],
    input_schema={
        "type": "object",
        "properties": {
        "jsonrpc": {
          "type": "string",
          "const": "2.0"
        },
        "id": {
          "const": 1
        },
        "method": {
          "type": "string",
          "const": "tools/call"
        },
        "params": {
          "type": "object",
          "additionalProperties": False,
          "properties": {
            "name": {
              "type": "string",
              "const": "get_current_weather"
            },
            "arguments": {
              "type": "object",
              "additionalProperties": False,
              "properties": {
                "city": {
                  "type": "string"
                }
              },
              "required": ["city"]
            }
          },
          "required": ["name", "arguments"]
        }
      },
      "required": ["jsonrpc", "id", "method", "params"]
    },
)

# MCP tools (discovered from MCP server at runtime)
github_tools = mcp_tool(
    server_url="http://localhost:3001/mcp",
    name="github",
    description="GitHub operations via MCP",
)

agent = Agent(
    name="api_assistant",
    model=settings.llm_model,
    tools=[format_report, weather_api],
    max_tokens=102040,
    instructions="You have access to weather data, GitHub, and report formatting.",
)

with AgentRuntime() as runtime:
    result = runtime.run(agent, "Get the weather in London and format it as a report.")
    result.print_result()
