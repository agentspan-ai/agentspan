# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Code Agent — create_agent with write_code, explain_code, and fix_bug tools.

Demonstrates:
    - Domain-specific tools that return realistic, formatted code strings
    - Building a coding assistant that can write, explain, and fix code
    - Multi-step tool usage: write then explain, or analyze then fix

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from agentspan.agents import AgentRuntime


@tool
def write_code(description: str, language: str = "python") -> str:
    """Generate code based on a description in the specified programming language.

    Args:
        description: What the code should do.
        language: The programming language (python, javascript, java, etc.).

    Returns a well-commented code snippet.
    """
    templates = {
        "binary search": f"""\
def binary_search(arr: list, target: int) -> int:
    \"\"\"Search for target in a sorted list. Returns index or -1.\"\"\"
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1
""",
        "fibonacci": f"""\
def fibonacci(n: int) -> list[int]:
    \"\"\"Return the first n Fibonacci numbers.\"\"\"
    if n <= 0:
        return []
    seq = [0, 1]
    while len(seq) < n:
        seq.append(seq[-1] + seq[-2])
    return seq[:n]
""",
    }
    desc_lower = description.lower()
    for key, code in templates.items():
        if key in desc_lower:
            return f"```{language}\n{code}```"
    return (
        f"```{language}\n"
        f"# TODO: Implement '{description}'\n"
        f"# This is a scaffold — fill in the logic below.\n"
        f"def solution():\n"
        f"    pass\n"
        f"```"
    )


@tool
def explain_code(code: str) -> str:
    """Explain what a piece of code does in plain English.

    Args:
        code: The source code snippet to explain.

    Returns a beginner-friendly explanation.
    """
    if "binary_search" in code or "binary search" in code.lower():
        return (
            "This code implements binary search: it repeatedly halves a sorted list "
            "to find a target value in O(log n) time, returning the index or -1 if not found."
        )
    if "fibonacci" in code:
        return (
            "This code generates Fibonacci numbers: starting with 0 and 1, "
            "each subsequent number is the sum of the two before it."
        )
    return (
        "This code defines a function or set of operations. "
        "It takes inputs, processes them according to the logic provided, "
        "and returns a result. Review the docstring and variable names for details."
    )


@tool
def fix_bug(code: str, error_message: str) -> str:
    """Analyze a buggy code snippet and the error it produces, then return the fixed version.

    Args:
        code: The buggy source code.
        error_message: The error or unexpected behavior description.

    Returns the corrected code with comments explaining the fix.
    """
    if "IndexError" in error_message or "index out of range" in error_message.lower():
        return (
            f"# BUG FIX: Added bounds checking to prevent IndexError\n"
            f"# Original code had off-by-one error in loop range.\n"
            f"{code.replace('range(len(arr))', 'range(len(arr) - 1)')}\n"
            f"# Fixed: adjusted loop range to avoid accessing out-of-bounds index."
        )
    if "ZeroDivisionError" in error_message:
        return (
            f"# BUG FIX: Added zero-division guard\n"
            f"{code}\n"
            f"# Fixed: wrap the division in an 'if denominator != 0' check."
        )
    return (
        f"# BUG FIX APPLIED\n"
        f"# Error: {error_message}\n"
        f"{code}\n"
        f"# Review the logic above and add appropriate error handling."
    )


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

graph = create_agent(
    llm,
    tools=[write_code, explain_code, fix_bug],
    system_prompt=(
        "You are an expert software engineer assistant. "
        "Use your tools to write, explain, and debug code. "
        "Always provide clear, well-commented solutions."
    ),
    name="code_agent",
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.langgraph.12_code_agent
        runtime.deploy(graph)
        runtime.serve(graph)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(
        # graph,
        # "Write a binary search function in Python and explain how it works.",
        # )
        # print(f"Status: {result.status}")
        # result.print_result()
