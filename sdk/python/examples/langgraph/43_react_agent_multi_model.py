# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""ReAct Agent — create_react_agent works with any LangChain-supported model.

Demonstrates:
    - create_react_agent with ChatAnthropic (Claude) instead of OpenAI
    - Model is auto-detected from the LLM instance and forwarded to Conductor
    - Same code, different model — no Agentspan-specific changes needed

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - ANTHROPIC_API_KEY for ChatAnthropic
"""

from datetime import date

from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from agentspan.agents import AgentRuntime


@tool
def get_today() -> str:
    """Return today's date in YYYY-MM-DD format."""
    return date.today().isoformat()


@tool
def days_between(date1: str, date2: str) -> str:
    """Calculate the number of days between two dates (YYYY-MM-DD format)."""
    try:
        from datetime import datetime

        d1 = datetime.strptime(date1, "%Y-%m-%d")
        d2 = datetime.strptime(date2, "%Y-%m-%d")
        diff = abs((d2 - d1).days)
        return f"There are {diff} days between {date1} and {date2}."
    except ValueError as e:
        return f"Invalid date format: {e}"


@tool
def day_of_week(date_str: str) -> str:
    """Return the day of the week for a given date (YYYY-MM-DD format)."""
    try:
        from datetime import datetime

        d = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{date_str} falls on a {d.strftime('%A')}."
    except ValueError as e:
        return f"Invalid date format: {e}"


llm = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0)

# Agentspan auto-detects ChatAnthropic and routes LLM calls through
# the anthropic/ provider on the Conductor server.
graph = create_react_agent(llm, tools=[get_today, days_between, day_of_week], name="date_calculator_agent")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.langgraph.43_react_agent_multi_model
        runtime.deploy(graph)
        runtime.serve(graph)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(
        # graph,
        # "What day of the week is today? "
        # "How many days until New Year's Day 2026? "
        # "What day of the week will that be?",
        # )
        # print(f"Status: {result.status}")
        # result.print_result()
