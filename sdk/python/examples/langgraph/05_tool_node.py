# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tool Node — create_agent with geography lookup tools.

Demonstrates:
    - Defining lookup tools with @tool decorator
    - create_agent handles the ReAct loop automatically (no manual ToolNode/tools_condition needed)
    - Agent calls multiple tools to answer a multi-part question

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents.langchain import create_agent
from agentspan.agents import AgentRuntime


@tool
def lookup_capital(country: str) -> str:
    """Look up the capital city of a country."""
    capitals = {
        "france": "Paris",
        "germany": "Berlin",
        "japan": "Tokyo",
        "brazil": "Brasília",
        "australia": "Canberra",
        "india": "New Delhi",
        "usa": "Washington D.C.",
        "canada": "Ottawa",
    }
    return capitals.get(country.lower(), f"Capital of {country} is not in my database.")


@tool
def lookup_population(country: str) -> str:
    """Return the approximate population of a country (in millions)."""
    populations = {
        "france": "68 million",
        "germany": "84 million",
        "japan": "125 million",
        "brazil": "215 million",
        "australia": "26 million",
        "india": "1.4 billion",
        "usa": "335 million",
        "canada": "38 million",
    }
    return populations.get(country.lower(), f"Population data for {country} is not available.")


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

graph = create_agent(
    llm,
    tools=[lookup_capital, lookup_population],
    name="tool_node_agent",
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "What is the capital and population of Japan and Brazil?",
        )
        print(f"Status: {result.status}")
        result.print_result()
