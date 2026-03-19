# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""ReAct with Tools — LangChain agent using the ReAct reasoning pattern.

Demonstrates:
    - Defining custom @tool functions using langchain_core.tools
    - create_agent produces a ReAct-style graph by default
    - Agent reasons through tool calls step by step
    - Practical use case: general-purpose assistant with lookup tools

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain_core.tools import tool
from agentspan.agents.langchain import create_agent
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


@tool
def get_population(country: str) -> str:
    """Return the approximate population of a country."""
    populations = {
        "usa": "~335 million",
        "china": "~1.4 billion",
        "india": "~1.45 billion",
        "germany": "~84 million",
        "brazil": "~215 million",
        "japan": "~123 million",
    }
    return populations.get(country.lower(), f"Population data not available for '{country}'")


@tool
def get_capital(country: str) -> str:
    """Return the capital city of a country."""
    capitals = {
        "usa": "Washington D.C.",
        "china": "Beijing",
        "india": "New Delhi",
        "germany": "Berlin",
        "brazil": "Brasília",
        "japan": "Tokyo",
        "france": "Paris",
        "uk": "London",
    }
    return capitals.get(country.lower(), f"Capital not found for '{country}'")


@tool
def get_currency(country: str) -> str:
    """Return the currency used in a country."""
    currencies = {
        "usa": "US Dollar (USD)",
        "germany": "Euro (EUR)",
        "japan": "Japanese Yen (JPY)",
        "uk": "British Pound (GBP)",
        "india": "Indian Rupee (INR)",
        "china": "Chinese Yuan (CNY)",
        "brazil": "Brazilian Real (BRL)",
    }
    return currencies.get(country.lower(), f"Currency not found for '{country}'")


graph = create_agent(
    llm,
    tools=[get_population, get_capital, get_currency],
    name="country_info_agent",
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "What is the capital and currency of Japan, and what is its population?",
        )
        print(f"Status: {result.status}")
        result.print_result()
