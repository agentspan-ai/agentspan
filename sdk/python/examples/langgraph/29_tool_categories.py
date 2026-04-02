# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tool Categories — organizing tools into categories with metadata.

Demonstrates:
    - Defining tools with rich metadata (description, args_schema)
    - Grouping tools by category (math, string, date)
    - Passing all categorized tools to create_agent
    - The LLM correctly selects the right tool for each query

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import math
import datetime
from typing import Optional

from langchain_core.tools import tool
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


# ── Math tools ────────────────────────────────────────────────────────────────

@tool
def square_root(number: float) -> str:
    """Calculate the square root of a non-negative number."""
    if number < 0:
        return "Error: Cannot compute square root of a negative number."
    return f"√{number} = {math.sqrt(number):.6f}"


@tool
def power(base: float, exponent: float) -> str:
    """Raise a base number to an exponent (base ** exponent)."""
    result = base ** exponent
    return f"{base}^{exponent} = {result}"


@tool
def factorial(n: int) -> str:
    """Compute the factorial of a non-negative integer."""
    if n < 0 or n > 20:
        return "Error: n must be between 0 and 20."
    return f"{n}! = {math.factorial(n)}"


# ── String tools ──────────────────────────────────────────────────────────────

@tool
def count_words(text: str) -> str:
    """Count the number of words in the given text."""
    words = text.split()
    return f"Word count: {len(words)}"


@tool
def reverse_string(text: str) -> str:
    """Reverse the characters in a string."""
    return f"Reversed: {text[::-1]}"


@tool
def title_case(text: str) -> str:
    """Convert the text to title case."""
    return f"Title case: {text.title()}"


# ── Date tools ────────────────────────────────────────────────────────────────

@tool
def current_date() -> str:
    """Return today's date in YYYY-MM-DD format."""
    return f"Today's date: {datetime.date.today().isoformat()}"


@tool
def days_until(target_date: str) -> str:
    """Calculate how many days until a target date (YYYY-MM-DD)."""
    try:
        target = datetime.date.fromisoformat(target_date)
        delta = (target - datetime.date.today()).days
        if delta > 0:
            return f"{delta} days until {target_date}"
        elif delta == 0:
            return f"{target_date} is today!"
        else:
            return f"{target_date} was {abs(delta)} days ago"
    except ValueError:
        return f"Invalid date format. Use YYYY-MM-DD."


@tool
def day_of_week(date_str: str) -> str:
    """Return the day of the week for a given date (YYYY-MM-DD)."""
    try:
        d = datetime.date.fromisoformat(date_str)
        return f"{date_str} is a {d.strftime('%A')}"
    except ValueError:
        return "Invalid date format. Use YYYY-MM-DD."


# ── Agent ─────────────────────────────────────────────────────────────────────

all_tools = [
    # Math
    square_root, power, factorial,
    # String
    count_words, reverse_string, title_case,
    # Date
    current_date, days_until, day_of_week,
]

graph = create_agent(llm, tools=all_tools, name="tool_categories_agent")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        for query in queries:
            print(f"\nQuery: {query}")
            result = runtime.run(graph, query)
            result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langgraph.29_tool_categories
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
