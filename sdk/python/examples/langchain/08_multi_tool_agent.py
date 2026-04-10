# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Multi-Tool Agent — agent with tools across multiple domains.

Demonstrates:
    - Combining tools for weather, finance, and news domains
    - Agent selects the right tool based on the question type
    - Handling multi-domain queries in a single request

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime


@tool
def get_weather(city: str) -> str:
    """Get current weather conditions for a city.

    Args:
        city: The city name (e.g., 'New York', 'London').
    """
    weather_data = {
        "new york": "72°F (22°C), partly cloudy, humidity 65%, light winds from SW.",
        "london": "58°F (14°C), overcast with light rain, humidity 80%.",
        "tokyo": "68°F (20°C), sunny, humidity 55%, calm winds.",
        "sydney": "75°F (24°C), clear skies, humidity 50%, gentle sea breeze.",
        "paris": "63°F (17°C), mostly cloudy, humidity 70%.",
    }
    return weather_data.get(city.lower(), f"Weather data unavailable for '{city}'.")


@tool
def get_stock_price(ticker: str) -> str:
    """Look up the current stock price for a ticker symbol.

    Args:
        ticker: The stock ticker symbol (e.g., 'AAPL', 'GOOGL').
    """
    prices = {
        "AAPL": "$182.50 (+1.2%)",
        "GOOGL": "$141.80 (-0.4%)",
        "MSFT": "$378.20 (+0.8%)",
        "AMZN": "$184.90 (+2.1%)",
        "TSLA": "$248.30 (-1.5%)",
    }
    return prices.get(ticker.upper(), f"No price data for ticker '{ticker}'.")


@tool
def get_news_headline(topic: str) -> str:
    """Fetch the top news headline for a given topic.

    Args:
        topic: The news topic (e.g., 'technology', 'climate', 'sports').
    """
    headlines = {
        "technology": "AI model achieves human-level performance on coding benchmarks.",
        "climate": "Global temperatures hit record highs for the third consecutive year.",
        "sports": "Record-breaking athlete sets new world marathon record at 1:59:40.",
        "finance": "Central bank holds interest rates steady amid cooling inflation.",
        "science": "Researchers discover a new species of deep-sea bioluminescent fish.",
    }
    return headlines.get(topic.lower(), f"No headlines found for topic '{topic}'.")


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [get_weather, get_stock_price, get_news_headline]

graph = create_agent(
    llm,
    tools=tools,
    name="multi_tool_agent",
    system_prompt="You are a multi-domain assistant with access to weather, stock, and news information.",
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "What's the weather in Tokyo, the price of AAPL stock, and the latest technology headline?",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.08_multi_tool_agent
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
