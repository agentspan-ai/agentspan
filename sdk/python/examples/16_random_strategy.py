# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Random Strategy — random agent selection each turn.

Demonstrates the ``strategy="random"`` pattern where a random sub-agent
is selected each iteration.  Unlike round-robin (fixed rotation), random
selection adds variety — useful for brainstorming or diverse perspectives.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import Agent, AgentRuntime, Strategy
from settings import settings

creative = Agent(
    name="creative",
    model=settings.llm_model,
    instructions=(
        "You are a creative thinker. Suggest innovative, unconventional ideas. "
        "Keep your response to 2-3 sentences."
    ),
)

practical = Agent(
    name="practical",
    model=settings.llm_model,
    instructions=(
        "You are a practical thinker. Focus on feasibility and cost-effectiveness. "
        "Keep your response to 2-3 sentences."
    ),
)

critical = Agent(
    name="critical",
    model=settings.llm_model,
    instructions=(
        "You are a critical thinker. Identify risks and potential issues. "
        "Keep your response to 2-3 sentences."
    ),
)

# Random selection: each turn, one of the three agents is picked at random
brainstorm = Agent(
    name="brainstorm",
    model=settings.llm_model,
    agents=[creative, practical, critical],
    strategy=Strategy.RANDOM,
    max_turns=6,
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            brainstorm,
            "How should we approach building an AI-powered customer service platform?",
        )
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(brainstorm)
        # CLI alternative:
        # agentspan deploy --package examples.16_random_strategy
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(brainstorm)

