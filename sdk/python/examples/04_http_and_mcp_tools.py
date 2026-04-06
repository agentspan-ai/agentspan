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
    - MCP test server running on http://localhost:3001 (see tests/e2e/mcp-test-server)
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import Agent, AgentRuntime, tool, http_tool, mcp_tool
from settings import settings


# Python tool (needs a worker)
@tool
def format_report(title: str, body: str) -> dict:
    """Format a title and body into a structured report."""
    return {"report": f"=== {title} ===\n{body}\n{'=' * (len(title) + 8)}"}


# HTTP tool (pure server-side, no worker needed)
reverse_api = http_tool(
    name="reverse_string",
    description="Reverse a string using the HTTP API",
    url="http://localhost:3001/api/string/reverse",
    method="POST",
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to reverse"},
        },
        "required": ["text"],
    },
)

# MCP tools (discovered from MCP server at runtime)
# Requires a running MCP server — uncomment and point to your MCP endpoint
# github_tools = mcp_tool(
#     server_url="http://localhost:3001/mcp",
#     name="github",
#     description="GitHub operations via MCP",
# )

agent = Agent(
    name="http_tools_demo",
    model=settings.llm_model,
    tools=[format_report, reverse_api],
    instructions=(
        "You can reverse strings and format reports. "
        "When asked to reverse a string, use reverse_string first, then format_report with the result."
    ),
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            agent,
            "Reverse the string 'hello world', then write a report with the result.",
        )
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.04_http_and_mcp_tools
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)
