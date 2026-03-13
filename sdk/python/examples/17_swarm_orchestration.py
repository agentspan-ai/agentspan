# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Swarm Orchestration — automatic agent transitions via transfer tools.

Demonstrates ``strategy="swarm"`` with LLM-driven, tool-based handoffs.
Each agent gets ``transfer_to_<peer>`` tools and the LLM decides when to
hand off by calling the appropriate transfer tool.

Condition-based handoffs (OnTextMention, etc.) remain as optional fallback
when no transfer tool is called.

Flow:
    1. Parent support agent triages the initial request (runs as agent "0")
    2. Support agent sees tools: [transfer_to_refund_specialist, transfer_to_tech_support]
    3. LLM calls transfer_to_refund_specialist() → inner loop exits
    4. Handoff check detects transfer → active_agent switches to "1"
    5. Refund specialist handles the request (no transfer) → loop exits
    6. Output: refund specialist's clean response

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

from agentspan.agents import Agent, AgentRuntime, Strategy
from settings import settings
from agentspan.agents.handoff import OnTextMention

# ── Specialist agents ────────────────────────────────────────────────

refund_agent = Agent(
    name="refund_specialist",
    model=settings.llm_model,
    instructions=(
        "You are a refund specialist. Process the customer's refund request. "
        "Check eligibility, confirm the refund amount, and let them know the "
        "timeline. Be empathetic and clear. Do NOT ask follow-up questions — "
        "just process the refund based on what the customer told you."
    ),
)

tech_agent = Agent(
    name="tech_support",
    model=settings.llm_model,
    instructions=(
        "You are a technical support specialist. Diagnose the customer's "
        "technical issue and provide clear troubleshooting steps."
    ),
)

# ── Front-line support agent with swarm handoffs ─────────────────────

support = Agent(
    name="support",
    model=settings.llm_model,
    instructions=(
        "You are the front-line customer support agent. Triage customer requests. "
        "If the customer needs a refund, transfer to the refund specialist. "
        "If they have a technical issue, transfer to tech support. "
        "Use the transfer tools available to you to hand off the conversation."
    ),
    agents=[refund_agent, tech_agent],
    strategy=Strategy.SWARM,
    handoffs=[
        # Fallback condition-based handoffs (evaluated only if no transfer tool was called)
        OnTextMention(text="refund", target="refund_specialist"),
        OnTextMention(text="technical", target="tech_support"),
    ],
    max_turns=3,
)

with AgentRuntime() as runtime:
    print("--- Refund scenario ---")
    result = runtime.run(
        support,
        "I bought a product last week and it arrived damaged. I want my money back.",
    )
    result.print_result()
