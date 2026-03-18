# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Deploy — register agents on the server (CI/CD step).

Demonstrates:
    - runtime.deploy() to compile and register multiple agents
    - DeploymentInfo result with workflow name and agent name
    - CI/CD use case: push agent definitions without executing them

deploy() sends agent configs to the server, which compiles them into
Conductor workflow definitions and registers the corresponding task
definitions. No local workers are started, no execution happens.

Run this once during deployment. Use serve() separately (63b) to keep
workers alive, and run-by-name (63c) to trigger execution.

Requirements:
    - Conductor server running
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

from agentspan.agents import Agent, AgentRuntime, tool
from settings import settings


@tool
def search_docs(query: str) -> str:
    """Search internal documentation.

    Args:
        query: Search query string.

    Returns:
        Matching documentation excerpts.
    """
    return f"Found 3 results for: {query}"


@tool
def check_status(service: str) -> str:
    """Check service health status.

    Args:
        service: Name of the service to check.

    Returns:
        Health status string.
    """
    return f"{service}: healthy"


# ── Define agents ────────────────────────────────────────────────────

doc_assistant = Agent(
    name="doc_assistant",
    model=settings.llm_model,
    tools=[search_docs],
    instructions="Help users find documentation. Use search_docs to look up answers.",
)

ops_bot = Agent(
    name="ops_bot",
    model=settings.llm_model,
    tools=[check_status],
    instructions="Monitor service health. Use check_status to inspect services.",
)

# ── Deploy: compile + register on server ─────────────────────────────

with AgentRuntime() as runtime:
    results = runtime.deploy(doc_assistant, ops_bot)

    for info in results:
        print(f"Deployed: {info.agent_name} -> {info.workflow_name}")

    print(f"\n{len(results)} agent(s) registered on server.")
    print("Now run 63b_serve.py to start workers, then 63c_run_by_name.py to execute.")
