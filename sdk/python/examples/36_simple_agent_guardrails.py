# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Simple agent guardrails — output validation without tools.

Demonstrates guardrails on a **simple agent** (no tools, no sub-agents).
The agent is compiled with a DoWhile loop that retries the LLM call when
a guardrail fails — same durable retry behavior as tool-using agents.

This example uses mixed guardrail types:

- ``RegexGuardrail`` — compiled as a Conductor InlineTask (server-side
  JavaScript, no Python worker needed)
- Custom ``@guardrail`` function — compiled as a Conductor worker task
  (runs in the SDK's worker process)

Both guardrails run inside the same DoWhile loop.  If either fails with
``on_fail="retry"``, the feedback message is appended to the conversation
and the LLM tries again.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import (
    Agent,
    AgentRuntime,
    Guardrail,
    GuardrailResult,
    OnFail,
    RegexGuardrail,
    guardrail,
)
from settings import settings


# ── RegexGuardrail: block bullet-point lists ─────────────────────────
# Compiles as an InlineTask — runs entirely on the Conductor server.

no_bullet_lists = RegexGuardrail(
    patterns=[r"^\s*[-*]\s", r"^\s*\d+\.\s"],
    mode="block",
    name="no_lists",
    message=(
        "Do not use bullet points or numbered lists. "
        "Write in flowing prose paragraphs instead."
    ),
    on_fail=OnFail.RETRY,
    max_retries=3,
)


# ── Custom guardrail: enforce minimum length ────────────────────────
# Compiles as a Conductor worker task (Python function).

@guardrail
def min_length(content: str) -> GuardrailResult:
    """Require at least 50 words in the response."""
    word_count = len(content.split())
    if word_count < 50:
        return GuardrailResult(
            passed=False,
            message=(
                f"Response is too short ({word_count} words). "
                "Please provide a more detailed answer with at least 50 words."
            ),
        )
    return GuardrailResult(passed=True)


# ── Agent (no tools) ────────────────────────────────────────────────

agent = Agent(
    name="essay_writer",
    model=settings.llm_model,
    instructions=(
        "You are a concise essay writer. Answer the user's question in "
        "well-structured prose paragraphs. Do NOT use bullet points or "
        "numbered lists."
    ),
    guardrails=[
        no_bullet_lists,
        Guardrail(min_length, on_fail=OnFail.RETRY),
    ],
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.36_simple_agent_guardrails
        runtime.deploy(agent)
        runtime.serve(agent)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(
        #     agent,
        #     "Explain why the sky is blue.",
        # )
        # result.print_result()

        # # Verify guardrails
        # output = str(result.output)
        # has_bullets = any(
        #     line.strip().startswith(("-", "*"))
        #     for line in output.splitlines()
        # )
        # word_count = len(output.split())

        # if has_bullets:
        #     print("[WARN] Output contains bullet points — guardrail may not have fired")
        # elif word_count < 50:
        #     print(f"[WARN] Output too short ({word_count} words)")
        # else:
        #     print(f"[OK] Prose response, {word_count} words — guardrails passed")

