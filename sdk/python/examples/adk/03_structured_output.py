# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Google ADK Agent with Structured Output — enforced JSON schema response.

Demonstrates:
    - Using output_schema for structured, validated responses
    - The server normalizer maps ADK's output_schema to AgentConfig.outputType
    - Generation config for controlling model behavior

Requirements:
    - pip install google-adk pydantic
    - Conductor server with Google Gemini LLM integration configured
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=google_gemini/gemini-2.0-flash as environment variable
"""

from typing import List

from google.adk.agents import Agent
from pydantic import BaseModel

from agentspan.agents import AgentRuntime

from settings import settings


class Ingredient(BaseModel):
    name: str
    quantity: str
    unit: str


class RecipeStep(BaseModel):
    step_number: int
    instruction: str
    duration_minutes: int


class Recipe(BaseModel):
    name: str
    servings: int
    prep_time_minutes: int
    cook_time_minutes: int
    ingredients: List[Ingredient]
    steps: List[RecipeStep]
    difficulty: str


agent = Agent(
    name="recipe_generator",
    model=settings.llm_model,
    instruction=(
        "You are a professional chef assistant. When asked for a recipe, "
        "provide a complete, well-structured recipe with precise measurements, "
        "clear step-by-step instructions, and accurate timing."
    ),
    output_schema=Recipe,
    generate_content_config={
        "temperature": 0.3,
    },
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
        agent,
        "Give me a recipe for classic Italian carbonara pasta.",
        )
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.adk.03_structured_output
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)
