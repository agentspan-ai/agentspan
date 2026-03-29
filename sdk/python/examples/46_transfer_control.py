# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Transfer Control — restrict which agents can hand off to which.

Uses ``allowed_transitions`` to constrain handoff paths between sub-agents.
This prevents unwanted transfers (e.g., a data collector shouldn't route
directly back to the coordinator).

Requirements:
    - Conductor server
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import Agent, AgentRuntime, tool
from settings import settings


@tool
def collect_data(source: str) -> dict:
    """Collect data from a source.

    Args:
        source: The data source name.

    Returns:
        Dictionary with collected data.
    """
    return {"source": source, "records": 42, "status": "collected"}


@tool
def analyze_data(data_summary: str) -> dict:
    """Analyze collected data.

    Args:
        data_summary: Summary of data to analyze.

    Returns:
        Dictionary with analysis results.
    """
    return {"analysis": "Trend is upward", "confidence": 0.87}


@tool
def write_summary(findings: str) -> dict:
    """Write a summary report.

    Args:
        findings: The findings to summarize.

    Returns:
        Dictionary with the summary.
    """
    return {"summary": f"Report: {findings[:100]}", "word_count": 150}


data_collector = Agent(
    name="data_collector_46",
    model=settings.llm_model,
    instructions="Collect data using collect_data. Then transfer to the analyst.",
    tools=[collect_data],
)

analyst = Agent(
    name="analyst_46",
    model=settings.llm_model,
    instructions="Analyze data using analyze_data. Transfer to summarizer when done.",
    tools=[analyze_data],
)

summarizer = Agent(
    name="summarizer_46",
    model=settings.llm_model,
    instructions="Write a summary using write_summary.",
    tools=[write_summary],
)

# Coordinator with constrained transitions:
# - data_collector can only go to analyst (not back to coordinator or peers)
# - analyst can go to summarizer or coordinator
# - summarizer can only return to coordinator
coordinator = Agent(
    name="coordinator_46",
    model=settings.llm_model,
    instructions=(
        "You coordinate a data pipeline. Route to data_collector_46 first, "
        "then analyst_46, then summarizer_46."
    ),
    agents=[data_collector, analyst, summarizer],
    strategy="handoff",
    allowed_transitions={
        "data_collector_46": ["analyst_46"],
        "analyst_46": ["summarizer_46", "coordinator_46"],
        "summarizer_46": ["coordinator_46"],
    },
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.46_transfer_control
        runtime.deploy(coordinator)
        runtime.serve(coordinator)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(
        #     coordinator,
        #     "Collect data from the sales database, analyze trends, and write a summary.",
        # )
        # result.print_result()

