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
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
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
        # Serve an explicit agent + auto-discover from a package
        # runtime.serve(monitoring_agent, packages=["myapp.agents"])

        # For this example, just serve the explicit agent
        print("Serving monitoring agent. Press Ctrl+C to stop.")
        print("Uncomment the packages= line to also serve discovered agents.")
        runtime.serve(monitoring_agent)
