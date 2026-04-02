# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Deploy — register agents on the server (CI/CD step).

Demonstrates:
    - runtime.deploy() to compile and register multiple agents
    - DeploymentInfo result with registered name and agent name
    - CI/CD use case: push agent definitions without executing them

deploy() sends agent configs to the server, which compiles them into
Conductor workflow definitions and registers the corresponding task
definitions. No local workers are started, no execution happens.

Run this once during deployment. Use serve() separately (63b) to keep
workers alive, or use `runtime.run()` directly in app code and keep
deploy/serve as the production pattern.

Requirements:
    - Conductor server running
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api in .env or environment
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini in .env or environment
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

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(doc_assistant, "How do I reset my password?")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # results = runtime.deploy(doc_assistant, ops_bot)
        # for info in results:
        #     print(f"Deployed: {info.agent_name} -> {info.registered_name}")
        # CLI alternative:
        # agentspan deploy --package examples.63_deploy
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(doc_assistant, ops_bot)
