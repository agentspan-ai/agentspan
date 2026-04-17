# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""OpenAI Agents SDK compatibility — drop-in Runner replacement.

Shows how to migrate an openai-agents script to Agentspan by changing
one import line.  Everything else stays identical.

Before (runs directly against OpenAI):
    from agents import Runner

After (runs on Agentspan — durable, observable, scalable):
    from agentspan import Runner

The rest of the code — Agent definition, @function_tool decorators,
Runner.run_sync() call, result.final_output — is unchanged.

Two usage patterns are shown:

Pattern A — keep openai-agents for Agent/function_tool, swap only Runner::

    from agentspan import Runner           # ← change this one line
    from agents import Agent, function_tool  # ← unchanged

Pattern B — use Agentspan for everything (no openai-agents dependency)::

    from agentspan import Runner, function_tool
    from agentspan.agents import Agent

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o (or anthropic/claude-opus-4-6)

Usage:
    # Pattern A (requires openai-agents installed: uv add openai-agents)
    python 92_openai_agents_compat.py --pattern a

    # Pattern B (Agentspan only, no openai-agents needed)
    python 92_openai_agents_compat.py --pattern b
    python 92_openai_agents_compat.py           # default: pattern b
"""

import argparse


# ── Pattern B — pure Agentspan, no openai-agents dependency ────────────────

def run_pattern_b() -> None:
    """Run using Agentspan's own Agent and function_tool (same result)."""
    from agentspan import Runner, function_tool
    from agentspan.agents import Agent
    from settings import settings

    @function_tool
    def get_weather(city: str) -> str:
        """Return the current weather for a city.

        Args:
            city: Name of the city.
        """
        return f"72°F and sunny in {city}"

    @function_tool
    def get_time(timezone: str) -> str:
        """Return the current time in a timezone.

        Args:
            timezone: IANA timezone name (e.g. 'America/New_York').
        """
        from datetime import datetime
        import zoneinfo

        try:
            tz = zoneinfo.ZoneInfo(timezone)
            return datetime.now(tz).strftime("%H:%M %Z")
        except Exception:
            return f"Unknown timezone: {timezone}"

    agent = Agent(
        name="weather_assistant_b",
        model=settings.llm_model,
        tools=[get_weather, get_time],
        instructions=(
            "You are a helpful assistant that answers questions about weather and time. "
            "Always use the provided tools to look up real data."
        ),
    )

    result = Runner.run_sync(agent, "What's the weather in NYC and what time is it there?")
    print(result.final_output)


# ── Pattern A — keep openai-agents Agent/function_tool, swap only Runner ───

def run_pattern_a() -> None:
    """Run with openai-agents Agent but Agentspan's Runner.

    Requires: uv add openai-agents
    """
    try:
        from agents import Agent, function_tool
    except ImportError:
        print("openai-agents not installed. Run: uv add openai-agents")
        print("Falling back to pattern B...")
        run_pattern_b()
        return

    # ── The ONE line you change ────────────────────────────────────────────
    # from agents import Runner     # ← original openai-agents import
    from agentspan import Runner    # ← drop-in Agentspan replacement

    @function_tool
    def get_weather(city: str) -> str:
        """Return the current weather for a city.

        Args:
            city: Name of the city.
        """
        return f"72°F and sunny in {city}"

    @function_tool
    def get_time(timezone: str) -> str:
        """Return the current time in a timezone.

        Args:
            timezone: IANA timezone name (e.g. 'America/New_York').
        """
        from datetime import datetime
        import zoneinfo

        try:
            tz = zoneinfo.ZoneInfo(timezone)
            return datetime.now(tz).strftime("%H:%M %Z")
        except Exception:
            return f"Unknown timezone: {timezone}"

    agent = Agent(
        name="weather_assistant_a",
        model="gpt-4o",
        tools=[get_weather, get_time],
        instructions=(
            "You are a helpful assistant that answers questions about weather and time. "
            "Always use the provided tools to look up real data."
        ),
    )

    result = Runner.run_sync(agent, "What's the weather in NYC and what time is it there?")
    print(result.final_output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OpenAI Agents SDK compatibility demo")
    parser.add_argument(
        "--pattern",
        choices=["a", "b"],
        default="b",
        help="a = openai-agents Agent + Agentspan Runner; b = pure Agentspan (default)",
    )
    args = parser.parse_args()

    if args.pattern == "a":
        run_pattern_a()
    else:
        run_pattern_b()
