# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Guardrails — output validation with tool calls.

Demonstrates a guardrail that catches PII leaking from tool results into
the agent's final answer.  The agent uses two tools:

1. get_order_status  — returns safe order data (no PII)
2. get_customer_info — returns data that includes a credit card number

The PII guardrail checks the agent's final output.  If the agent includes
the raw credit card number in its response, the guardrail fails with
on_fail="retry" — the agent retries with feedback asking it to redact
the PII.

For agents with tools, guardrails are compiled into the Conductor DoWhile
loop as durable workflow tasks.  This means:
- Guardrail retries happen inside the workflow (no full re-execution)
- Guardrails are visible in the Conductor UI
- They work with ``start()`` and ``stream()`` (not just ``run()``)

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

import re

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


# ── Tools ─────────────────────────────────────────────────────────────

@tool
def get_order_status(order_id: str) -> dict:
    """Look up the current status of an order."""
    return {
        "order_id": order_id,
        "status": "shipped",
        "tracking": "1Z999AA10123456784",
        "estimated_delivery": "2026-02-22",
    }


@tool
def get_customer_info(customer_id: str) -> dict:
    """Retrieve customer details including payment info on file."""
    # This tool returns data with PII — the guardrail should catch it
    # if the agent includes it verbatim in the response.
    return {
        "customer_id": customer_id,
        "name": "Alice Johnson",
        "email": "alice@example.com",
        "card_on_file": "4532-0150-1234-5678",  # PII!
        "membership": "gold",
    }


# ── Guardrail (using @guardrail decorator) ────────────────────────────

@guardrail
def no_pii(content: str) -> GuardrailResult:
    """Reject responses that contain credit card numbers or SSNs."""
    cc_pattern = r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"
    ssn_pattern = r"\b\d{3}-\d{2}-\d{4}\b"

    if re.search(cc_pattern, content) or re.search(ssn_pattern, content):
        return GuardrailResult(
            passed=False,
            message=(
                "Your response contains PII (credit card or SSN). "
                "Redact all card numbers and SSNs before responding."
            ),
        )
    return GuardrailResult(passed=True)


# ── Agent ─────────────────────────────────────────────────────────────

agent = Agent(
    name="support_agent",
    model=settings.llm_model,
    tools=[get_order_status, get_customer_info],
    instructions=(
        "You are a customer support assistant. Use the available tools to "
        "answer questions about orders and customers. Always include all "
        "details from the tool results in your response."
        # ^^^ This instruction deliberately encourages the agent to include
        # raw tool output, which will trigger the guardrail on the second
        # tool call's PII data.
    ),
    guardrails=[
        Guardrail(no_pii, position=Position.OUTPUT, on_fail=OnFail.RETRY),
    ],
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.10_guardrails
        runtime.deploy(agent)
        runtime.serve(agent)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # # This prompt triggers both tools:
        # #   1. get_order_status("ORD-42")   → safe data, passes guardrail
        # #   2. get_customer_info("CUST-7")  → contains credit card, trips guardrail
        # result = runtime.run(
        #     agent,
        #     "I need a full summary: What's the status of order ORD-42, "
        #     "and what's the profile for customer CUST-7?"
        # )
        # result.print_result()

        # # Verify the guardrail worked — no raw card number in the output
        # if result.output and "4532-0150-1234-5678" in str(result.output):
        #     print("[WARN] PII leaked through the guardrail!")
        # else:
        #     print("[OK] PII was redacted from the final output.")

