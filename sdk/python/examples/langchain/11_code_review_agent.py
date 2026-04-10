# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Code Review Agent — agent that analyzes Python code for quality issues.

Demonstrates:
    - Static code analysis tools (syntax, style, complexity)
    - Combining multiple specialized analysis tools
    - Producing actionable code review feedback

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import ast

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime


@tool
def check_syntax(code: str) -> str:
    """Check Python code for syntax errors.

    Args:
        code: Python source code to validate.
    """
    try:
        ast.parse(code)
        return "Syntax OK — no syntax errors found."
    except SyntaxError as e:
        return f"Syntax error at line {e.lineno}: {e.msg}"


@tool
def measure_complexity(code: str) -> str:
    """Estimate cyclomatic complexity by counting branches in Python code.

    Args:
        code: Python source code to analyze.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return "Cannot measure complexity — syntax error in code."

    branches = sum(
        1 for node in ast.walk(tree)
        if isinstance(node, (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.With, ast.Assert))
    )
    score = branches + 1
    rating = "Low" if score <= 5 else "Medium" if score <= 10 else "High"
    return f"Cyclomatic complexity: {score} ({rating}). Branch count: {branches}."


@tool
def check_naming_conventions(code: str) -> str:
    """Check whether function and variable names follow PEP 8 snake_case convention.

    Args:
        code: Python source code to check.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return "Cannot check naming — syntax error in code."

    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            if node.name != node.name.lower():
                violations.append(f"Function '{node.name}' should be snake_case.")
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            if node.id != node.id.lower() and not node.id.isupper():
                violations.append(f"Variable '{node.id}' should be snake_case (or ALL_CAPS for constants).")

    if not violations:
        return "Naming conventions OK — all names follow PEP 8."
    return "Naming issues:\n" + "\n".join(f"  • {v}" for v in violations[:5])


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [check_syntax, measure_complexity, check_naming_conventions]

graph = create_agent(
    llm,
    tools=tools,
    name="code_review_agent",
    system_prompt=(
        "You are an expert code reviewer. Analyze code thoroughly using the available tools. "
        "Report findings clearly and suggest improvements."
    ),
)

SAMPLE_CODE = """
def ProcessUserData(UserName, UserAge):
    if UserAge < 0:
        return None
    if UserAge < 18:
        if UserAge < 13:
            return 'child'
        else:
            return 'teen'
    return 'adult'
"""

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            f"Review this Python code and identify all issues:\n```python{SAMPLE_CODE}```",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.11_code_review_agent
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
