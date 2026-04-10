# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""SQL Agent — natural language to SQL with schema inspection and query validation.

Demonstrates:
    - Schema introspection tools
    - SQL query generation from natural language
    - Query validation before execution
    - Simulated in-memory database execution

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import sqlite3

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

# In-memory SQLite database seeded with sample data
_DB_CONN = sqlite3.connect(":memory:", check_same_thread=False)
_DB_CONN.execute("""
    CREATE TABLE employees (
        id INTEGER PRIMARY KEY,
        name TEXT, department TEXT, salary REAL, hire_year INTEGER
    )
""")
_DB_CONN.executemany(
    "INSERT INTO employees VALUES (?,?,?,?,?)",
    [
        (1, "Alice Chen", "Engineering", 95000, 2020),
        (2, "Bob Martinez", "Marketing", 72000, 2019),
        (3, "Carol Williams", "Engineering", 105000, 2018),
        (4, "Dave Johnson", "HR", 68000, 2021),
        (5, "Eve Davis", "Engineering", 88000, 2022),
        (6, "Frank Lee", "Marketing", 79000, 2020),
        (7, "Grace Kim", "HR", 71000, 2019),
        (8, "Henry Brown", "Engineering", 112000, 2017),
    ],
)
_DB_CONN.commit()


@tool
def get_schema() -> str:
    """Return the database schema: table names and column definitions."""
    cursor = _DB_CONN.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    schema_parts = []
    for table in tables:
        cols = _DB_CONN.execute(f"PRAGMA table_info({table})").fetchall()
        col_defs = ", ".join(f"{c[1]} {c[2]}" for c in cols)
        schema_parts.append(f"Table '{table}': {col_defs}")
    return "\n".join(schema_parts)


@tool
def execute_query(sql: str) -> str:
    """Execute a SELECT SQL query and return the results as formatted text.

    Only SELECT queries are allowed for safety.

    Args:
        sql: A valid SELECT SQL statement.
    """
    sql_stripped = sql.strip().upper()
    if not sql_stripped.startswith("SELECT"):
        return "Error: Only SELECT queries are permitted."
    try:
        cursor = _DB_CONN.execute(sql)
        rows = cursor.fetchall()
        if not rows:
            return "Query returned no results."
        headers = [desc[0] for desc in cursor.description]
        lines = [" | ".join(headers)]
        lines.append("-" * len(lines[0]))
        for row in rows:
            lines.append(" | ".join(str(v) for v in row))
        return "\n".join(lines)
    except Exception as e:
        return f"SQL error: {e}"


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [get_schema, execute_query]

graph = create_agent(
    llm,
    tools=tools,
    name="sql_agent",
    system_prompt=(
        "You are a SQL assistant. Always inspect the schema first, then write and execute a SELECT query. "
        "Translate natural language questions into correct SQL."
    ),
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "Which department has the highest average salary? Show me the top 3 earners in Engineering.",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.17_sql_agent
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
