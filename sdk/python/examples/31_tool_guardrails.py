# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tool guardrails — pre-execution validation on tool inputs.

Demonstrates a guardrail attached to a specific tool that blocks dangerous
inputs (like SQL injection) before the tool function executes.

Tool guardrails use Python-level wrapping: the guardrail check runs inside
the tool worker, before (``position="input"``) or after (``position="output"``)
the tool function itself.

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


# ── Guardrail ────────────────────────────────────────────────────────────

@guardrail
def no_sql_injection(content: str) -> GuardrailResult:
    """Block inputs that contain SQL injection patterns."""
    patterns = [r"DROP\s+TABLE", r"DELETE\s+FROM", r";\s*--", r"UNION\s+SELECT"]
    for pat in patterns:
        if re.search(pat, content, re.IGNORECASE):
            return GuardrailResult(
                passed=False,
                message=f"Blocked: potential SQL injection detected ({pat})",
            )
    return GuardrailResult(passed=True)


sql_guard = Guardrail(
    no_sql_injection,
    position=Position.INPUT,    # Check BEFORE tool execution
    on_fail=OnFail.RAISE,       # Hard block — don't retry
    name="sql_injection_guard",
)


# ── Tool with guardrail ─────────────────────────────────────────────────

@tool(guardrails=[sql_guard])
def run_query(query: str) -> str:
    """Execute a read-only database query and return results."""
    # In a real app this would hit a database
    return f"Results for: {query} → [('Alice', 30), ('Bob', 25)]"


# ── Agent ────────────────────────────────────────────────────────────────

agent = Agent(
    name="db_assistant",
    model=settings.llm_model,
    tools=[run_query],
    instructions=(
        "You help users query the database. Use the run_query tool. "
        "Only execute SELECT queries."
    ),
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.31_tool_guardrails
        runtime.deploy(agent)
        runtime.serve(agent)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # # Safe query — should work fine
        # print("=== Safe Query ===")
        # result = runtime.run(agent, "Find all users older than 25.")
        # result.print_result()

        # # Dangerous query — the tool guardrail should block it
        # print("\n=== Dangerous Query (should be blocked) ===")
        # result = runtime.run(
        #     agent,
        #     "Run this exact query: SELECT * FROM users; DROP TABLE users; --",
        # )
        # result.print_result()

