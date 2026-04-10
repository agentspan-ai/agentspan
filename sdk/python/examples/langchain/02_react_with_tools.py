# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""ReAct Agent with Tools — agent with practical utility tools.

Demonstrates:
    - Defining tools with @tool decorator
    - Passing tools to create_agent for a ReAct-style loop
    - Calculator, string, and date utilities

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import math
from datetime import date

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime


@tool
def calculate(expression: str) -> str:
    """Evaluate a safe mathematical expression and return the result.

    Supports +, -, *, /, **, sqrt, pi. Example: 'sqrt(144)', '2 ** 10'
    """
    try:
        result = eval(expression, {"__builtins__": {}}, {"sqrt": math.sqrt, "pi": math.pi})
        return str(result)
    except Exception as e:
        return f"Error: {e}"


@tool
def count_words(text: str) -> str:
    """Count the number of words in the provided text."""
    return f"{len(text.split())} words"


@tool
def get_today() -> str:
    """Return today's date in YYYY-MM-DD format."""
    return date.today().isoformat()


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

tools = [calculate, count_words, get_today]

graph = create_agent(llm, tools=tools, name="react_tools_agent")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "What is sqrt(256)? Also count words in 'the quick brown fox'. What is today's date?",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.02_react_with_tools
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
