# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tool Retry Configuration — per-tool retry_count and retry_delay_seconds.

Demonstrates how to control Conductor task retry behaviour on a per-tool basis
using the new retry_count and retry_delay_seconds parameters on the @tool
decorator (issue #150).

Three patterns shown:
    1. Default behaviour  — no retry params; Conductor uses retry_count=2,
                            retry_delay_seconds=2 (the built-in defaults).
    2. Aggressive retries — retry_count=10, retry_delay_seconds=5 for a
                            flaky external API that occasionally times out.
    3. Zero retries       — retry_count=0 for an idempotency-sensitive
                            operation (e.g. payment processing) that must
                            never be silently retried.

Key concept:
    Each @tool function is registered as a Conductor TaskDef.  The
    retry_count / retry_delay_seconds values are written directly into that
    TaskDef, so Conductor's own retry machinery honours them — no application-
    level retry loops needed.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

import random

from agentspan.agents import Agent, AgentRuntime, tool
from settings import settings


# ── Pattern 1: Default retries (retry_count=2, retry_delay_seconds=2) ────────
#
# Omitting retry params uses the SDK defaults.  Suitable for most tools.

@tool
def get_weather(city: str) -> dict:
    """Get current weather for a city."""
    weather_data = {
        "new york": {"temp": 72, "condition": "Partly Cloudy"},
        "san francisco": {"temp": 58, "condition": "Foggy"},
        "miami": {"temp": 85, "condition": "Sunny"},
    }
    data = weather_data.get(city.lower(), {"temp": 70, "condition": "Clear"})
    return {"city": city, "temperature_f": data["temp"], "condition": data["condition"]}


# ── Pattern 2: Aggressive retries for a flaky external API ───────────────────
#
# retry_count=10  — Conductor will attempt the task up to 11 times total
#                   (1 initial attempt + 10 retries).
# retry_delay_seconds=5 — Wait 5 seconds between each attempt, giving the
#                          upstream service time to recover.
#
# Use this for third-party APIs that are occasionally unavailable or rate-limit
# with transient 429/503 responses.

@tool(retry_count=10, retry_delay_seconds=5)
def call_flaky_api(query: str) -> dict:
    """Search an external knowledge base that occasionally times out.

    Simulates a flaky upstream service: fails ~30 % of the time so that
    Conductor's retry logic can kick in during a real deployment.
    """
    # Simulate intermittent failure (demo only — remove in production)
    if random.random() < 0.3:
        raise RuntimeError("Upstream service temporarily unavailable — will be retried")

    return {
        "query": query,
        "results": [
            {"title": "Result A", "score": 0.95},
            {"title": "Result B", "score": 0.87},
        ],
    }


# ── Pattern 3: Zero retries for idempotency-sensitive operations ──────────────
#
# retry_count=0 — Conductor will NOT retry this task if it fails.
#
# Critical for operations that must not be executed more than once:
#   - Payment charges
#   - Email / SMS sends
#   - Irreversible database mutations
#
# If the task fails, the workflow fails immediately and the caller is
# responsible for deciding whether to retry the entire workflow.

@tool(retry_count=0)
def process_payment(amount: float, card_token: str) -> dict:
    """Charge a payment card.

    retry_count=0 ensures Conductor never silently re-runs this task,
    preventing accidental double-charges.
    """
    # In production this would call your payment gateway
    return {
        "status": "charged",
        "amount": amount,
        "transaction_id": "txn_demo_001",
        "card_last4": card_token[-4:],
    }


# ── Agent ─────────────────────────────────────────────────────────────────────

agent = Agent(
    name="retry_config_demo_agent",
    model=settings.llm_model,
    tools=[get_weather, call_flaky_api, process_payment],
    instructions=(
        "You are a helpful assistant. "
        "Use get_weather for weather queries, "
        "call_flaky_api for knowledge-base searches, "
        "and process_payment to charge a card."
    ),
)


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Demonstrate the default-retry tool
        print("=== Weather (default retries: 2) ===")
        result = runtime.run(agent, "What is the weather in Miami?")
        result.print_result()

        # Demonstrate the high-retry tool
        print("\n=== Flaky API (retry_count=10, retry_delay_seconds=5) ===")
        result = runtime.run(agent, "Search the knowledge base for 'distributed systems'.")
        result.print_result()

        # Demonstrate the zero-retry tool
        print("\n=== Payment (retry_count=0 — no retries) ===")
        result = runtime.run(
            agent,
            "Charge $49.99 to card token 'tok_visa_4242'.",
        )
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.98_tool_retry_config
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)
