# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Math Calculator — agent with comprehensive mathematical tools.

Demonstrates:
    - A suite of math tools covering arithmetic, algebra, statistics, and geometry
    - Agent selecting the right formula for each problem
    - Clear, formatted output from each tool
    - Practical use case: intelligent math tutor / calculator

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import math
import statistics
from typing import List

from langchain_core.tools import tool
from agentspan.agents.langchain import create_agent
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


@tool
def basic_arithmetic(expression: str) -> str:
    """Evaluate a basic arithmetic expression safely.
    Supports +, -, *, /, **, %, and parentheses.
    Example: '(3 + 5) * 2'
    """
    import ast, operator as op
    allowed = {
        ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul,
        ast.Div: op.truediv, ast.Pow: op.pow, ast.Mod: op.mod,
        ast.USub: op.neg, ast.FloorDiv: op.floordiv,
    }
    def _eval(node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.BinOp):
            return allowed[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp):
            return allowed[type(node.op)](_eval(node.operand))
        raise ValueError(f"Unsupported: {ast.dump(node)}")
    try:
        result = _eval(ast.parse(expression, mode="eval").body)
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error: {e}"


@tool
def statistics_summary(numbers: str) -> str:
    """Compute statistical summary (mean, median, std dev, min, max) for a comma-separated list of numbers."""
    try:
        nums = [float(x.strip()) for x in numbers.split(",")]
        if len(nums) < 2:
            return "Provide at least 2 numbers."
        return (
            f"Count:  {len(nums)}\n"
            f"Mean:   {statistics.mean(nums):.4f}\n"
            f"Median: {statistics.median(nums):.4f}\n"
            f"StdDev: {statistics.stdev(nums):.4f}\n"
            f"Min:    {min(nums)}\n"
            f"Max:    {max(nums)}"
        )
    except ValueError as e:
        return f"Error parsing numbers: {e}"


@tool
def solve_quadratic(a: float, b: float, c: float) -> str:
    """Solve ax² + bx + c = 0 using the quadratic formula."""
    discriminant = b**2 - 4*a*c
    if discriminant > 0:
        x1 = (-b + math.sqrt(discriminant)) / (2*a)
        x2 = (-b - math.sqrt(discriminant)) / (2*a)
        return f"Two real roots: x₁ = {x1:.6f}, x₂ = {x2:.6f}"
    elif discriminant == 0:
        x = -b / (2*a)
        return f"One real root: x = {x:.6f}"
    else:
        real = -b / (2*a)
        imag = math.sqrt(-discriminant) / (2*a)
        return f"Complex roots: x₁ = {real:.4f}+{imag:.4f}i, x₂ = {real:.4f}-{imag:.4f}i"


@tool
def circle_properties(radius: float) -> str:
    """Calculate area, circumference, and diameter of a circle."""
    area = math.pi * radius**2
    circumference = 2 * math.pi * radius
    diameter = 2 * radius
    return (
        f"Circle (r={radius}):\n"
        f"  Diameter:      {diameter:.4f}\n"
        f"  Circumference: {circumference:.4f}\n"
        f"  Area:          {area:.4f}"
    )


@tool
def prime_factorization(n: int) -> str:
    """Find the prime factorization of a positive integer."""
    if n < 2:
        return f"{n} has no prime factors."
    factors = []
    d = 2
    temp = n
    while d * d <= temp:
        while temp % d == 0:
            factors.append(d)
            temp //= d
        d += 1
    if temp > 1:
        factors.append(temp)
    factor_str = " × ".join(str(f) for f in factors)
    return f"{n} = {factor_str}"


graph = create_agent(
    llm,
    tools=[basic_arithmetic, statistics_summary, solve_quadratic, circle_properties, prime_factorization],
    name="math_calculator_agent",
)

if __name__ == "__main__":
    problems = [
        "What is (15 * 4 + 8) / 7?",
        "Solve 2x² - 5x + 3 = 0",
        "What are the properties of a circle with radius 7?",
        "Find the prime factorization of 360.",
        "Give me statistics for: 12, 45, 23, 67, 34, 89, 11, 55",
    ]

    with AgentRuntime() as runtime:
        for problem in problems:
            print(f"\nProblem: {problem}")
            result = runtime.run(graph, problem)
            result.print_result()
