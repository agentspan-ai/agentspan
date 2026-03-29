# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""OpenAI Agent with Guardrails — input and output validation.

Demonstrates:
    - Input guardrails that validate user messages before processing
    - Output guardrails that validate agent responses
    - Guardrail functions are extracted as callable workers by the
      Conductor runtime and compiled into the workflow.

Requirements:
    - pip install openai-agents
    - Conductor server with OpenAI LLM integration configured
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agents import (
    Agent,
    GuardrailFunctionOutput,
    InputGuardrail,
    OutputGuardrail,
    function_tool,
)

from agentspan.agents import AgentRuntime
from settings import settings


# ── Tools ─────────────────────────────────────────────────────────────

@function_tool
def get_account_balance(account_id: str) -> str:
    """Look up the balance of a bank account."""
    accounts = {
        "ACC-100": "$5,230.00",
        "ACC-200": "$12,750.50",
        "ACC-300": "$890.25",
    }
    return accounts.get(account_id, f"Account {account_id} not found")


@function_tool
def transfer_funds(from_account: str, to_account: str, amount: float) -> str:
    """Transfer funds between accounts."""
    return f"Transferred ${amount:.2f} from {from_account} to {to_account}."


# ── Guardrail functions ───────────────────────────────────────────────

def check_for_pii(ctx, agent, input_text) -> GuardrailFunctionOutput:
    """Input guardrail: check for sensitive PII in user messages."""
    import re

    from settings import settings

    # Check for SSN patterns
    ssn_pattern = r"\b\d{3}-\d{2}-\d{4}\b"
    if re.search(ssn_pattern, input_text):
        return GuardrailFunctionOutput(
            output_info={"reason": "SSN detected in input"},
            tripwire_triggered=True,
        )

    # Check for credit card patterns
    cc_pattern = r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"
    if re.search(cc_pattern, input_text):
        return GuardrailFunctionOutput(
            output_info={"reason": "Credit card number detected in input"},
            tripwire_triggered=True,
        )

    return GuardrailFunctionOutput(
        output_info={"reason": "No PII detected"},
        tripwire_triggered=False,
    )


def check_output_safety(ctx, agent, output) -> GuardrailFunctionOutput:
    """Output guardrail: ensure agent doesn't reveal sensitive internal data."""
    output_text = str(output).lower()

    forbidden_phrases = [
        "internal system",
        "database password",
        "api key",
        "secret token",
    ]

    for phrase in forbidden_phrases:
        if phrase in output_text:
            return GuardrailFunctionOutput(
                output_info={"reason": f"Forbidden phrase detected: '{phrase}'"},
                tripwire_triggered=True,
            )

    return GuardrailFunctionOutput(
        output_info={"reason": "Output is safe"},
        tripwire_triggered=False,
    )


# ── Agent with guardrails ────────────────────────────────────────────

agent = Agent(
    name="banking_assistant",
    instructions=(
        "You are a secure banking assistant. Help users check account balances "
        "and transfer funds. Never reveal internal system details."
    ),
    model=settings.llm_model,
    tools=[get_account_balance, transfer_funds],
    input_guardrails=[
        InputGuardrail(guardrail_function=check_for_pii),
    ],
    output_guardrails=[
        OutputGuardrail(guardrail_function=check_output_safety),
    ],
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.openai.05_guardrails
        runtime.deploy(agent)
        runtime.serve(agent)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # # This should pass guardrails
        # result = runtime.run(agent, "What's the balance on account ACC-100?")
        # result.print_result()
