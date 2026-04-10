# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""HTTP and MCP Tools — server-side tools (no workers needed).

Demonstrates:
    - http_tool: HTTP endpoints as tools (Conductor HttpTask)
    - mcp_tool: MCP server tools (Conductor ListMcpTools + CallMcpTool)
    - Mixing Python tools with server-side tools

These tools execute entirely server-side — no Python worker process needed.

MCP Test Server Setup (mcp-testkit):
    pip install mcp-testkit

    # Start without auth:
    mcp-testkit --transport http

    # Or start with auth (requires storing the secret as a credential):
    mcp-testkit --transport http --auth <secret>

    # Store credentials via CLI or Agentspan UI:
    agentspan credentials set HTTP_TEST_API_KEY <secret>
    agentspan credentials set MCP_TEST_API_KEY <secret>

Requirements:
    - Conductor server with LLM support
    - mcp-testkit running on http://localhost:3001 (see setup above)
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
# ${HTTP_TEST_API_KEY} is resolved server-side from the credential store.
reverse_api = http_tool(
    name="reverse_string",
    description="Reverse a string using the HTTP API",
    url="http://localhost:3001/api/string/reverse",
    method="POST",
    headers={"Authorization": "Bearer ${HTTP_TEST_API_KEY}"},
    credentials=["HTTP_TEST_API_KEY"],
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to reverse"},
        },
        "required": ["text"],
    },
)

# MCP tools (discovered from MCP server at runtime)
# ${MCP_TEST_API_KEY} is resolved server-side from the credential store.
mcp_test_tools = mcp_tool(
    server_url="http://localhost:3001/mcp",
    name="mcp_test_tools",
    description="Deterministic test tools via MCP — math, string, collection, encoding, hash, datetime, validation, and conversion operations.",
    headers={"Authorization": "Bearer ${MCP_TEST_API_KEY}"},
    credentials=["MCP_TEST_API_KEY"],
)

agent = Agent(
    name="http_tools_demo",
    model=settings.llm_model,
    tools=[format_report, reverse_api, mcp_test_tools],
    instructions=(
        "You can reverse strings and format reports. "
        "When asked to reverse a string, use reverse_string first, then format_report with the result."
    ),
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            agent,
            "Reverse the string 'hello world' and add 33 and 21 append the result to that string, then write a report with the result.",
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
