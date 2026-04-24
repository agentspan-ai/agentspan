# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tool Retry Configuration — per-tool retry_count, retry_delay_seconds, retry_logic.

Demonstrates:
    - Setting retry_count on @tool to control how many times Conductor retries
      a failed task before giving up
    - Setting retry_delay_seconds to control the wait between retries
    - Setting retry_logic to choose the backoff strategy:
        "FIXED"               — same delay every time
        "LINEAR_BACKOFF"      — delay grows linearly (default)
        "EXPONENTIAL_BACKOFF" — delay doubles each attempt
    - Using retry_count=0 to disable retries entirely (e.g. payment operations)
    - Mixing retry configs across tools in the same agent

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

import random

from agentspan.agents import Agent, AgentRuntime, tool
from settings import settings


# ---------------------------------------------------------------------------
# Tool 1: Flaky external API — aggressive retries with exponential backoff.
#
# retry_count=5        → up to 5 retry attempts after the first failure
# retry_delay_seconds=3 → base delay of 3 s (doubles each attempt with EXPONENTIAL_BACKOFF)
# retry_logic="EXPONENTIAL_BACKOFF" → 3s, 6s, 12s, 24s, 48s between retries
# ---------------------------------------------------------------------------
@tool(retry_count=5, retry_delay_seconds=3, retry_logic="EXPONENTIAL_BACKOFF")
def fetch_market_data(ticker: str) -> dict:
    """Fetch real-time market data for a stock ticker.

    This tool calls an unreliable third-party market-data API.
    Exponential backoff gives the upstream service time to recover.
    """
    # Simulate occasional failures from a flaky upstream API
    if random.random() < 0.3:
        raise RuntimeError(f"Market data API timeout for {ticker}")

    prices = {
        "AAPL": 189.42,
        "GOOGL": 175.18,
        "MSFT": 415.30,
        "AMZN": 198.75,
        "TSLA": 248.60,
    }
    price = prices.get(ticker.upper(), round(random.uniform(50, 500), 2))
    return {
        "ticker": ticker.upper(),
        "price": price,
        "currency": "USD",
        "source": "market-data-api",
    }


# ---------------------------------------------------------------------------
# Tool 2: Payment processing — NO retries.
#
# retry_count=0 → fail immediately on error; never retry.
#
# Critical for idempotency: retrying a payment could charge the customer twice.
# ---------------------------------------------------------------------------
@tool(retry_count=0)
def process_payment(amount: float, currency: str, description: str) -> dict:
    """Process a payment transaction.

    IMPORTANT: retry_count=0 ensures this tool is never retried automatically.
    Retrying a payment could result in duplicate charges.
    """
    # Simulate payment processing
    transaction_id = f"txn_{random.randint(100000, 999999)}"
    return {
        "transaction_id": transaction_id,
        "amount": amount,
        "currency": currency,
        "description": description,
        "status": "approved",
    }


# ---------------------------------------------------------------------------
# Tool 3: Internal microservice — fixed delay retries.
#
# retry_count=3        → up to 3 retries
# retry_delay_seconds=2 → always wait exactly 2 s between retries (FIXED)
# retry_logic="FIXED"  → predictable, constant delay (good for internal services)
# ---------------------------------------------------------------------------
@tool(retry_count=3, retry_delay_seconds=2, retry_logic="FIXED")
def get_account_balance(account_id: str) -> dict:
    """Retrieve the current balance for a bank account.

    Calls an internal account-service. Fixed retry delay gives the service
    a predictable recovery window without compounding backoff pressure.
    """
    # Simulate internal service lookup
    balances = {
        "ACC-001": 12_450.00,
        "ACC-002": 3_820.50,
        "ACC-003": 98_100.75,
    }
    balance = balances.get(account_id, round(random.uniform(100, 50000), 2))
    return {
        "account_id": account_id,
        "balance": balance,
        "currency": "USD",
        "as_of": "2026-04-24T12:00:00Z",
    }


# ---------------------------------------------------------------------------
# Tool 4: Default retry behaviour (no retry params set).
#
# Omitting retry params uses the SDK defaults:
#   retry_count=2, retry_delay_seconds=2, retry_logic="LINEAR_BACKOFF"
# ---------------------------------------------------------------------------
@tool
def get_exchange_rate(from_currency: str, to_currency: str) -> dict:
    """Get the current exchange rate between two currencies.

    Uses default retry settings (retry_count=2, LINEAR_BACKOFF).
    Suitable for most tools that don't have special retry requirements.
    """
    rates = {
        ("USD", "EUR"): 0.92,
        ("USD", "GBP"): 0.79,
        ("USD", "JPY"): 154.30,
        ("EUR", "USD"): 1.09,
    }
    rate = rates.get((from_currency.upper(), to_currency.upper()), 1.0)
    return {
        "from": from_currency.upper(),
        "to": to_currency.upper(),
        "rate": rate,
    }


# ---------------------------------------------------------------------------
# Agent — uses all four tools with different retry profiles
# ---------------------------------------------------------------------------
agent = Agent(
    name="financial_assistant_retry_demo",
    model=settings.llm_model,
    tools=[fetch_market_data, process_payment, get_account_balance, get_exchange_rate],
    instructions=(
        "You are a financial assistant. Help users with stock prices, account balances, "
        "currency conversions, and payment processing. "
        "Always confirm payment details with the user before processing."
    ),
)


if __name__ == "__main__":
    print("=== Tool Retry Configuration Demo ===\n")
    print("Retry profiles:")
    print("  fetch_market_data   → retry_count=5, retry_delay_seconds=3, EXPONENTIAL_BACKOFF")
    print("  process_payment     → retry_count=0  (no retries — idempotency critical)")
    print("  get_account_balance → retry_count=3, retry_delay_seconds=2, FIXED")
    print("  get_exchange_rate   → defaults       (retry_count=2, LINEAR_BACKOFF)\n")

    with AgentRuntime() as runtime:
        result = runtime.run(
            agent,
            "What is the current price of AAPL stock? "
            "Also, what is the USD to EUR exchange rate? "
            "And what is the balance on account ACC-001?",
        )
        result.print_result()

    # Production pattern:
    # 1. Deploy once during CI/CD:
    #    runtime.deploy(agent)
    #
    # 2. In a separate long-lived worker process:
    #    runtime.serve(agent)
    #
    # 3. Trigger runs from anywhere:
    #    agentspan run financial_assistant_retry_demo "Check AAPL price"
