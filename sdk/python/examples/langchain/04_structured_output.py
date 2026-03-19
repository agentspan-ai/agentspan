# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Structured Output — extracting structured data using with_structured_output.

Demonstrates:
    - Using ChatOpenAI.with_structured_output() with a Pydantic schema
    - Embedding structured LLM calls inside @tool functions
    - The outer agent returns a natural language summary of structured results
    - Practical use case: entity extraction from unstructured text

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from typing import List, Optional

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from agentspan.agents.langchain import create_agent
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


# ── Pydantic schemas for structured output ────────────────────────────────────

class Person(BaseModel):
    name: str = Field(description="Full name of the person")
    age: Optional[int] = Field(default=None, description="Age in years if mentioned")
    occupation: Optional[str] = Field(default=None, description="Job title or occupation")
    location: Optional[str] = Field(default=None, description="City or country if mentioned")


class PersonList(BaseModel):
    people: List[Person] = Field(description="List of people mentioned in the text")
    total_count: int = Field(description="Total number of people mentioned")


class EventSummary(BaseModel):
    event_name: str = Field(description="Name or title of the event")
    date: Optional[str] = Field(default=None, description="Date or time period of the event")
    location: Optional[str] = Field(default=None, description="Where the event took place")
    key_outcomes: List[str] = Field(description="Main outcomes or results of the event")


# ── Structured LLM instances ──────────────────────────────────────────────────

people_extractor = llm.with_structured_output(PersonList)
event_extractor = llm.with_structured_output(EventSummary)


# ── Tool wrappers ─────────────────────────────────────────────────────────────

@tool
def extract_people(text: str) -> str:
    """Extract information about people mentioned in the text.

    Returns a structured summary of all people found.
    """
    result = people_extractor.invoke(
        f"Extract all people mentioned in the following text:\n\n{text}"
    )
    lines = [f"Found {result.total_count} person(s):"]
    for p in result.people:
        parts = [f"  • {p.name}"]
        if p.age:
            parts.append(f"age {p.age}")
        if p.occupation:
            parts.append(p.occupation)
        if p.location:
            parts.append(f"from {p.location}")
        lines.append(", ".join(parts))
    return "\n".join(lines)


@tool
def extract_event(text: str) -> str:
    """Extract structured information about an event described in the text.

    Returns event name, date, location, and key outcomes.
    """
    result = event_extractor.invoke(
        f"Extract event information from the following text:\n\n{text}"
    )
    outcomes = "\n".join(f"    - {o}" for o in result.key_outcomes)
    return (
        f"Event: {result.event_name}\n"
        f"Date:  {result.date or 'Not specified'}\n"
        f"Location: {result.location or 'Not specified'}\n"
        f"Outcomes:\n{outcomes}"
    )


graph = create_agent(
    llm,
    tools=[extract_people, extract_event],
    name="structured_output_agent",
)

if __name__ == "__main__":
    texts = [
        (
            "At yesterday's summit, Prime Minister Sarah Chen, 52, met with Tech CEO Marcus Rodriguez, "
            "45, from San Francisco. The two discussed AI regulation. Dr. Yuki Tanaka, a 38-year-old "
            "economist from Tokyo, moderated the panel."
        ),
        (
            "The 2024 OpenAI DevDay took place in San Francisco on November 6th. Key announcements "
            "included GPT-4 Turbo, a new Assistants API with code interpreter and file handling, "
            "and significant price reductions across the API."
        ),
    ]

    with AgentRuntime() as runtime:
        for text in texts:
            print(f"\nText: {text[:80]}...")
            result = runtime.run(graph, f"Extract all information from this text: {text}")
            result.print_result()
            print("-" * 60)
