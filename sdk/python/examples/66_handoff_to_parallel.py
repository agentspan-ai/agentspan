# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Handoff to Parallel — delegate to a multi-agent group.

Demonstrates a parent agent that can hand off to either a single agent
(for quick checks) or a parallel multi-agent group (for deep analysis).
The parallel sub-agent runs its own fan-out/fan-in internally.

Architecture:
    coordinator (HANDOFF)
    ├── quick_check           (single agent, fast)
    └── deep_analysis         (PARALLEL group)
        ├── market_analyst
        └── risk_analyst

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api in .env or environment
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

from agentspan.agents import Agent, AgentRuntime, Strategy
from settings import settings


# ── Quick check (single agent) ──────────────────────────────────────

quick_check = Agent(
    name="quick_check",
    model=settings.llm_model,
    instructions=(
        "You provide quick, 1-sentence assessments. Be brief and direct."
    ),
)

# ── Deep analysis (parallel group) ──────────────────────────────────

market_analyst = Agent(
    name="market_analyst_66",
    model=settings.llm_model,
    instructions=(
        "You are a market analyst. Analyze the market opportunity: "
        "size, growth rate, key players. 3-4 bullet points."
    ),
)

risk_analyst = Agent(
    name="risk_analyst_66",
    model=settings.llm_model,
    instructions=(
        "You are a risk analyst. Identify the top 3 risks: "
        "regulatory, technical, and competitive. 3-4 bullet points."
    ),
)

deep_analysis = Agent(
    name="deep_analysis",
    model=settings.llm_model,
    agents=[market_analyst, risk_analyst],
    strategy=Strategy.PARALLEL,
)

# ── Coordinator with handoff ────────────────────────────────────────

coordinator = Agent(
    name="coordinator_66",
    model=settings.llm_model,
    instructions=(
        "You are a business strategist. Route requests to the right team:\n"
        "- quick_check for simple yes/no questions or quick assessments\n"
        "- deep_analysis for comprehensive analysis requiring multiple perspectives"
    ),
    agents=[quick_check, deep_analysis],
    strategy=Strategy.HANDOFF,
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # ── Scenario 1: Deep analysis (handoff to parallel group)
        print("=" * 60)
        print("  Scenario 1: Deep analysis (handoff → parallel group)")
        print("=" * 60)
        result = runtime.run(
            coordinator,
            "Provide a deep analysis of entering the AI healthcare market.",
        )
        result.print_result()

        if result.status == "COMPLETED":
            print("[OK] Handoff to parallel group completed successfully")
        else:
            print(f"[WARN] Unexpected status: {result.status}")

        # ── Scenario 2: Quick check (handoff to single agent)
        print("\n" + "=" * 60)
        print("  Scenario 2: Quick check (handoff → single agent)")
        print("=" * 60)
        result2 = runtime.run(
            coordinator,
            "Is the mobile app market still growing?",
        )
        result2.print_result()

        if result2.status == "COMPLETED":
            print("[OK] Quick check completed successfully")
        else:
            print(f"[WARN] Unexpected status: {result2.status}")

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(coordinator)
        # CLI alternative:
        # agentspan deploy --package examples.66_handoff_to_parallel
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(coordinator)

