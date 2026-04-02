# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Serve from Package — auto-discover and serve all agents in a package.

Demonstrates:
    - runtime.serve(packages=["myapp.agents"]) — auto-discovery
    - Scanning Python packages for module-level Agent instances
    - Mixing explicit agents with package-based discovery

discover_agents() recursively imports the specified packages and
collects all module-level Agent instances. This avoids the need to
explicitly list every agent when serving a large codebase.

    python 63d_serve_from_package.py

Requirements:
    - Conductor server running
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api in .env or environment
    - A Python package with Agent instances at module level
"""

from agentspan.agents import Agent, AgentRuntime, discover_agents, tool
from settings import settings


# ── Option 1: Discover agents from packages ──────────────────────────

# Preview what would be discovered (useful for debugging)
# agents = discover_agents(["myapp.agents"])
# for a in agents:
#     print(f"  Discovered: {a.name}")


# ── Option 2: Mix explicit agents with package discovery ─────────────

@tool
def health_check() -> str:
    """Perform a basic health check.

    Returns:
        Health status message.
    """
    return "All systems operational"


monitoring_agent = Agent(
    name="monitoring",
    model=settings.llm_model,
    tools=[health_check],
    instructions="You monitor system health.",
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(monitoring_agent, "Is everything healthy? Run a full check.")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(monitoring_agent, *discover_agents(["myapp.agents"]))
        # CLI alternative:
        # agentspan deploy --package examples.63d_serve_from_package
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(monitoring_agent, packages=["myapp.agents"])
