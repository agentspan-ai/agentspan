# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Math Agent — create_agent with comprehensive arithmetic and math tools.

Demonstrates:
    - Defining multiple related tools in a single agent
    - Using create_agent for a specialized domain (mathematics)
    - Chaining multiple tool calls to solve multi-step problems

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import math

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from agentspan.agents import AgentRuntime


@tool
def add(a: float, b: float) -> float:
    """Add two numbers together and return the sum."""
    return a + b


@tool
def subtract(a: float, b: float) -> float:
    """Subtract b from a and return the result."""
    return a - b


@tool
def multiply(a: float, b: float) -> float:
    """Multiply two numbers and return the product."""
    return a * b


@tool
def divide(a: float, b: float) -> str:
    """Divide a by b and return the quotient. Returns an error if b is zero."""
    if b == 0:
        return "Error: Division by zero is undefined."
    return str(a / b)


@tool
def power(base: float, exponent: float) -> float:
    """Raise base to the given exponent and return the result."""
    return base ** exponent


@tool
def sqrt(n: float) -> str:
    """Compute the square root of n. Returns an error for negative numbers."""
    if n < 0:
        return f"Error: Cannot compute the square root of a negative number ({n})."
    return str(math.sqrt(n))


@tool
def factorial(n: int) -> str:
    """Compute the factorial of a non-negative integer n."""
    if n < 0:
        return "Error: Factorial is not defined for negative numbers."
    if n > 20:
        return "Error: Input too large (max 20 to avoid overflow)."
    return str(math.factorial(n))


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

graph = create_agent(
    llm,
    tools=[add, subtract, multiply, divide, power, sqrt, factorial],
    name="math_agent",
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
        graph,
        "Calculate: (2^10 + sqrt(144)) / 4, then compute 5! and tell me the final answers.",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langgraph.09_math_agent
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
