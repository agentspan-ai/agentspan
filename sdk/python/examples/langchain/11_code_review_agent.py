# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Code Review Agent — automated code review with categorized feedback.

Demonstrates:
    - Specialized system prompt for a code reviewer persona
    - Tools for checking different aspects of code quality
    - Aggregating findings into a structured review report
    - Practical use case: automated PR reviewer / code quality gate

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import ast

from langchain_core.tools import tool
from agentspan.agents.langchain import create_agent
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


@tool
def check_syntax(code: str) -> str:
    """Check Python code for syntax errors.

    Returns 'OK' or a description of syntax errors found.
    """
    try:
        ast.parse(code)
        return "Syntax: OK — no syntax errors."
    except SyntaxError as e:
        return f"Syntax Error at line {e.lineno}: {e.msg}"


@tool
def check_complexity(code: str) -> str:
    """Estimate the cyclomatic complexity of Python code.

    Counts branches (if, for, while, try, and, or) as a rough complexity proxy.
    """
    try:
        tree = ast.parse(code)
        complexity = 1  # base
        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.For, ast.While, ast.ExceptHandler,
                                  ast.With, ast.Assert)):
                complexity += 1
            elif isinstance(node, (ast.BoolOp,)):
                complexity += len(node.values) - 1

        if complexity <= 5:
            rating = "Low (good)"
        elif complexity <= 10:
            rating = "Medium (acceptable)"
        else:
            rating = "High (consider refactoring)"
        return f"Cyclomatic complexity: {complexity} — {rating}"
    except SyntaxError:
        return "Cannot check complexity: syntax error in code."


@tool
def check_naming_conventions(code: str) -> str:
    """Check if function and variable names follow Python PEP 8 snake_case conventions."""
    try:
        tree = ast.parse(code)
        issues = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = node.name
                if name != name.lower() and not name.startswith("_") and name not in ("setUp", "tearDown"):
                    issues.append(f"Function '{name}' should be snake_case")
            elif isinstance(node, ast.ClassDef):
                name = node.name
                if not name[0].isupper():
                    issues.append(f"Class '{name}' should be PascalCase")
        if issues:
            return "Naming issues:\n" + "\n".join(f"  • {i}" for i in issues)
        return "Naming conventions: OK — all names follow PEP 8."
    except SyntaxError:
        return "Cannot check naming: syntax error in code."


@tool
def check_docstrings(code: str) -> str:
    """Check whether functions and classes have docstrings."""
    try:
        tree = ast.parse(code)
        missing = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not (node.body and isinstance(node.body[0], ast.Expr) and
                        isinstance(node.body[0].value, ast.Constant)):
                    missing.append(f"{type(node).__name__.replace('Def', '')} '{node.name}'")
        if missing:
            return "Missing docstrings in:\n" + "\n".join(f"  • {m}" for m in missing)
        return "Docstrings: OK — all functions and classes are documented."
    except SyntaxError:
        return "Cannot check docstrings: syntax error in code."


CODE_REVIEWER_SYSTEM = """You are an expert code reviewer. When given code to review:
1. Run ALL available checks (syntax, complexity, naming, docstrings)
2. Summarize findings with severity (critical/warning/info)
3. Provide an overall score out of 10
4. List the top 3 improvements
"""

graph = create_agent(
    llm,
    tools=[check_syntax, check_complexity, check_naming_conventions, check_docstrings],
    name="code_review_agent",
    system_prompt=CODE_REVIEWER_SYSTEM,
)

SAMPLE_CODE = '''
def calculateTotal(items, TaxRate):
    total = 0
    for item in items:
        if item["price"] > 0:
            total += item["price"]
            if item.get("discount"):
                total -= item["discount"]
    return total * (1 + TaxRate)

class shoppingCart:
    def addItem(self, item):
        self.items.append(item)

    def removeItem(self, item_id):
        self.items = [i for i in self.items if i["id"] != item_id]
'''

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            f"Please review this Python code:\n\n```python\n{SAMPLE_CODE}\n```",
        )
        print(f"Status: {result.status}")
        result.print_result()
