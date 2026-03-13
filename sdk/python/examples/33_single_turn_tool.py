# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Single-Turn Tool Call — LLM calls a tool and answers in one shot.

The simplest tool-calling pattern: the user asks a question, the LLM
calls a tool to get data, then responds with the answer.  No iterative
loop — the agent runs for exactly one exchange.

Compiled workflow:

    LLM(prompt, tools) → tool executes → LLM sees result → answer

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


agent = Agent(
    name="weather_agent",
    model=settings.llm_model,
    instructions="You are a weather assistant. Use the get_weather tool to answer.",
    tools=[get_weather],
    max_turns=2,  # 1 turn to call the tool, 1 turn to answer
)

with AgentRuntime() as runtime:
    result = runtime.run(agent, "What's the weather in San Francisco?")
    result.print_result()
