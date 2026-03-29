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
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
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


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.21_regex_guardrails
        runtime.deploy(agent)
        runtime.serve(agent)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # # ── Scenario 1: Guardrail TRIGGERS — PII in tool output ───────────
        # print("=" * 60)
        # print("  Scenario 1: Request PII — guardrails trigger")
        # print("=" * 60)
        # result = runtime.run(
        #     agent,
        #     "Tell me everything about user U-001.",
        # )
        # result.print_result()

        # output = str(result.output)
        # if "alice.johnson@example.com" in output:
        #     print("[FAIL] Email leaked!")
        # else:
        #     print("[OK] Email was blocked by RegexGuardrail")

        # if "123-45-6789" in output:
        #     print("[FAIL] SSN leaked!")
        # else:
        #     print("[OK] SSN was blocked by RegexGuardrail")

        # # ── Scenario 2: Guardrail does NOT trigger — no PII ───────────────
        # print("\n" + "=" * 60)
        # print("  Scenario 2: Non-PII question — guardrails pass")
        # print("=" * 60)

        # # New agent without PII-returning tool
        # clean_agent = Agent(
        #     name="dept_assistant",
        #     model=settings.llm_model,
        #     instructions="You are an HR assistant. Answer questions about departments.",
        #     guardrails=[no_emails, no_ssn],
        # )
        # result2 = runtime.run(clean_agent, "What departments exist at the company?")
        # result2.print_result()

        # if result2.status == "COMPLETED":
        #     print("[OK] Clean response passed guardrails successfully")
        # else:
        #     print(f"[WARN] Unexpected status: {result2.status}")

