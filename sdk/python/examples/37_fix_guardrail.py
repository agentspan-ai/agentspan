# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Fix guardrail — auto-correct output instead of retrying.

Demonstrates ``on_fail="fix"``: when the guardrail fails, it provides a
corrected version of the output via ``GuardrailResult.fixed_output``.
The workflow uses the fixed output directly without calling the LLM again.

This is useful when the correction is deterministic (e.g. stripping PII,
truncating, formatting) — faster and cheaper than retry since no LLM
round-trip is needed.

Comparison of on_fail modes:
    - ``OnFail.RETRY``  — send feedback to LLM and regenerate (best for style issues)
    - ``OnFail.FIX``    — replace output with ``fixed_output`` (best for deterministic fixes)
    - ``OnFail.RAISE``  — terminate the workflow with an error
    - ``OnFail.HUMAN``  — pause for human review (see example 32)

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
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


# ── Fix guardrail: redact phone numbers ──────────────────────────────
# Instead of asking the LLM to retry, this guardrail redacts phone
# numbers directly and returns the cleaned output.

@guardrail
def redact_phone_numbers(content: str) -> GuardrailResult:
    """Redact US phone numbers from the output."""
    phone_pattern = r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"

    if re.search(phone_pattern, content):
        redacted = re.sub(phone_pattern, "[PHONE REDACTED]", content)
        return GuardrailResult(
            passed=False,
            message="Phone numbers detected and redacted.",
            fixed_output=redacted,
        )
    return GuardrailResult(passed=True)


# ── Tool ─────────────────────────────────────────────────────────────

@tool
def get_contact_info(name: str) -> dict:
    """Look up contact information for a person."""
    contacts = {
        "alice": {
            "name": "Alice Johnson",
            "email": "alice@example.com",
            "phone": "(555) 123-4567",
            "department": "Engineering",
        },
        "bob": {
            "name": "Bob Smith",
            "email": "bob@example.com",
            "phone": "555-987-6543",
            "department": "Marketing",
        },
    }
    key = name.lower().split()[0]
    return contacts.get(key, {"error": f"No contact found for '{name}'"})


# ── Agent ────────────────────────────────────────────────────────────

agent = Agent(
    name="directory_agent",
    model=settings.llm_model,
    tools=[get_contact_info],
    instructions=(
        "You are a company directory assistant. When asked about employees, "
        "look up their contact info and share everything you find."
    ),
    guardrails=[
        Guardrail(
            redact_phone_numbers,
            position=Position.OUTPUT,
            on_fail=OnFail.FIX,      # Auto-correct instead of retry
            name="phone_redactor",
        ),
    ],
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # ── Scenario 1: Guardrail TRIGGERS — contact has phone number ─────
        print("=" * 60)
        print("  Scenario 1: Contact with phone number (guardrail triggers)")
        print("=" * 60)
        result = runtime.run(
            agent,
            "What's Alice Johnson's contact information?",
        )
        result.print_result()

        output = str(result.output)
        if "(555) 123-4567" in output or "555-123-4567" in output:
            print("[FAIL] Phone number leaked through the guardrail!")
        elif "[PHONE REDACTED]" in output:
            print("[OK] Phone number was auto-redacted by fix guardrail")
        else:
            print("[OK] No phone number in output")

        # ── Scenario 2: Guardrail does NOT trigger — no phone in response ─
        print("\n" + "=" * 60)
        print("  Scenario 2: General question (guardrail does not trigger)")
        print("=" * 60)
        result2 = runtime.run(
            agent,
            "What department does Alice work in? Just the department name.",
        )
        result2.print_result()

        output2 = str(result2.output)
        if "[PHONE REDACTED]" in output2:
            print("[WARN] Unexpected redaction in clean response")
        else:
            print("[OK] No redaction needed — guardrail passed cleanly")

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.37_fix_guardrail
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)

