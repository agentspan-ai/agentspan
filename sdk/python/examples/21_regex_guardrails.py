# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Regex Guardrails — pattern-based content validation.

Demonstrates ``RegexGuardrail`` for blocking or allowing content based
on regex patterns.

Examples:
    - Block mode: reject responses containing email addresses or SSNs
    - Allow mode: require responses to be valid JSON

RegexGuardrails compile to Conductor **InlineTasks** — the regex patterns
are evaluated server-side in JavaScript (GraalVM), so no Python worker
process is needed.  This makes them lightweight and fast.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

from agentspan.agents import Agent, AgentRuntime, OnFail, Position, RegexGuardrail, tool
from settings import settings


# ── Block mode: reject responses with PII ────────────────────────────

no_emails = RegexGuardrail(
    patterns=[r"[\w.+-]+@[\w-]+\.[\w.-]+"],
    mode="block",
    name="no_email_addresses",
    message="Response must not contain email addresses. Redact them.",
    position=Position.OUTPUT,
    on_fail=OnFail.RETRY,
)

no_ssn = RegexGuardrail(
    patterns=[r"\b\d{3}-\d{2}-\d{4}\b"],
    mode="block",
    name="no_ssn",
    message="Response must not contain Social Security Numbers.",
    position=Position.OUTPUT,
    on_fail=OnFail.RAISE,
)

# ── Agent with PII-blocking guardrails ───────────────────────────────

@tool
def get_user_profile(user_id: str) -> dict:
    """Retrieve a user's profile from the database."""
    return {
        "name": "Alice Johnson",
        "email": "alice.johnson@example.com",  # PII - should be blocked
        "ssn": "123-45-6789",                  # PII - should be blocked
        "department": "Engineering",
        "role": "Senior Developer",
    }

agent = Agent(
    name="hr_assistant",
    model=settings.llm_model,
    tools=[get_user_profile],
    instructions=(
        "You are an HR assistant. When asked about employees, look up their "
        "profile and share ALL the details you find."
    ),
    guardrails=[no_emails, no_ssn],
)

with AgentRuntime() as runtime:
    result = runtime.run(
        agent,
        "Tell me everything about user U-001.",
    )
    result.print_result()

    # Verify PII was blocked
    output = str(result.output)
    if "alice.johnson@example.com" in output:
        print("[WARN] Email leaked!")
    else:
        print("[OK] Email was blocked by RegexGuardrail")
