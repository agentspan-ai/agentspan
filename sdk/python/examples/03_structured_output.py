# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Structured Output — Pydantic output types.

Demonstrates how to get typed, validated responses from an agent
using Pydantic models.

Requirements:
    - Conductor server with LLM support
    - pydantic installed
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from pydantic import BaseModel

from agentspan.agents import Agent, AgentRuntime, tool
from settings import settings


class WeatherReport(BaseModel):
    city: str
    temperature: float
    condition: str
    recommendation: str


@tool
def get_weather(city: str) -> dict:
    """Get current weather data for a city."""
    return {"city": city, "temp_f": 72, "condition": "Sunny", "humidity": 45}


agent = Agent(
    name="weather_reporter",
    model=settings.llm_model,
    tools=[get_weather],
    output_type=WeatherReport,
    instructions="You are a weather reporter. Get the weather and provide a recommendation.",
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.03_structured_output
        runtime.deploy(agent)
        runtime.serve(agent)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(agent, "What's the weather in NYC?")
        # result.print_result()

