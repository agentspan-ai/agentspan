# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Basic ReAct Agent — create_react_agent runs on Conductor without create_agent.

Demonstrates:
    - Using langgraph.prebuilt.create_react_agent directly with AgentRuntime
    - No Agentspan wrapper needed — pass the graph straight to runtime.run()
    - Agentspan detects the ReAct structure and runs LLM + tools on Conductor
      (AI_MODEL task for the LLM, SIMPLE tasks per tool)

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import math

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from agentspan.agents import AgentRuntime


@tool
def calculate(expression: str) -> str:
    """Evaluate a mathematical expression and return the result.

    Supports +, -, *, /, **, sqrt, and pi.
    Example: '2 ** 10', 'sqrt(144)', '(3 + 5) * 2'
    """
    try:
        result = eval(expression, {"__builtins__": {}}, {"sqrt": math.sqrt, "pi": math.pi})
        return str(result)
    except Exception as e:
        return f"Error evaluating expression: {e}"


@tool
def count_words(text: str) -> str:
    """Count the number of words in the provided text."""
    return f"The text contains {len(text.split())} word(s)."


@tool
def reverse_string(text: str) -> str:
    """Reverse a string and return it."""
    return text[::-1]


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# create_react_agent from langgraph.prebuilt — no Agentspan wrapper needed.
# AgentRuntime automatically detects the "agent" + "tools" node structure,
# extracts the LLM and tools, and runs them on Conductor as separate tasks.
graph = create_react_agent(llm, tools=[calculate, count_words, reverse_string], name="math_and_text_agent")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
        graph,
        "What is sqrt(256) + 2**10? "
        "Also count the words in 'the quick brown fox jumps over the lazy dog'. "
        "And what is 'Agentspan' reversed?",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langgraph.41_react_agent_basic
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
