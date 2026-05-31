# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""OpenAI Agent with Function Tools — tool calling via @function_tool.

Demonstrates:
    - Using OpenAI's @function_tool decorator for tool definitions
    - Multiple tools with typed parameters
    - The Conductor runtime auto-extracts callables, registers them as
      workers, and the server normalizes function tools into worker tasks.

Requirements:
    - pip install openai-agents
    - Conductor server with OpenAI LLM integration configured
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agents import Agent, function_tool

from agentspan.agents import AgentRuntime

from settings import settings


@function_tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    weather_data = {
        "new york": "72°F, Partly Cloudy",
        "san francisco": "58°F, Foggy",
        "miami": "85°F, Sunny",
        "london": "55°F, Rainy",
    }
    return weather_data.get(city.lower(), f"Weather data not available for {city}")


@function_tool
def calculate(expression: str) -> str:
    """Evaluate a mathematical expression and return the result."""
    import math
    safe_builtins = {
        "abs": abs, "round": round, "min": min, "max": max,
        "sqrt": math.sqrt, "pow": pow, "pi": math.pi, "e": math.e,
    }
    try:
        result = eval(expression, {"__builtins__": {}}, safe_builtins)
        return str(result)
    except Exception as e:
        return f"Error: {e}"


@function_tool
def lookup_population(city: str) -> str:
    """Look up the population of a city."""
    populations = {
        "new york": "8.3 million",
        "san francisco": "874,000",
        "miami": "442,000",
        "london": "8.8 million",
    }
    return populations.get(city.lower(), "Unknown")


agent = Agent(
    name="multi_tool_agent",
    instructions=(
        "You are a helpful assistant with access to weather, calculator, "
        "and population lookup tools. Use them to answer questions accurately."
    ),
    model=settings.llm_model,
    tools=[get_weather, calculate, lookup_population],
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
        agent,
        "What's the weather in San Francisco? Also, what's the population there "
        "and what's the square root of that number (just the digits)?",
        )
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.openai.02_function_tools
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)
