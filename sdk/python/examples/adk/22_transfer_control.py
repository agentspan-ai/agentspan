# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Google ADK Transfer Control — restricted agent handoffs.

Demonstrates:
    - disallow_transfer_to_parent: prevents sub-agent from returning to parent
    - disallow_transfer_to_peers: prevents sub-agent from transferring to siblings
    - These map to allowedTransitions in the Conductor workflow

Architecture:
    coordinator (parent)
      sub_agents:
        - specialist_a (can only talk to specialist_b, not parent)
        - specialist_b (can talk to anyone)
        - specialist_c (can only talk to parent, not peers)

Requirements:
    - pip install google-adk
    - Conductor server with transfer control support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=google_gemini/gemini-2.0-flash as environment variable
"""

from google.adk.agents import LlmAgent

from agentspan.agents import AgentRuntime

from settings import settings

specialist_a = LlmAgent(
    name="data_collector",
    model=settings.llm_model,
    instruction=(
        "You are a data collection specialist. Gather relevant data points "
        "about the topic and pass them to the analyst for analysis. "
        "You should NOT return to the coordinator directly."
    ),
    disallow_transfer_to_parent=True,
)

specialist_b = LlmAgent(
    name="analyst",
    model=settings.llm_model,
    instruction=(
        "You are a data analyst. Take the data collected and provide "
        "a concise analysis with insights. You can transfer to any agent."
    ),
)

specialist_c = LlmAgent(
    name="summarizer",
    model=settings.llm_model,
    instruction=(
        "You are a summarizer. Take the analysis and create a brief "
        "executive summary. Return the summary to the coordinator. "
        "Do NOT transfer to other specialists."
    ),
    disallow_transfer_to_peers=True,
)

coordinator = LlmAgent(
    name="research_coordinator",
    model=settings.llm_model,
    instruction=(
        "You are a research coordinator managing a team of specialists:\n"
        "- data_collector: gathers raw data (cannot return to you directly)\n"
        "- analyst: analyzes data (can transfer freely)\n"
        "- summarizer: creates executive summaries (cannot transfer to peers)\n\n"
        "Route the user's request through the appropriate workflow."
    ),
    sub_agents=[specialist_a, specialist_b, specialist_c],
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.adk.22_transfer_control
        runtime.deploy(coordinator)
        runtime.serve(coordinator)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(
        # coordinator,
        # "Research the current state of renewable energy adoption worldwide.",
        # )
        # result.print_result()
