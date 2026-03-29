# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Parallel Agents — fan-out / fan-in.

Demonstrates the parallel strategy where all sub-agents run concurrently
on the same input and their results are aggregated.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import Agent, AgentRuntime, Strategy
from settings import settings

# ── Specialist analysts ─────────────────────────────────────────────

market_analyst = Agent(
    name="market_analyst",
    model=settings.llm_model,
    instructions=(
        "You are a market analyst. Analyze the given topic from a market perspective: "
        "market size, growth trends, key players, and opportunities."
    ),
)

risk_analyst = Agent(
    name="risk_analyst",
    model=settings.llm_model,
    instructions=(
        "You are a risk analyst. Analyze the given topic for risks: "
        "regulatory risks, technical risks, competitive threats, and mitigation strategies."
    ),
)

compliance_checker = Agent(
    name="compliance",
    model=settings.llm_model,
    instructions=(
        "You are a compliance specialist. Check the given topic for compliance considerations: "
        "data privacy, regulatory requirements, and industry standards."
    ),
)

# ── Parallel analysis ───────────────────────────────────────────────

analysis = Agent(
    name="analysis",
    model=settings.llm_model,
    agents=[market_analyst, risk_analyst, compliance_checker],
    strategy=Strategy.PARALLEL,
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.07_parallel_agents
        runtime.deploy(analysis)
        runtime.serve(analysis)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(analysis, "Launching an AI-powered healthcare diagnostic tool in the US market")
        # result.print_result()

