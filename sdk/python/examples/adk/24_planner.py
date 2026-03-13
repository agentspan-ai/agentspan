# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Google ADK BuiltInPlanner — agent with planning step.

Demonstrates:
    - Using BuiltInPlanner to add a planning phase before execution
    - The agent creates a step-by-step plan, then follows it
    - Mapped to system prompt enhancement on the server side

Requirements:
    - pip install google-adk
    - Conductor server
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=google_gemini/gemini-2.0-flash in .env or environment
"""

from google.adk.agents import LlmAgent
from google.adk.planners import BuiltInPlanner
from google.genai import types

from agentspan.agents import AgentRuntime

from settings import settings


def search_web(query: str) -> dict:
    """Search the web for information.

    Args:
        query: Search query string.

    Returns:
        Dictionary with search results.
    """
    results = {
        "climate change solutions": {
            "results": [
                "Solar energy costs dropped 89% since 2010",
                "Wind power is now cheapest energy source in many regions",
                "Carbon capture technology advancing rapidly",
            ]
        },
        "renewable energy statistics": {
            "results": [
                "Renewables account for 30% of global electricity (2023)",
                "Solar capacity grew 50% year-over-year",
                "China leads in renewable energy investment",
            ]
        },
    }
    for key, val in results.items():
        if any(word in query.lower() for word in key.split()):
            return {"query": query, **val}
    return {"query": query, "results": ["No specific results found."]}


def write_section(title: str, content: str) -> dict:
    """Write a section of a report.

    Args:
        title: Section title.
        content: Section body text.

    Returns:
        Dictionary with the formatted section.
    """
    return {"section": f"## {title}\n\n{content}"}


# Agent with planner — the server enhances the system prompt
# with planning instructions when it detects the planner field
agent = LlmAgent(
    name="research_writer",
    model=settings.llm_model,
    instruction=(
        "You are a research writer. When given a topic, research it "
        "thoroughly and write a structured report with multiple sections."
    ),
    tools=[search_web, write_section],
    planner=BuiltInPlanner(
        thinking_config=types.ThinkingConfig(thinking_budget=1024)
    ),
)

with AgentRuntime() as runtime:
    result = runtime.run(
        agent,
        "Write a brief report on the current state of renewable energy "
        "and climate change solutions.",
    )
    result.print_result()
