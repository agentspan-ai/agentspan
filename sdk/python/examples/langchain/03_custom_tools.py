# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Custom Tools — advanced tool definitions with typed schemas.

Demonstrates:
    - Tools with Pydantic input schemas via args_schema
    - Tools that return structured data
    - Multiple tool types: lookup, compute, format
    - How LangChain validates tool inputs before calling the function

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from typing import Optional
from pydantic import BaseModel, Field

from langchain_core.tools import tool, StructuredTool
from agentspan.agents.langchain import create_agent
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


# ── Tool with Pydantic schema ─────────────────────────────────────────────────

class UnitConversionInput(BaseModel):
    value: float = Field(description="The numeric value to convert")
    from_unit: str = Field(description="Source unit (e.g. km, miles, kg, lbs, celsius, fahrenheit)")
    to_unit: str = Field(description="Target unit (e.g. km, miles, kg, lbs, celsius, fahrenheit)")


def _convert_units(value: float, from_unit: str, to_unit: str) -> str:
    """Convert between common units."""
    from_unit = from_unit.lower().strip()
    to_unit = to_unit.lower().strip()
    conversions = {
        ("km", "miles"): lambda v: v * 0.621371,
        ("miles", "km"): lambda v: v * 1.60934,
        ("kg", "lbs"): lambda v: v * 2.20462,
        ("lbs", "kg"): lambda v: v * 0.453592,
        ("celsius", "fahrenheit"): lambda v: v * 9/5 + 32,
        ("fahrenheit", "celsius"): lambda v: (v - 32) * 5/9,
        ("meters", "feet"): lambda v: v * 3.28084,
        ("feet", "meters"): lambda v: v * 0.3048,
    }
    key = (from_unit, to_unit)
    if key in conversions:
        result = conversions[key](value)
        return f"{value} {from_unit} = {result:.4f} {to_unit}"
    return f"Conversion from {from_unit} to {to_unit} is not supported."


convert_units = StructuredTool.from_function(
    func=_convert_units,
    name="convert_units",
    description="Convert a value from one unit to another (length, weight, temperature).",
    args_schema=UnitConversionInput,
)


# ── Simple @tool with optional parameters ─────────────────────────────────────

@tool
def format_number(number: float, decimal_places: Optional[int] = 2, use_comma: bool = True) -> str:
    """Format a number with optional decimal places and thousands separator.

    Args:
        number: The number to format.
        decimal_places: Number of decimal places (default 2).
        use_comma: Whether to use comma as thousands separator (default True).
    """
    fmt = f",.{decimal_places}f" if use_comma else f".{decimal_places}f"
    return f"Formatted: {number:{fmt}}"


@tool
def percentage(part: float, whole: float) -> str:
    """Calculate what percentage 'part' is of 'whole'."""
    if whole == 0:
        return "Error: 'whole' cannot be zero."
    pct = (part / whole) * 100
    return f"{part} is {pct:.2f}% of {whole}"


graph = create_agent(
    llm,
    tools=[convert_units, format_number, percentage],
    name="custom_tools_agent",
)

if __name__ == "__main__":
    queries = [
        "Convert 100 km to miles.",
        "Format the number 1234567.891 with 3 decimal places.",
        "What percentage is 37 of 185?",
    ]

    with AgentRuntime() as runtime:
        for query in queries:
            print(f"\nQ: {query}")
            result = runtime.run(graph, query)
            result.print_result()
