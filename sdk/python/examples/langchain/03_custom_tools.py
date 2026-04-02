# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Custom Tools — defining tools with StructuredTool and typed inputs.

Demonstrates:
    - Creating tools with StructuredTool.from_function
    - Multi-argument tools with typed parameters
    - Unit conversion and formatting utilities

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain.agents import create_agent
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime


def convert_temperature(value: float, from_unit: str, to_unit: str) -> str:
    """Convert temperature between Celsius, Fahrenheit, and Kelvin."""
    from_unit = from_unit.upper()
    to_unit = to_unit.upper()
    if from_unit == to_unit:
        return f"{value} {to_unit}"
    if from_unit == "C":
        celsius = value
    elif from_unit == "F":
        celsius = (value - 32) * 5 / 9
    elif from_unit == "K":
        celsius = value - 273.15
    else:
        return f"Unknown unit: {from_unit}"
    if to_unit == "C":
        result = celsius
    elif to_unit == "F":
        result = celsius * 9 / 5 + 32
    elif to_unit == "K":
        result = celsius + 273.15
    else:
        return f"Unknown unit: {to_unit}"
    return f"{value}°{from_unit} = {result:.2f}°{to_unit}"


def format_number(value: float, decimals: int = 2, use_commas: bool = True) -> str:
    """Format a number with specified decimal places and optional comma separators."""
    if use_commas:
        return f"{value:,.{decimals}f}"
    return f"{value:.{decimals}f}"


temperature_tool = StructuredTool.from_function(
    func=convert_temperature,
    name="convert_temperature",
    description="Convert temperature between Celsius (C), Fahrenheit (F), and Kelvin (K).",
)

number_tool = StructuredTool.from_function(
    func=format_number,
    name="format_number",
    description="Format a number with decimal places and optional comma separators.",
)

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [temperature_tool, number_tool]

graph = create_agent(llm, tools=tools, name="custom_tools_agent")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "Convert 100°C to Fahrenheit and Kelvin. Also format 1234567.891 with 2 decimal places.",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.03_custom_tools
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
