# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Math Calculator — agent with arithmetic and unit conversion tools.

Demonstrates:
    - Safe expression evaluation with ast
    - Unit conversion tools (length, weight, volume)
    - Multi-step calculation workflows

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import ast
import math
import operator as op

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

_OPS = {
    ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul,
    ast.Div: op.truediv, ast.Pow: op.pow, ast.Mod: op.mod,
    ast.FloorDiv: op.floordiv, ast.USub: op.neg,
}


def _safe_eval(expr: str) -> float:
    def _eval(node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.BinOp):
            return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp):
            return _OPS[type(node.op)](_eval(node.operand))
        raise ValueError(f"Unsupported: {ast.dump(node)}")
    return _eval(ast.parse(expr, mode="eval").body)


@tool
def evaluate(expression: str) -> str:
    """Evaluate an arithmetic expression (+, -, *, /, **, %, //).

    Args:
        expression: A math expression like '(3 + 5) * 2 ** 4'.
    """
    try:
        return str(_safe_eval(expression))
    except Exception as e:
        return f"Error: {e}"


@tool
def convert_length(value: float, from_unit: str, to_unit: str) -> str:
    """Convert between length units: meters, kilometers, miles, feet, inches, cm.

    Args:
        value: The numeric value to convert.
        from_unit: Source unit (m, km, mi, ft, in, cm).
        to_unit: Target unit (m, km, mi, ft, in, cm).
    """
    to_meters = {"m": 1, "km": 1000, "mi": 1609.344, "ft": 0.3048, "in": 0.0254, "cm": 0.01}
    fu = from_unit.lower().rstrip("s")
    tu = to_unit.lower().rstrip("s")
    if fu not in to_meters or tu not in to_meters:
        return f"Unknown unit(s): {from_unit}, {to_unit}"
    result = value * to_meters[fu] / to_meters[tu]
    return f"{value} {from_unit} = {result:.4f} {to_unit}"


@tool
def statistics(numbers: str) -> str:
    """Compute mean, median, min, max, and sum for a comma-separated list of numbers.

    Args:
        numbers: Comma-separated numbers, e.g. '3, 7, 2, 9, 4'.
    """
    try:
        nums = [float(x.strip()) for x in numbers.split(",")]
        sorted_nums = sorted(nums)
        n = len(nums)
        median = sorted_nums[n // 2] if n % 2 else (sorted_nums[n // 2 - 1] + sorted_nums[n // 2]) / 2
        return (
            f"Count: {n}, Sum: {sum(nums):.2f}, Mean: {sum(nums)/n:.2f}, "
            f"Median: {median:.2f}, Min: {min(nums):.2f}, Max: {max(nums):.2f}"
        )
    except Exception as e:
        return f"Error: {e}"


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [evaluate, convert_length, statistics]

graph = create_agent(
    llm,
    tools=tools,
    name="math_calculator_agent",
    system_prompt="You are a precise math assistant. Always use tools to compute exact answers.",
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "What is (2 ** 8) + (15 * 7)? Convert 5 miles to kilometers. "
            "What is the mean and median of 12, 7, 3, 19, 5, 8?",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.09_math_calculator
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
