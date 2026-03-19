# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tools Condition — create_agent with weather and timezone tools.

Demonstrates:
    - Using create_agent with multiple lookup tools
    - create_agent handles the ReAct loop automatically (no manual tools_condition needed)
    - Practical use case: a weather and timezone information agent

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents.langchain import create_agent
from agentspan.agents import AgentRuntime


@tool
def get_weather(city: str) -> str:
    """Return current weather conditions for a city (mock data).

    Args:
        city: The name of the city to get weather for.
    """
    weather_db = {
        "london": "Cloudy, 12°C, 80% humidity, light drizzle",
        "new york": "Sunny, 22°C, 55% humidity, clear skies",
        "tokyo": "Partly cloudy, 18°C, 65% humidity, mild breeze",
        "sydney": "Warm and sunny, 28°C, 45% humidity",
        "paris": "Overcast, 9°C, 85% humidity, foggy morning",
    }
    return weather_db.get(city.lower(), f"Weather data unavailable for {city}.")


@tool
def get_timezone(city: str) -> str:
    """Return the current timezone and UTC offset for a city.

    Args:
        city: The name of the city to look up.
    """
    timezone_db = {
        "london": "GMT+0 (BST+1 in summer) — Europe/London",
        "new york": "UTC-5 (EDT-4 in summer) — America/New_York",
        "tokyo": "UTC+9 — Asia/Tokyo",
        "sydney": "UTC+10 (AEDT+11 in summer) — Australia/Sydney",
        "paris": "UTC+1 (CEST+2 in summer) — Europe/Paris",
    }
    return timezone_db.get(city.lower(), f"Timezone data unavailable for {city}.")


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

graph = create_agent(
    llm,
    tools=[get_weather, get_timezone],
    name="weather_timezone_agent",
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "What's the weather like in Tokyo and London? Also what timezone are they in?",
        )
        print(f"Status: {result.status}")
        result.print_result()
