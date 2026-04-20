# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""OpenAI Agents SDK migration — drop-in Runner replacement.

Shows how to migrate an openai-agents script to Agentspan by changing
one import line.  Everything else — Agent definition, @function_tool
decorators, Runner.run_sync() call, result.final_output — stays identical.

Before (runs directly against OpenAI):
    from agents import Runner

After (runs on Agentspan — durable, observable, scalable):
    from agentspan import Runner

The diff:
    -from agents import Runner
    +from agentspan import Runner

Requirements:
    - uv add openai-agents          (from sdk/python/)
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o (or any supported model)

Usage (from sdk/python/):
    uv run python examples/92_openai_agents_compat.py
"""

try:
    from agents import Agent, function_tool
except ImportError:
    raise SystemExit(
        "openai-agents not installed.\n"
        "Install it with (from sdk/python/): uv add openai-agents\n"
        "Then run: uv run python examples/92_openai_agents_compat.py"
    )

# ── Only this line changes ──────────────────────────────────────────────────
# from agents import Runner          # ← original (runs directly on OpenAI)
from agentspan import Runner         # ← agentspan (runs on Agentspan)
# ───────────────────────────────────────────────────────────────────────────


@function_tool
def get_weather(city: str) -> str:
    """Return the current weather for a city."""
    return f"72°F and sunny in {city}"


@function_tool
def get_time(timezone: str) -> str:
    """Return the current time in a timezone (e.g. 'America/New_York')."""
    import zoneinfo
    from datetime import datetime

    try:
        tz = zoneinfo.ZoneInfo(timezone)
        return datetime.now(tz).strftime("%H:%M %Z")
    except Exception:
        return f"Unknown timezone: {timezone}"


agent = Agent(
    name="weather_assistant",
    model="gpt-4o",
    tools=[get_weather, get_time],
    instructions=(
        "You are a helpful assistant that answers questions about weather and time. "
        "Always use the provided tools."
    ),
)

if __name__ == "__main__":
    result = Runner.run_sync(agent, "What's the weather in NYC and what time is it there?")
    print(result.final_output)
