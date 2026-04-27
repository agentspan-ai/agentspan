# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Retry Example — automatic tool retries on transient failures.

Demonstrates:
    - @tool with retry_count and retry_delay_seconds
    - Simulated transient failure that succeeds after retries
    - How Agentspan automatically retries the tool without agent intervention

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

import os
from agentspan.agents import Agent, AgentRuntime, tool

# Simulates a flaky external service: fails on the first two calls, succeeds on the third.
_call_count = 0


@tool(retry_count=3, retry_delay_seconds=1)
def fetch_exchange_rate(base: str, target: str) -> dict:
    """Fetch the exchange rate between two currencies."""
    global _call_count
    _call_count += 1

    if _call_count <= 2:
        raise ConnectionError(
            f"[attempt {_call_count}] Upstream service unavailable — retrying..."
        )

    # Third attempt succeeds
    rates = {("USD", "EUR"): 0.92, ("USD", "GBP"): 0.79, ("EUR", "USD"): 1.09}
    rate = rates.get((base.upper(), target.upper()), 1.0)
    return {"base": base.upper(), "target": target.upper(), "rate": rate, "attempt": _call_count}


agent = Agent(
    name="exchange_rate_agent",
    model=os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o-mini"),
    tools=[fetch_exchange_rate],
    instructions="You are a helpful currency assistant. Use the fetch_exchange_rate tool to answer questions.",
)


if __name__ == "__main__":
    print("Running retry example — the tool will fail twice before succeeding.\n")
    with AgentRuntime() as runtime:
        result = runtime.run(agent, "What is the current USD to EUR exchange rate?")
        result.print_result()
