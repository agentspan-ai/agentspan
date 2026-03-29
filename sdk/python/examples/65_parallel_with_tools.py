# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Parallel Agents with Tools — each branch has its own tools.

Extends the basic parallel pattern (example 07) by giving each parallel
branch its own domain tools. All branches run concurrently and each
independently calls its tools.

Architecture:
    parallel_analysis
    ├── financial_analyst  (tools: [check_balance])
    └── order_analyst      (tools: [lookup_order])

Both analysts run at the same time on the same input. Their results
are aggregated by the parent.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

from agentspan.agents import Agent, AgentRuntime, Strategy, tool
from settings import settings


# ── Domain tools ────────────────────────────────────────────────────

@tool
def check_balance(account_id: str) -> dict:
    """Check the balance of a bank account."""
    return {"account_id": account_id, "balance": 5432.10, "currency": "USD"}


@tool
def lookup_order(order_id: str) -> dict:
    """Look up the status of an order."""
    return {"order_id": order_id, "status": "shipped", "eta": "2 days"}


# ── Parallel agents with tools ─────────────────────────────────────

financial_analyst = Agent(
    name="financial_analyst",
    model=settings.llm_model,
    instructions=(
        "You are a financial analyst. Use check_balance to look up the "
        "account mentioned. Report the balance and any financial observations."
    ),
    tools=[check_balance],
)

order_analyst = Agent(
    name="order_analyst",
    model=settings.llm_model,
    instructions=(
        "You are an order analyst. Use lookup_order to check the order "
        "mentioned. Report the status and delivery timeline."
    ),
    tools=[lookup_order],
)

# Both analysts run concurrently
analysis = Agent(
    name="parallel_analysis",
    model=settings.llm_model,
    agents=[financial_analyst, order_analyst],
    strategy=Strategy.PARALLEL,
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.65_parallel_with_tools
        runtime.deploy(analysis)
        runtime.serve(analysis)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(
        #     analysis,
        #     "Check account ACC-200 balance and look up order ORD-300 status.",
        # )
        # result.print_result()

        # output = str(result.output)
        # checks = []
        # if "5432" in output:
        #     checks.append("[OK] Financial analyst retrieved balance")
        # else:
        #     checks.append("[WARN] Expected balance in output")
        # if "shipped" in output.lower():
        #     checks.append("[OK] Order analyst retrieved order status")
        # else:
        #     checks.append("[WARN] Expected order status in output")
        # for c in checks:
        #     print(c)

