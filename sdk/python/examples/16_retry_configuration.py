# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Retry Configuration — controlling how Conductor retries failed tool executions.

Demonstrates three retry strategies:
  - FIXED: constant delay between retries (default when not specified)
  - LINEAR_BACKOFF: delay increases linearly (delay × attempt_number)
  - EXPONENTIAL_BACKOFF: delay increases exponentially (delay × 2^attempt_number)

Also shows retry_count=0 to disable retries entirely (fail immediately on first error).

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import Agent, AgentRuntime, tool
from settings import settings


@tool(retry_count=10, retry_delay_seconds=5)
def fetch_data(query: str) -> str:
    """Fetch data from a remote source.

    Retries up to 10 times with a fixed 5-second delay between attempts
    (FIXED strategy is the default when retry_logic is not specified).
    """
    return f"Data fetched for query: {query}"


@tool(retry_count=5, retry_delay_seconds=2, retry_logic="LINEAR_BACKOFF")
def call_external_api(endpoint: str) -> str:
    """Call an external API endpoint.

    Retries up to 5 times with linearly increasing delays:
    2s, 4s, 6s, 8s, 10s (delay × attempt_number).
    """
    return f"API response from: {endpoint}"


@tool(retry_count=3, retry_delay_seconds=1, retry_logic="EXPONENTIAL_BACKOFF")
def process_payment(amount: float) -> str:
    """Process a payment transaction.

    Retries up to 3 times with exponentially increasing delays:
    1s, 2s, 4s (delay × 2^attempt_number).
    """
    return f"Payment processed: null"


@tool(retry_count=0)
def validate_input(data: str) -> str:
    """Validate input data — no retries.

    retry_count=0 disables retries entirely. If this tool fails,
    Conductor will not retry it and the execution will fail immediately.
    """
    if not data:
        raise ValueError("Input data cannot be empty")
    return f"Input valid: {data}"


agent = Agent(
    name="retry_demo",
    model=settings.llm_model,
    instructions=(
        "You are a demo agent showcasing retry configuration. "
        "Use the available tools to demonstrate different retry strategies."
    ),
    tools=[fetch_data, call_external_api, process_payment, validate_input],
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(agent, "Demo retry configuration by fetching data and calling an API")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.16_retry_configuration
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)
