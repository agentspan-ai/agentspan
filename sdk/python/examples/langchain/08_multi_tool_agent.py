# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Multi-Tool Agent — agent with diverse tool categories.

Demonstrates:
    - Combining tools from different domains: time, currency, weather, distance
    - Agent correctly selects and chains tool calls
    - Tools returning realistic formatted data
    - Practical use case: travel planning assistant

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import datetime

from langchain_core.tools import tool
from agentspan.agents.langchain import create_agent
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


@tool
def get_local_time(city: str) -> str:
    """Get the current local time and timezone for a city."""
    timezones = {
        "new york": ("UTC-5 (EST)", -5),
        "london": ("UTC+0 (GMT)", 0),
        "paris": ("UTC+1 (CET)", 1),
        "tokyo": ("UTC+9 (JST)", 9),
        "sydney": ("UTC+11 (AEDT)", 11),
        "dubai": ("UTC+4 (GST)", 4),
        "los angeles": ("UTC-8 (PST)", -8),
    }
    key = city.lower().strip()
    tz_label, offset = timezones.get(key, ("UTC", 0))
    utc_now = datetime.datetime.utcnow()
    local_time = utc_now + datetime.timedelta(hours=offset)
    return f"{city.title()}: {local_time.strftime('%H:%M')} ({tz_label})"


@tool
def convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
    """Convert an amount between currencies using approximate exchange rates."""
    rates_to_usd = {
        "usd": 1.0, "eur": 1.08, "gbp": 1.26, "jpy": 0.0067,
        "aud": 0.64, "cad": 0.74, "chf": 1.11, "inr": 0.012,
    }
    from_rate = rates_to_usd.get(from_currency.lower())
    to_rate = rates_to_usd.get(to_currency.lower())
    if not from_rate or not to_rate:
        return f"Currency conversion not supported for {from_currency}/{to_currency}"
    result = amount * from_rate / to_rate
    return f"{amount} {from_currency.upper()} ≈ {result:.2f} {to_currency.upper()}"


@tool
def get_flight_duration(from_city: str, to_city: str) -> str:
    """Get the approximate flight duration between two major cities."""
    durations = {
        ("new york", "london"): "7h 30m",
        ("london", "new york"): "8h 00m",
        ("london", "tokyo"): "11h 45m",
        ("tokyo", "london"): "12h 15m",
        ("new york", "los angeles"): "5h 30m",
        ("los angeles", "tokyo"): "11h 00m",
        ("paris", "new york"): "8h 10m",
        ("dubai", "london"): "7h 10m",
    }
    key = (from_city.lower(), to_city.lower())
    rev_key = (to_city.lower(), from_city.lower())
    duration = durations.get(key) or durations.get(rev_key)
    if duration:
        return f"Flight from {from_city} to {to_city}: approximately {duration}"
    return f"No direct flight data available for {from_city} → {to_city}"


@tool
def get_visa_requirement(nationality: str, destination: str) -> str:
    """Check visa requirements for a nationality traveling to a destination."""
    # Simplified visa requirement data
    visa_free = {
        ("american", "france"): "Visa-free for up to 90 days (Schengen).",
        ("american", "uk"): "Visa-free for up to 6 months.",
        ("american", "japan"): "Visa-free for up to 90 days.",
        ("british", "usa"): "ESTA required (online, $14, valid 2 years).",
        ("european", "usa"): "ESTA required for most EU nationalities.",
    }
    key = (nationality.lower(), destination.lower())
    info = visa_free.get(key, f"Please check the official embassy website for {nationality} citizens traveling to {destination}.")
    return info


graph = create_agent(
    llm,
    tools=[get_local_time, convert_currency, get_flight_duration, get_visa_requirement],
    name="travel_assistant_agent",
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "I'm an American planning to travel from New York to Tokyo. "
            "What time is it there right now, how long is the flight, "
            "and how much is 500 USD in JPY?",
        )
        print(f"Status: {result.status}")
        result.print_result()
