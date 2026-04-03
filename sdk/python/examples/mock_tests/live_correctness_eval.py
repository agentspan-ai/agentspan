# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Live CorrectnessEval — run eval cases against a real server.

Demonstrates two approaches:

  1. **Manual** — hand-write EvalCase definitions with explicit expectations.
  2. **Auto-capture** — run the agent once, auto-generate EvalCase from the
     observed behavior, then replay as a regression test.

Unlike mock tests, this sends real prompts through the LLM and validates
the agent's behavior end-to-end.

Requirements:
    - A running Agentspan server (default: http://localhost:6767/api)
    - An LLM API key (e.g. OPENAI_API_KEY)
    - AGENTSPAN_LLM_MODEL env var (default: openai/gpt-4o-mini)

Run:
    cd sdk/python
    uv run python examples/mock_tests/live_correctness_eval.py
"""

import sys
import os

# Ensure the examples directory is on the path for settings import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agentspan.agents import Agent, AgentRuntime, tool
from agentspan.agents.testing import (
    CorrectnessEval,
    EvalCase,
    capture_eval_case,
    eval_case_from_result,
    record,
)
from settings import settings


# ── Tools ────────────────────────────────────────────────────────────


@tool
def get_weather(city: str) -> dict:
    """Get the current weather for a city."""
    return {"city": city, "temp_f": 72, "condition": "Sunny"}


@tool
def get_stock_price(symbol: str) -> dict:
    """Get the current stock price for a ticker symbol."""
    return {"symbol": symbol, "price": 182.50, "change": "+1.2%"}


# ── Agent ────────────────────────────────────────────────────────────

agent = Agent(
    name="weather_stock_agent",
    model=settings.llm_model,
    tools=[get_weather, get_stock_price],
    instructions="You are a helpful assistant. Use tools to answer questions about weather and stocks.",
)


# ═════════════════════════════════════════════════════════════════════
# 1. MANUAL — hand-written eval cases
# ═════════════════════════════════════════════════════════════════════

manual_cases = [
    EvalCase(
        name="weather_uses_correct_tool",
        agent=agent,
        prompt="What's the weather in San Francisco?",
        expect_tools=["get_weather"],
        expect_tools_not_used=["get_stock_price"],
        expect_output_contains=["72", "sunny"],
    ),
    EvalCase(
        name="stock_uses_correct_tool",
        agent=agent,
        prompt="What's the stock price for AAPL?",
        expect_tools=["get_stock_price"],
        expect_tools_not_used=["get_weather"],
        expect_output_contains=["182"],
    ),
    EvalCase(
        name="weather_passes_correct_args",
        agent=agent,
        prompt="What's the weather like in Tokyo?",
        expect_tools=["get_weather"],
        expect_tool_args={"get_weather": {"city": "Tokyo"}},
    ),
]


# ═════════════════════════════════════════════════════════════════════
# 2. AUTO-CAPTURE — generate eval cases from observed behavior
# ═════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        evaluator = CorrectnessEval(runtime)

        # ── Run manual cases ─────────────────────────────────────
        print(">>> Running manual eval cases...")
        manual_results = evaluator.run(manual_cases)
        manual_results.print_summary()

        # ── Auto-capture: run once, generate case, re-run as regression ──
        print(">>> Auto-capturing eval cases...")

        # Option A: capture_eval_case() — one-liner, runs + generates
        case1, result1 = capture_eval_case(
            runtime, agent, "What's the weather in Paris?"
        )
        print(f"  Captured: {case1.name}")
        print(f"    expect_tools={case1.expect_tools}")
        print(f"    expect_tool_args={case1.expect_tool_args}")
        print(f"    expect_status={case1.expect_status}")

        # Option B: eval_case_from_result() — from an existing result
        result2 = runtime.run(agent, "Check the stock price of TSLA")
        case2 = eval_case_from_result(
            result2,
            agent=agent,
            prompt="Check the stock price of TSLA",
            name="tsla_stock_check",
            tags=["captured", "stock"],
        )
        print(f"  Captured: {case2.name}")
        print(f"    expect_tools={case2.expect_tools}")
        print(f"    expect_tool_args={case2.expect_tool_args}")

        # Optionally save the result as a fixture for replay
        record(result2, "tests/recordings/tsla_stock.json")
        print("  Saved fixture: tests/recordings/tsla_stock.json")

        # ── Re-run captured cases as regression tests ────────────
        print("\n>>> Running captured cases as regression tests...")
        captured_results = evaluator.run([case1, case2])
        captured_results.print_summary()

        all_passed = manual_results.all_passed and captured_results.all_passed
        if not all_passed:
            sys.exit(1)
