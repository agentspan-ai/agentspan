# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tool Retries — automatic tool retries on transient failures.

Demonstrates:
    - @tool(retry_count=3, retry_delay_seconds=2) to configure Conductor retry policy
    - Simulated transient failure: tool fails on the first two attempts, succeeds on the third
    - How Agentspan automatically retries the tool without agent intervention
    - retry_count=0 to disable retries entirely (fail-fast tools like payment processing)

How it works:
    When a @tool function raises an exception, Conductor retries the task up to
    ``retry_count`` times, waiting ``retry_delay_seconds`` between each attempt.
    The LLM never sees the intermediate failures — it only receives the final
    successful result (or a failure if all retries are exhausted).

Parameters:
    retry_count         — maximum number of retry attempts (default: 2)
    retry_delay_seconds — seconds to wait between retries (default: 2)

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable

Usage:
    python 85_tool_retries.py
"""

import os

os.environ.setdefault("AGENTSPAN_LOG_LEVEL", "WARNING")

from agentspan.agents import Agent, AgentRuntime, tool
from settings import settings

# ---------------------------------------------------------------------------
# Simulates a flaky external service: fails on the first two calls, succeeds
# on the third.  In production this would be a real network call.
# ---------------------------------------------------------------------------
_call_count = 0


@tool(retry_count=3, retry_delay_seconds=2)
def fetch_exchange_rate(base: str, target: str) -> dict:
    """Fetch the current exchange rate between two currencies."""
    global _call_count
    _call_count += 1

    if _call_count <= 2:
        raise ConnectionError(
            f"[attempt {_call_count}] Upstream FX service unavailable — retrying..."
        )

    # Third attempt succeeds
    rates = {
        ("USD", "EUR"): 0.92,
        ("USD", "GBP"): 0.79,
        ("EUR", "USD"): 1.09,
    }
    rate = rates.get((base.upper(), target.upper()), 1.0)
    return {
        "base": base.upper(),
        "target": target.upper(),
        "rate": rate,
        "attempt": _call_count,
    }


# retry_count=0 means fail immediately — no retries.
# Useful for idempotency-sensitive operations like payment processing.
@tool(retry_count=0)
def process_payment(amount: float, currency: str) -> dict:
    """Process a payment (fail-fast — no retries)."""
    return {"status": "approved", "amount": amount, "currency": currency.upper()}


agent = Agent(
    name="retry_demo_agent",
    model=settings.llm_model,
    tools=[fetch_exchange_rate, process_payment],
    instructions=(
        "You are a helpful currency and payment assistant. "
        "Use fetch_exchange_rate to look up exchange rates and "
        "process_payment to handle payments."
    ),
)


if __name__ == "__main__":
    print("Running tool-retry example.")
    print("fetch_exchange_rate will fail twice before succeeding on the third attempt.\n")

    with AgentRuntime() as runtime:
        result = runtime.run(agent, "What is the current USD to EUR exchange rate?")
        result.print_result()

    # Production pattern:
    # 1. Deploy once during CI/CD:
    # with AgentRuntime() as runtime:
    #     runtime.deploy(agent)
    #
    # 2. In a separate long-lived worker process:
    # with AgentRuntime() as runtime:
    #     runtime.serve(agent)
