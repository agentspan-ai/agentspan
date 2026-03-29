# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""MCP Weather — using Conductor's MCP system tasks for live weather.

Demonstrates the `mcp_tool()` function which uses Conductor's built-in
LIST_MCP_TOOLS and CALL_MCP_TOOL system tasks. The MCP weather server
provides real weather data, and the Conductor server handles all MCP
protocol communication — **no worker process needed**.

Flow:
    ListMcpTools → LLM (picks tool) → CallMcpTool → Final LLM

Requirements:
    - Conductor server with LLM support
    - MCP weather server running on http://localhost:3001/mcp
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import Agent, AgentRuntime, mcp_tool
from settings import settings

# Create MCP tool from the weather server — Conductor discovers tools at runtime
weather = mcp_tool(
    server_url="http://localhost:3001/mcp",
    name="weather_mcp",
    description="Weather and air quality tools via MCP, use it to get current and historical weather information for "
                "a city",
)

agent = Agent(
    name="weather_mcp_agent",
    model=settings.llm_model,
    max_tokens=10240,
    tools=[weather],
    instructions=(
        "You are a weather assistant. Use the available MCP tools "
        "to answer questions about weather conditions around the world."
        "when asked get the current temperature in F"
        "use the tools provided"
    ),
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.04_mcp_weather
        runtime.deploy(agent)
        runtime.serve(agent)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(agent, "What's the weather like in San Francisco (CA) right now?")
        # result.print_result()

