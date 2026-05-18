#!/usr/bin/env python3
"""Agent with tools — define a tool function, agent calls it."""

from agentspan.agents import Agent, AgentRuntime, tool


@tool
def get_weather(city: str) -> str:
    """Get current weather for a city."""
    return f"72°F and sunny in {city}"


agent = Agent(
    name="weather_bot",
    model="openai/gpt-4o-mini",
    instructions="Use the get_weather tool to answer weather questions.",
    tools=[get_weather],
)

if __name__ == "__main__":
    with AgentRuntime() as rt:
        result = rt.run(agent, "What's the weather in Tokyo?")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # rt.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.quickstart.02_tools
        #
        # 2. In a separate long-lived worker process:
        # rt.serve(agent)
