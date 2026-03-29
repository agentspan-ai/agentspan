# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Structured Output — create_agent with response_format for Pydantic output.

Demonstrates:
    - Passing a Pydantic model as response_format to create_agent
    - Forcing the LLM to return structured, typed data
    - Accessing fields of the structured response

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from typing import List

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from agentspan.agents import AgentRuntime


class MovieReview(BaseModel):
    """A structured movie review with title, rating, and key points."""

    title: str = Field(description="The title of the movie being reviewed")
    rating: float = Field(description="Rating from 0.0 to 10.0", ge=0.0, le=10.0)
    pros: List[str] = Field(description="List of positive aspects of the movie")
    cons: List[str] = Field(description="List of negative aspects of the movie")
    summary: str = Field(description="One-sentence overall verdict")
    recommended: bool = Field(description="Whether the reviewer recommends watching it")


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# response_format forces the agent to emit a MovieReview JSON object
graph = create_agent(
    llm,
    tools=[],
    response_format=MovieReview,
    name="movie_review_agent",
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.langgraph.08_structured_output
        runtime.deploy(graph)
        runtime.serve(graph)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(
        # graph,
        # "Write a review for the movie Inception (2010).",
        # )
        # print(f"Status: {result.status}")
        # result.print_result()
