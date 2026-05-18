# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""API Tool — auto-discover endpoints from OpenAPI, Swagger, or Postman specs.

Demonstrates api_tool(), which points to an API spec and automatically
discovers all operations as agent tools. The server fetches the spec at
workflow startup, parses it, and makes each operation available to the LLM.
No manual tool definitions needed — just point and go.

Four patterns shown:
    1. OpenAPI 3.x spec URL (local MCP test server with 65 deterministic tools)
    2. Filtered operations — whitelist specific endpoints via tool_names
    3. Mixing api_tool with other tool types (@tool)
    4. Large API with credential auth (GitHub)

MCP Test Server Setup (mcp-testkit) — required for examples 1-3:
    pip install mcp-testkit

    # Start without auth:
    mcp-testkit --transport http

    # Or start with auth (requires storing the secret as a credential):
    mcp-testkit --transport http --auth <secret>

    # Store credentials via CLI or Agentspan UI:
    agentspan credentials set HTTP_TEST_API_KEY <secret>

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
    - mcp-testkit running on http://localhost:3001 (for examples 1-3, see setup above)
    - For GitHub example: agentspan credentials set GITHUB_TOKEN ghp_xxx
"""

from agentspan.agents import Agent, AgentRuntime, api_tool, tool
from settings import settings

MCP_TEST_SERVER_SPEC = "http://localhost:3001/api-docs"


# ── Example 1: OpenAPI spec (full discovery) ──────────────────────────
#
# Point to a live OpenAPI spec. The server discovers all operations,
# and the LLM picks the right one based on the user's request.
# The MCP test server exposes 65 deterministic tools across math,
# string, collection, encoding, hash, datetime, validation, and
# conversion groups.

math_api = api_tool(
    url=MCP_TEST_SERVER_SPEC,
    name="mcp_test_tools",
    headers={"Authorization": "Bearer ${HTTP_TEST_API_KEY}"},
    credentials=["HTTP_TEST_API_KEY"],
    max_tools=10,  # 65 ops — filter to top 10 most relevant
)

math_agent = Agent(
    name="math_assistant",
    model=settings.llm_model,
    instructions="You are a math assistant. Use the API tools to compute results.",
    tools=[math_api],
)


# ── Example 2: Filtered operations (tool_names whitelist) ─────────────
#
# Whitelist specific operations by operationId. Only these are
# exposed to the LLM — everything else is ignored.

string_api = api_tool(
    url=MCP_TEST_SERVER_SPEC,
    headers={"Authorization": "Bearer ${HTTP_TEST_API_KEY}"},
    credentials=["HTTP_TEST_API_KEY"],
    tool_names=["string_reverse", "string_uppercase", "string_length"],
)

string_agent = Agent(
    name="string_assistant",
    model=settings.llm_model,
    instructions="You are a string manipulation assistant.",
    tools=[string_api],
)


# ── Example 3: Mix api_tool with other tool types ─────────────────────
#
# api_tool works alongside mcp_tool, http_tool, and native @tool.
# The LLM sees all tools uniformly — it doesn't know which are
# auto-discovered vs hand-defined.

@tool
def calculate(expression: str) -> dict:
    """Evaluate a math expression."""
    import math
    safe_builtins = {"abs": abs, "round": round, "sqrt": math.sqrt, "pow": pow}
    try:
        result = eval(expression, {"__builtins__": {}}, safe_builtins)
        return {"expression": expression, "result": result}
    except Exception as e:
        return {"expression": expression, "error": str(e)}


collection_api = api_tool(
    url=MCP_TEST_SERVER_SPEC,
    headers={"Authorization": "Bearer ${HTTP_TEST_API_KEY}"},
    credentials=["HTTP_TEST_API_KEY"],
    tool_names=["collection_sort", "collection_unique", "collection_flatten"],
    max_tools=10,
)

multi_tool_agent = Agent(
    name="multi_tool_assistant",
    model=settings.llm_model,
    instructions=(
        "You are a versatile assistant. Use API tools for collection operations, "
        "and the calculator for math. Pick the best tool for each request."
    ),
    tools=[collection_api, calculate],
)


# ── Example 4: Large API with credential auth ────────────────────────
#
# For large APIs (300+ operations), max_tools controls filtering.
# A lightweight LLM automatically selects the most relevant operations
# based on the user's prompt — so the main agent LLM only sees what
# it needs.
#
# Before running:
#   agentspan credentials set GITHUB_TOKEN ghp_xxxxxxxxxxxx

github = api_tool(
    url="https://api.github.com",
    headers={"Authorization": "token ${GITHUB_TOKEN}", "Accept": "application/vnd.github+json"},
    credentials=["GITHUB_TOKEN"],
    tool_names=["repos_list_for_user", "repos_create_for_authenticated_user",
                "issues_list_for_repo", "issues_create"],
    max_tools=20,
)

github_agent = Agent(
    name="github_assistant",
    model=settings.llm_model,
    instructions="You help users manage their GitHub repositories and issues.",
    tools=[github],
)


# ── Run ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Example 1: Math via OpenAPI-discovered tools
        print("=== Math API ===")
        result = runtime.run(math_agent, "What is 15 + 27? Also compute 8 factorial.")
        result.print_result()

        # Example 2: Filtered string tools
        print("\n=== String API (filtered) ===")
        result = runtime.run(string_agent, "Reverse the string 'hello world' and tell me its length.")
        result.print_result()

        # Example 3: Mixed tools
        print("\n=== Mixed Tools ===")
        result = runtime.run(multi_tool_agent, "Sort [3,1,4,1,5,9] and also compute sqrt(144).")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(math_agent)
        # CLI alternative:
        # agentspan deploy --package examples.71_api_tool
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(math_agent)

