# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Human-in-the-loop guardrail — ``on_fail="human"``.

Demonstrates a guardrail that pauses the workflow for human review when
the output fails validation.  The human can approve, reject, or edit.

Since the workflow pauses at a HumanTask, this example uses ``start()``
(async) instead of ``run()`` (blocking).

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

import time

from agentspan.agents import (
    Agent,
    AgentRuntime,
    Guardrail,
    GuardrailResult,
    OnFail,
    Position,
    guardrail,
    tool,
)
from settings import settings


# ── Guardrail ────────────────────────────────────────────────────────────

@guardrail
def compliance_check(content: str) -> GuardrailResult:
    """Flag any response that mentions specific financial terms for review."""
    flagged_terms = ["investment advice", "guaranteed returns", "risk-free"]
    for term in flagged_terms:
        if term.lower() in content.lower():
            return GuardrailResult(
                passed=False,
                message=f"Response contains flagged term: '{term}'. Needs human review.",
            )
    return GuardrailResult(passed=True)


# ── Tool ─────────────────────────────────────────────────────────────────

@tool
def get_market_data(ticker: str) -> dict:
    """Get current market data for a stock ticker."""
    return {
        "ticker": ticker,
        "price": 185.42,
        "change": "+2.3%",
        "volume": "45.2M",
    }


# ── Agent ────────────────────────────────────────────────────────────────

agent = Agent(
    name="finance_agent",
    model=settings.llm_model,
    tools=[get_market_data],
    instructions=(
        "You are a financial information assistant. Provide market data "
        "and general financial information. You may discuss investment "
        "strategies and returns."
    ),
    guardrails=[
        Guardrail(
            compliance_check,
            position=Position.OUTPUT,
            on_fail=OnFail.HUMAN,
            name="compliance",
        ),
    ],
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(agent, "Look up AAPL and summarize the latest price movement.")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.32_human_guardrail
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)

        # Interactive human-review alternative:
        # # Start the agent (async — doesn't block)
        # handle = runtime.start(
        #     agent,
        #     "Look up AAPL and explain whether it's a good investment. "
        #     "Include your opinion on potential returns.",
        # )
        # print(f"Workflow started: {handle.execution_id}")

        # # Poll for status
        # for i in range(60):
        #     status = handle.get_status()
        #     print(f"  Status: {status.status} (waiting={status.is_waiting})")

        #     if status.is_waiting:
        #         print("\n--- Workflow paused for human review ---")
        #         print("The guardrail flagged the response for compliance review.")
        #         print("Options: approve(), reject(reason), or respond(output)")

        #         # In a real app, a human would review in the Conductor UI.
        #         # Here we auto-approve for the demo.
        #         print("Auto-approving for demo...")
        #         runtime.reject(handle.execution_id, "bad idea")
        #         print("Approved! Resuming workflow...\n")

        #     if status.is_complete:
        #         print(f"\nFinal output: {status.output}")
        #         break

        #     time.sleep(1)
        # else:
        #     print("Timed out waiting for workflow to complete")
        #     runtime.cancel(handle.execution_id)

