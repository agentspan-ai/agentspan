# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""tools_condition — StateGraph using prebuilt tools_condition for ReAct routing.

Demonstrates:
    - Building a ReAct loop using tools_condition from langgraph.prebuilt
    - tools_condition returns "tools" if the last message has tool_calls, else END
    - Practical use: a weather and timezone information agent

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import operator
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
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


tools = [get_weather, get_timezone]
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
llm_with_tools = llm.bind_tools(tools)


class State(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]


def agent(state: State) -> State:
    """Invoke the LLM; it decides whether to call tools or finalize."""
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}


# tools_condition: if the last message has tool_calls → "tools", else → END
builder = StateGraph(State)
builder.add_node("agent", agent)
builder.add_node("tools", ToolNode(tools))

builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", tools_condition)
builder.add_edge("tools", "agent")

graph = builder.compile(name="weather_timezone_agent")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.langgraph.18_tools_condition
        runtime.deploy(graph)
        runtime.serve(graph)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(
        # graph,
        # "What's the weather like in Tokyo and London? Also what timezone are they in?",
        # )
        # print(f"Status: {result.status}")
        # result.print_result()
