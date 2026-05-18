# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""ReAct Agent with System Prompt — create_react_agent with prompt parameter.

Demonstrates:
    - Passing a system prompt via the prompt parameter (LangGraph 1.x API)
    - Agentspan extracts the system prompt and forwards it to the server
      as the agent's instructions — no information is lost
    - Custom persona carried through the full Conductor execution

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from agentspan.agents import AgentRuntime


@tool
def get_exchange_rate(from_currency: str, to_currency: str) -> str:
    """Get the exchange rate between two currencies (demo rates)."""
    rates = {
        ("USD", "EUR"): 0.92,
        ("USD", "GBP"): 0.79,
        ("USD", "JPY"): 149.5,
        ("EUR", "USD"): 1.09,
        ("GBP", "USD"): 1.27,
        ("JPY", "USD"): 0.0067,
    }
    key = (from_currency.upper(), to_currency.upper())
    rate = rates.get(key)
    if rate:
        return f"1 {from_currency.upper()} = {rate} {to_currency.upper()}"
    return f"Exchange rate for {from_currency}/{to_currency} not available."


@tool
def convert_units(value: float, from_unit: str, to_unit: str) -> str:
    """Convert between common units (length, weight, temperature)."""
    conversions = {
        ("km", "miles"): lambda x: x * 0.621371,
        ("miles", "km"): lambda x: x * 1.60934,
        ("kg", "lbs"): lambda x: x * 2.20462,
        ("lbs", "kg"): lambda x: x * 0.453592,
        ("celsius", "fahrenheit"): lambda x: x * 9 / 5 + 32,
        ("fahrenheit", "celsius"): lambda x: (x - 32) * 5 / 9,
    }
    key = (from_unit.lower(), to_unit.lower())
    fn = conversions.get(key)
    if fn:
        return f"{value} {from_unit} = {fn(value):.2f} {to_unit}"
    return f"Conversion from {from_unit} to {to_unit} not supported."


SYSTEM_PROMPT = (
    "You are a friendly travel assistant specializing in currency exchange "
    "and unit conversions. Always show the exact numbers and be concise."
)

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# prompt sets the system prompt (LangGraph 1.x API, replaces state_modifier).
# Agentspan extracts the prompt from the graph's closure and forwards it
# to the server as the agent's instructions.
graph = create_react_agent(
    llm,
    tools=[get_exchange_rate, convert_units],
    prompt=SYSTEM_PROMPT,
    name="travel_assistant_agent",
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
        graph,
        "I'm flying from the US to Japan with $800. "
        "How many yen will I get? The flight is 9,540 km — how far is that in miles?",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langgraph.42_react_agent_system_prompt
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
