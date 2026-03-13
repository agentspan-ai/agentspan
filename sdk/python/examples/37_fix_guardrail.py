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
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
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


with AgentRuntime() as runtime:
    result = runtime.run(
        agent,
        "What's Alice Johnson's contact information?",
    )
    result.print_result()

    # Verify the fix guardrail worked
    output = str(result.output)
    if "(555) 123-4567" in output or "555-123-4567" in output:
        print("[WARN] Phone number leaked through the guardrail!")
    elif "[PHONE REDACTED]" in output:
        print("[OK] Phone number was auto-redacted by fix guardrail")
    else:
        print("[OK] No phone number in output")
