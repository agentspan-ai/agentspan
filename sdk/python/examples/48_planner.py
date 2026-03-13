# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Planner — agent that plans before executing.

When ``planner=True``, the server enhances the system prompt with planning
instructions so the agent creates a step-by-step plan before executing
tools. This improves performance on complex, multi-step tasks.

Requirements:
    - Conductor server with planner support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

from agentspan.agents import Agent, AgentRuntime, tool
from settings import settings


@tool
def search_web(query: str) -> dict:
    """Search the web for information.

    Args:
        query: Search query string.

    Returns:
        Dictionary with search results.
    """
    results = {
        "climate change": [
            "Solar energy costs dropped 89% since 2010",
            "Wind power is cheapest in many regions",
        ],
        "renewable energy": [
            "Renewables = 30% of global electricity (2023)",
            "Solar capacity grew 50% year-over-year",
        ],
    }
    for key, vals in results.items():
        if any(word in query.lower() for word in key.split()):
            return {"query": query, "results": vals}
    return {"query": query, "results": ["No specific results."]}


@tool
def write_section(title: str, content: str) -> dict:
    """Write a section of a report.

    Args:
        title: Section title.
        content: Section body text.

    Returns:
        Dictionary with the formatted section.
    """
    return {"section": f"## {title}\n\n{content}"}


agent = Agent(
    name="research_writer_48",
    model=settings.llm_model,
    instructions=(
        "You are a research writer. Research topics thoroughly and "
        "write structured reports with multiple sections."
    ),
    tools=[search_web, write_section],
    planner=True,
)

with AgentRuntime() as runtime:
    result = runtime.run(
        agent,
        "Write a brief report on renewable energy and climate change solutions.",
    )
    result.print_result()
