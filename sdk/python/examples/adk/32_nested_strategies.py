# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Google ADK Nested Strategies — ParallelAgent inside SequentialAgent.

Demonstrates composing agent strategies: parallel research runs
concurrently, then results flow into a sequential summarizer.

Requirements:
    - pip install google-adk
    - Conductor server
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=google_gemini/gemini-2.0-flash as environment variable
"""

from google.adk.agents import Agent, ParallelAgent, SequentialAgent

from agentspan.agents import AgentRuntime

from settings import settings

# ── Parallel research agents ───────────────────────────────────────

market_analyst = Agent(
    name="market_analyst",
    model=settings.llm_model,
    instruction=(
        "You are a market analyst. Analyze the market size, growth rate, "
        "and key players for the given topic. Be concise (3-4 bullet points)."
    ),
)

risk_analyst = Agent(
    name="risk_analyst",
    model=settings.llm_model,
    instruction=(
        "You are a risk analyst. Identify the top 3 risks: regulatory, "
        "technical, and competitive. Be concise."
    ),
)

# Both run concurrently
parallel_research = ParallelAgent(
    name="research_phase",
    sub_agents=[market_analyst, risk_analyst],
)

# ── Summarizer ─────────────────────────────────────────────────────

summarizer = Agent(
    name="summarizer",
    model=settings.llm_model,
    instruction=(
        "You are an executive briefing writer. Synthesize the market analysis "
        "and risk assessment into a concise executive summary (1 paragraph)."
    ),
)

# ── Pipeline: parallel → sequential ────────────────────────────────

pipeline = SequentialAgent(
    name="analysis_pipeline",
    sub_agents=[parallel_research, summarizer],
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
        pipeline,
        "Launching an AI-powered healthcare diagnostics tool in the US",
        )
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(pipeline)
        # CLI alternative:
        # agentspan deploy --package examples.adk.32_nested_strategies
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(pipeline)
