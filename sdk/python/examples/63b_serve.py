# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Serve — keep tool workers running as a persistent service.

Demonstrates:
    - runtime.serve() to register Python workers and block until interrupted
    - Serving multiple agents in a single process
    - Decoupled from deploy: workers only, no workflow registration

serve() registers the Python tool functions (tools, custom guardrails,
callbacks, handoff checks) as Conductor workers and starts polling for
tasks. The workflow must already exist on the server (from a prior
deploy() or run() call, possibly in a different process).

Start this in a long-running process (systemd, Docker, k8s pod).
Press Ctrl+C to stop.

    python 63b_serve.py

Requirements:
    - Conductor server running
    - Agents already deployed (run 63_deploy.py first)
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


# ── Define agents (same definitions as 63_deploy.py) ─────────────────

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

if __name__ == "__main__":
    # ── Serve: register workers and block ────────────────────────────────

    with AgentRuntime() as runtime:
        print("Serving workers for doc_assistant + ops_bot. Press Ctrl+C to stop.")
        runtime.serve(doc_assistant, ops_bot)  # blocks until Ctrl+C / SIGTERM
