# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""ReAct Agent with Tools — AgentExecutor with practical utility tools.

Demonstrates:
    - Defining tools with @tool decorator
    - Passing tools to AgentExecutor for a ReAct-style loop
    - Calculator, string, and date utilities

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import math
from datetime import date

from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate
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

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant with access to calculation and utility tools."),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

agent = create_tool_calling_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools, name="react_tools_agent")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            executor,
            "What is sqrt(256)? Also count words in 'the quick brown fox'. What is today's date?",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(executor)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.02_react_with_tools
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(executor)
