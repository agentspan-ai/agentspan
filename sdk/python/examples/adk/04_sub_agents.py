# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Google ADK Agent with Sub-Agents — multi-agent orchestration.

Demonstrates:
    - Defining specialist sub-agents with tools
    - A coordinator agent that routes to specialists via sub_agents
    - The server normalizer maps sub_agents to agents + strategy="handoff"

Requirements:
    - pip install google-adk
    - Conductor server with Google Gemini LLM integration configured
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=google_gemini/gemini-2.0-flash in .env or environment
"""

from google.adk.agents import Agent

from agentspan.agents import AgentRuntime

from settings import settings


# ── Specialist tools ──────────────────────────────────────────────────

def search_flights(origin: str, destination: str, date: str) -> dict:
    """Search for available flights.

    Args:
        origin: Departure city.
        destination: Arrival city.
        date: Travel date (YYYY-MM-DD).

    Returns:
        Dictionary with flight options.
    """
    return {
        "flights": [
            {"airline": "SkyLine", "departure": "08:00", "arrival": "11:30", "price": "$320"},
            {"airline": "AirGlobe", "departure": "14:00", "arrival": "17:45", "price": "$285"},
        ],
        "route": f"{origin} → {destination}",
        "date": date,
    }


def search_hotels(city: str, checkin: str, checkout: str) -> dict:
    """Search for available hotels.

    Args:
        city: City to search hotels in.
        checkin: Check-in date (YYYY-MM-DD).
        checkout: Check-out date (YYYY-MM-DD).

    Returns:
        Dictionary with hotel options.
    """
    return {
        "hotels": [
            {"name": "Grand Plaza", "rating": 4.5, "price": "$180/night"},
            {"name": "City Comfort Inn", "rating": 4.0, "price": "$95/night"},
            {"name": "Boutique Lux", "rating": 4.8, "price": "$250/night"},
        ],
        "city": city,
        "dates": f"{checkin} to {checkout}",
    }


def get_travel_advisory(country: str) -> dict:
    """Get travel advisory information for a country.

    Args:
        country: Country name.

    Returns:
        Dictionary with travel advisory details.
    """
    advisories = {
        "japan": {"level": "Level 1 - Exercise Normal Precautions", "visa": "Visa-free for 90 days"},
        "france": {"level": "Level 2 - Exercise Increased Caution", "visa": "Schengen visa required"},
        "australia": {"level": "Level 1 - Exercise Normal Precautions", "visa": "eVisitor visa required"},
    }
    return advisories.get(country.lower(), {"level": "Unknown", "visa": "Check embassy website"})


# ── Specialist agents ─────────────────────────────────────────────────

flight_agent = Agent(
    name="flight_specialist",
    model=settings.llm_model,
    description="Handles flight searches and booking inquiries.",
    instruction=(
        "You are a flight specialist. Search for flights and present "
        "options clearly with prices and schedules."
    ),
    tools=[search_flights],
)

hotel_agent = Agent(
    name="hotel_specialist",
    model=settings.llm_model,
    description="Handles hotel searches and accommodation inquiries.",
    instruction=(
        "You are a hotel specialist. Search for hotels and present "
        "options with ratings and prices."
    ),
    tools=[search_hotels],
)

advisory_agent = Agent(
    name="travel_advisory_specialist",
    model=settings.llm_model,
    description="Provides travel advisories, visa requirements, and safety information.",
    instruction=(
        "You are a travel advisory specialist. Provide safety levels "
        "and visa requirements for destinations."
    ),
    tools=[get_travel_advisory],
)

# ── Coordinator agent ─────────────────────────────────────────────────

coordinator = Agent(
    name="travel_coordinator",
    model=settings.llm_model,
    instruction=(
        "You are a travel planning coordinator. When a user wants to plan a trip:\n"
        "1. Use the travel advisory specialist to check safety and visa info\n"
        "2. Use the flight specialist to find flights\n"
        "3. Use the hotel specialist to find accommodation\n"
        "Route the user's request to the appropriate specialist."
    ),
    sub_agents=[flight_agent, hotel_agent, advisory_agent],
)

with AgentRuntime() as runtime:
    result = runtime.run(
        coordinator,
        "I want to plan a trip to Japan. I need a flight from San Francisco "
        "on 2025-04-15 and a hotel for 5 nights. Also, what's the travel advisory?",
    )
    result.print_result()
