# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Nested Strategies — parallel agents inside a sequential pipeline.

Demonstrates composing strategies: a ParallelAgent phase runs multiple
research agents concurrently, followed by a sequential summarizer.

    pipeline = parallel_research >> summarizer

Requirements:
    - Conductor server
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

from agentspan.agents import Agent, AgentRuntime
from settings import settings

# ── Parallel research phase ────────────────────────────────────────

market_analyst = Agent(
    name="market_analyst_52",
    model=settings.llm_model,
    instructions=(
        "You are a market analyst. Analyze the market size, growth rate, "
        "and key players for the given topic. Be concise (3-4 bullet points)."
    ),
)

risk_analyst = Agent(
    name="risk_analyst_52",
    model=settings.llm_model,
    instructions=(
        "You are a risk analyst. Identify the top 3 risks: regulatory, "
        "technical, and competitive. Be concise."
    ),
)

# Both analysts run concurrently
parallel_research = Agent(
    name="research_phase_52",
    model=settings.llm_model,
    agents=[market_analyst, risk_analyst],
    strategy="parallel",
)

# ── Sequential summarizer ──────────────────────────────────────────

summarizer = Agent(
    name="summarizer_52",
    model=settings.llm_model,
    instructions=(
        "You are an executive briefing writer. Synthesize the market analysis "
        "and risk assessment into a concise executive summary (1 paragraph)."
    ),
)

# ── Pipeline: parallel research → summary ──────────────────────────
pipeline = parallel_research >> summarizer

with AgentRuntime() as runtime:
    result = runtime.run(pipeline, "Launching an AI-powered healthcare diagnostics tool in the US")
    result.print_result()
