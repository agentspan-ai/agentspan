# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Simple Tool Calling — two tools, the LLM picks the right one.

The agent has two tools: one for weather, one for stock prices.
Based on the user's question, the LLM decides which tool to call.

In the Conductor UI you'll see each tool call as a separate task
(DynamicTask) with its inputs and outputs clearly visible.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

from agentspan.agents import Agent, AgentRuntime, tool
from settings import settings


@tool
def get_weather(city: str) -> dict:
    """Get the current weather for a city."""
    return {"city": city, "temp_f": 72, "condition": "Sunny"}


@tool
def get_stock_price(symbol: str) -> dict:
    """Get the current stock price for a ticker symbol."""
    return {"symbol": symbol, "price": 182.50, "change": "+1.2%"}


agent = Agent(
    name="weather_stock_agent",
    model=settings.llm_model,
    tools=[get_weather, get_stock_price],
    instructions="You are a helpful assistant. Use tools to answer questions.",
)

with AgentRuntime() as runtime:
    # The LLM will call get_weather (not get_stock_price)
    result = runtime.run(agent, "What's the weather like in San Francisco?")
    result.print_result()
