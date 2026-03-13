# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Google ADK Agent with Function Tools — tool calling via Python functions.

Demonstrates:
    - Defining tools as plain Python functions (ADK auto-converts them)
    - Multiple tools with typed parameters and docstrings
    - The Conductor runtime auto-extracts callables, registers them as
      workers, and the server normalizes them into worker tasks.

Requirements:
    - pip install google-adk
    - Conductor server with Google Gemini LLM integration configured
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=google_gemini/gemini-2.0-flash in .env or environment
"""

from google.adk.agents import Agent

from agentspan.agents import AgentRuntime

from settings import settings


def get_weather(city: str) -> dict:
    """Get the current weather for a city.

    Args:
        city: Name of the city to get weather for.

    Returns:
        Dictionary with weather information.
    """
    weather_data = {
        "tokyo": {"temp_c": 22, "condition": "Clear", "humidity": 65},
        "paris": {"temp_c": 18, "condition": "Partly Cloudy", "humidity": 72},
        "sydney": {"temp_c": 25, "condition": "Sunny", "humidity": 58},
        "mumbai": {"temp_c": 32, "condition": "Humid", "humidity": 85},
    }
    data = weather_data.get(city.lower(), {"temp_c": 20, "condition": "Unknown", "humidity": 50})
    return {"city": city, **data}


def convert_temperature(temp_celsius: float, to_unit: str = "fahrenheit") -> dict:
    """Convert temperature between Celsius and Fahrenheit.

    Args:
        temp_celsius: Temperature in Celsius.
        to_unit: Target unit — "fahrenheit" or "kelvin".

    Returns:
        Dictionary with converted temperature.
    """
    if to_unit.lower() == "fahrenheit":
        converted = temp_celsius * 9 / 5 + 32
        return {"celsius": temp_celsius, "fahrenheit": round(converted, 1)}
    elif to_unit.lower() == "kelvin":
        converted = temp_celsius + 273.15
        return {"celsius": temp_celsius, "kelvin": round(converted, 1)}
    return {"error": f"Unknown unit: {to_unit}"}


def get_time_zone(city: str) -> dict:
    """Get the timezone for a city.

    Args:
        city: Name of the city.

    Returns:
        Dictionary with timezone information.
    """
    timezones = {
        "tokyo": {"timezone": "JST", "utc_offset": "+9:00"},
        "paris": {"timezone": "CET", "utc_offset": "+1:00"},
        "sydney": {"timezone": "AEST", "utc_offset": "+10:00"},
        "mumbai": {"timezone": "IST", "utc_offset": "+5:30"},
    }
    return timezones.get(city.lower(), {"timezone": "Unknown", "utc_offset": "Unknown"})


agent = Agent(
    name="travel_assistant",
    model=settings.llm_model,
    instruction=(
        "You are a travel assistant. Help users with weather information, "
        "temperature conversions, and timezone lookups. Be concise and accurate."
    ),
    tools=[get_weather, convert_temperature, get_time_zone],
)

with AgentRuntime() as runtime:
    result = runtime.run(
        agent,
        "What's the weather in Tokyo right now? Convert the temperature to "
        "Fahrenheit and tell me what timezone they're in.",
    )
    result.print_result()
