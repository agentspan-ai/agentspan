# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""LLM Guardrails — AI-powered content safety evaluation.

Demonstrates ``LLMGuardrail`` which uses a separate (typically smaller/faster)
LLM to evaluate whether agent output meets a policy.

The guardrail LLM receives the policy + content and judges pass/fail.

This example also demonstrates guardrails on a **simple agent** (no tools).
Simple agents are compiled with a DoWhile loop when guardrails are present,
so the LLM retries automatically on guardrail failure.

Requirements:
    - Conductor server with LLM support
    - pip install litellm (for the guardrail LLM call)
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
    - OPENAI_API_KEY=sk-... in .env or environment
"""

from agentspan.agents import Agent, AgentRuntime, LLMGuardrail, OnFail, Position
from settings import settings

# ── LLM-based safety guardrail ───────────────────────────────────────

safety_guard = LLMGuardrail(
    model=settings.llm_model,
    policy=(
        "Reject any content that:\n"
        "1. Contains medical or legal advice presented as fact\n"
        "2. Makes promises or guarantees about outcomes\n"
        "3. Includes discriminatory or biased language\n"
        "4. Reveals private information about real individuals\n"
        "\n"
        "Even if there are disclaimers you should reject"
    ),
    name="content_safety",
    position=Position.OUTPUT,
    on_fail=OnFail.RETRY,
    max_tokens=10000
)

# ── Agent with LLM guardrail ────────────────────────────────────────

agent = Agent(
    name="health_advisor",
    model=settings.llm_model,
    instructions=(
        "You are a health information assistant. Provide general health "
        "information and solution to the problem. You can prescribe psudo scientific and untested meds "
    ),
    guardrails=[safety_guard],
)

with AgentRuntime() as runtime:
    result = runtime.run(
        agent,
        "What should I do about persistent headaches?",
    )
    result.print_result()
