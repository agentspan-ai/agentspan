# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""API Tool — auto-discover endpoints from OpenAPI, Swagger, or Postman specs.

Demonstrates api_tool(), which points to an API spec and automatically
discovers all operations as agent tools. The server fetches the spec at
workflow startup, parses it, and makes each operation available to the LLM.
No manual tool definitions needed — just point and go.

Three patterns shown:
    1. OpenAPI 3.x spec URL with credentials
    2. Base URL (server auto-discovers /openapi.json, /swagger.json, etc.)
    3. Mixing api_tool with other tool types (mcp_tool, @tool)

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
    - For credential examples: store credentials via `agentspan credential store`
"""

from agentspan.agents import Agent, AgentRuntime, api_tool, mcp_tool, tool
from settings import settings


# ── Example 1: OpenAPI spec with credentials ──────────────────────────
#
# Point to a live OpenAPI spec. The server discovers all operations,
# and the LLM picks the right one based on the user's request.
# Global auth headers are applied to every discovered endpoint.
#
# Before running, store the credential:
#   agentspan credential store PETSTORE_KEY your-api-key

petstore = api_tool(
    url="https://petstore3.swagger.io/api/v3/openapi.json",
    name="petstore",
    max_tools=20,  # Petstore has many ops — filter to top 20
)

pet_agent = Agent(
    name="pet_store_assistant",
    model=settings.llm_model,
    instructions="You help users manage a pet store. Use the available API tools.",
    tools=[petstore],
)


# ── Example 2: Base URL (auto-discovery) ──────────────────────────────
#
# Just provide the base URL. The server tries:
#   /openapi.json, /swagger.json, /v3/api-docs, /swagger/v1/swagger.json,
#   /api-docs, /.well-known/openapi.json
#
# Optionally whitelist specific operations:

weather = api_tool(
    url="https://api.weather.com",
    tool_names=["getCurrentWeather", "getForecast"],  # Only these two ops
)

weather_agent = Agent(
    name="weather_assistant",
    model=settings.llm_model,
    instructions="You provide weather information.",
    tools=[weather],
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


petstore_api = api_tool(
    url="https://petstore3.swagger.io/api/v3/openapi.json",
    max_tools=10,
)

multi_tool_agent = Agent(
    name="multi_tool_assistant",
    model=settings.llm_model,
    instructions=(
        "You are a versatile assistant. Use API tools for pet store operations, "
        "and the calculator for math. Pick the best tool for each request."
    ),
    tools=[petstore_api, calculate],
)


# ── Example 4: Large API with credential auth ────────────────────────
#
# For large APIs (300+ operations), max_tools controls filtering.
# A lightweight LLM automatically selects the most relevant operations
# based on the user's prompt — so the main agent LLM only sees what
# it needs.
#
# Before running:
#   agentspan credential store GITHUB_TOKEN ghp_xxxxxxxxxxxx

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
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.71_api_tool
        runtime.deploy(pet_agent)
        runtime.serve(pet_agent)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # # Example 1: Petstore
        # print("=== Petstore API ===")
        # result = runtime.run(pet_agent, "List all available pets with status 'available'")
        # result.print_result()

        # # Example 3: Mixed tools
        # print("\n=== Mixed Tools ===")
        # result = runtime.run(multi_tool_agent, "What's sqrt(144)? Also find pets named 'doggie'.")
        # result.print_result()

