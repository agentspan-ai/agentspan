# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Structured Output — agent that returns typed Pydantic data.

Demonstrates:
    - Using with_structured_output() on a ChatOpenAI model
    - Forcing the LLM to return validated, typed responses
    - Wrapping structured LLM in a create_agent via a passthrough tool

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import json
from typing import List

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from agentspan.agents import AgentRuntime


class BookRecommendation(BaseModel):
    """A structured book recommendation."""

    title: str = Field(description="The book title")
    author: str = Field(description="The book author")
    genre: str = Field(description="The primary genre")
    rating: float = Field(description="Rating from 1.0 to 5.0", ge=1.0, le=5.0)
    summary: str = Field(description="One-sentence description")
    why_recommended: str = Field(description="Why this book is recommended")


structured_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0).with_structured_output(BookRecommendation)


@tool
def recommend_book(genre: str) -> str:
    """Recommend a book for the given genre, returning structured data.

    Args:
        genre: The book genre (e.g., 'sci-fi', 'mystery', 'history').
    """
    result = structured_llm.invoke(f"Recommend one excellent {genre} book.")
    return json.dumps(result.model_dump(), indent=2)


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [recommend_book]

graph = create_agent(
    llm,
    tools=tools,
    name="structured_output_agent",
    system_prompt="You are a book recommendation assistant. Use the recommend_book tool to find books.",
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(graph, "Recommend a great science fiction book and a good mystery novel.")
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.04_structured_output
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
