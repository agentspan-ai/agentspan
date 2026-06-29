# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tool retry configuration — customizing retry behavior per tool.

Demonstrates:
    - retry_policy: "fixed", "linear_backoff", or "exponential_backoff"
    - retry_count: number of retry attempts
    - retry_delay_seconds: base delay between retries
    - Mixing different retry strategies across tools

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from conductor.ai.agents import Agent, AgentRuntime, tool
from settings import settings


@tool(retry_policy="exponential_backoff", retry_count=5, retry_delay_seconds=1)
def call_external_api(query: str) -> dict:
    """Call an unreliable external API that may need aggressive retries."""
    return {"result": f"Data for: {query}", "source": "external_api"}


@tool(retry_policy="fixed", retry_count=3, retry_delay_seconds=5)
def query_database(sql: str) -> dict:
    """Run a database query with fixed-interval retries for transient connection issues."""
    return {"rows": [{"id": 1, "value": sql}], "count": 1}


@tool(retry_policy="linear_backoff", retry_count=2, retry_delay_seconds=2)
def process_data(data: str) -> dict:
    """Process data locally — light retries with linear backoff."""
    return {"processed": data, "status": "ok"}


agent = Agent(
    name="retry_config_demo",
    model=settings.llm_model,
    tools=[call_external_api, query_database, process_data],
    instructions="You help users fetch and process data. Use the appropriate tool for each request.",
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(agent, "Look up the latest Python release info from the API.")
        result.print_result()
