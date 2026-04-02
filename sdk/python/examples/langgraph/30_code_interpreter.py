# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Code Interpreter — agent that writes and (safely) evaluates Python expressions.

Demonstrates:
    - An agent that generates and explains Python code
    - Safe expression evaluation for numeric calculations
    - Code explanation and debugging assistance
    - Practical use case: interactive Python tutor / coding assistant

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import ast
import operator as op
from typing import Union

from langchain_core.tools import tool
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# Allowed operations for safe eval
_ALLOWED_OPS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.Pow: op.pow,
    ast.USub: op.neg,
    ast.Mod: op.mod,
    ast.FloorDiv: op.floordiv,
}


def _safe_eval(expr: str) -> Union[float, int]:
    """Safely evaluate a simple arithmetic expression."""
    def _eval(node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            return _ALLOWED_OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp):
            operand = _eval(node.operand)
            return _ALLOWED_OPS[type(node.op)](operand)
        raise ValueError(f"Unsupported expression: {ast.dump(node)}")
    tree = ast.parse(expr, mode="eval")
    return _eval(tree.body)


@tool
def evaluate_expression(expression: str) -> str:
    """Evaluate a safe Python arithmetic expression and return the result.

    Supports +, -, *, /, **, %, //. No function calls or variables allowed.
    Example: '(3 + 4) * 2 ** 3'
    """
    try:
        result = _safe_eval(expression)
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error evaluating '{expression}': {e}"


@tool
def explain_code(code: str) -> str:
    """Explain what a Python code snippet does in plain English.

    Returns a line-by-line explanation.
    """
    lines = code.strip().split("\n")
    explanations = []
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            explanations.append(f"Line {i}: (comment or blank)")
            continue
        if "=" in stripped and not stripped.startswith("if"):
            var = stripped.split("=")[0].strip()
            explanations.append(f"Line {i}: Assigns a value to variable '{var}'")
        elif stripped.startswith("for "):
            explanations.append(f"Line {i}: Starts a for-loop")
        elif stripped.startswith("if "):
            explanations.append(f"Line {i}: Conditional check")
        elif stripped.startswith("def "):
            fname = stripped.split("(")[0].replace("def ", "")
            explanations.append(f"Line {i}: Defines function '{fname}'")
        elif stripped.startswith("return "):
            explanations.append(f"Line {i}: Returns a value from the function")
        elif stripped.startswith("print("):
            explanations.append(f"Line {i}: Prints output to the console")
        else:
            explanations.append(f"Line {i}: Executes: {stripped[:60]}")
    return "\n".join(explanations)


@tool
def check_syntax(code: str) -> str:
    """Check if a Python code snippet has valid syntax.

    Returns 'Syntax OK' or a description of the syntax error.
    """
    try:
        ast.parse(code)
        return "Syntax OK — no syntax errors found."
    except SyntaxError as e:
        return f"Syntax error at line {e.lineno}: {e.msg}"


graph = create_agent(
    llm,
    tools=[evaluate_expression, explain_code, check_syntax],
    name="code_interpreter_agent",
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        for query in queries:
            print(f"\nQuery: {query}")
            result = runtime.run(graph, query)
            result.print_result()
            print("-" * 60)

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langgraph.30_code_interpreter
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
