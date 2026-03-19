# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""SQL Agent — natural language to SQL query generation and explanation.

Demonstrates:
    - Translating natural language questions to SQL queries
    - Executing queries against an in-memory SQLite database
    - Explaining query results in plain English
    - Practical use case: business intelligence assistant for non-technical users

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import sqlite3

from langchain_core.tools import tool
from agentspan.agents.langchain import create_agent
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


# ── Set up an in-memory SQLite database ───────────────────────────────────────

def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE employees (
            id INTEGER PRIMARY KEY,
            name TEXT,
            department TEXT,
            salary REAL,
            hire_year INTEGER,
            manager_id INTEGER
        );
        INSERT INTO employees VALUES
            (1, 'Alice Chen', 'Engineering', 120000, 2019, NULL),
            (2, 'Bob Martinez', 'Engineering', 95000, 2021, 1),
            (3, 'Carol White', 'Engineering', 88000, 2022, 1),
            (4, 'David Kim', 'Marketing', 75000, 2020, NULL),
            (5, 'Emma Wilson', 'Marketing', 68000, 2022, 4),
            (6, 'Frank Brown', 'Finance', 110000, 2018, NULL),
            (7, 'Grace Lee', 'Finance', 92000, 2020, 6),
            (8, 'Henry Davis', 'HR', 72000, 2021, NULL);

        CREATE TABLE projects (
            id INTEGER PRIMARY KEY,
            name TEXT,
            department TEXT,
            budget REAL,
            status TEXT
        );
        INSERT INTO projects VALUES
            (1, 'API Redesign', 'Engineering', 150000, 'active'),
            (2, 'Brand Refresh', 'Marketing', 80000, 'active'),
            (3, 'Audit System', 'Finance', 120000, 'completed'),
            (4, 'Data Pipeline', 'Engineering', 200000, 'active'),
            (5, 'Recruitment Portal', 'HR', 45000, 'planning');
    """)
    conn.commit()
    return conn


_DB = _get_db()


@tool
def get_schema() -> str:
    """Return the database schema showing all tables and their columns."""
    cur = _DB.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cur.fetchall()]
    schema_parts = []
    for table in tables:
        cur.execute(f"PRAGMA table_info({table})")
        cols = cur.fetchall()
        col_defs = ", ".join(f"{c[1]} {c[2]}" for c in cols)
        schema_parts.append(f"{table}({col_defs})")
    return "Database Schema:\n" + "\n".join(schema_parts)


@tool
def run_sql_query(sql: str) -> str:
    """Execute a read-only SQL SELECT query and return results.

    Args:
        sql: A valid SQLite SELECT statement.
    """
    sql_stripped = sql.strip().upper()
    if not sql_stripped.startswith("SELECT"):
        return "Error: Only SELECT queries are allowed."
    try:
        cur = _DB.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        if not rows:
            return "Query returned no results."
        # Format as table
        col_names = [d[0] for d in cur.description]
        header = " | ".join(col_names)
        separator = "-" * len(header)
        data_rows = [" | ".join(str(v) for v in row) for row in rows]
        return f"Results ({len(rows)} row(s)):\n{header}\n{separator}\n" + "\n".join(data_rows)
    except sqlite3.Error as e:
        return f"SQL Error: {e}"


@tool
def generate_sql(question: str) -> str:
    """Generate a SQL query for the given natural language question.

    Uses the database schema to generate an appropriate SELECT query.

    Args:
        question: Natural language question about the database.
    """
    schema = get_schema.invoke({})
    response = llm.invoke(
        f"Given this database schema:\n{schema}\n\n"
        f"Write a SQLite SELECT query to answer: '{question}'\n"
        f"Return ONLY the SQL query, no explanation."
    )
    return response.content.strip()


SQL_SYSTEM = """You are a data analyst assistant with SQL expertise.
When answering data questions:
1. First get the schema to understand the database structure
2. Generate the appropriate SQL query
3. Execute the query to get results
4. Explain the results in plain English
Always explain what the numbers mean in business terms.
"""

graph = create_agent(
    llm,
    tools=[get_schema, generate_sql, run_sql_query],
    name="sql_agent",
    system_prompt=SQL_SYSTEM,
)

if __name__ == "__main__":
    questions = [
        "What is the average salary by department?",
        "Which employees were hired before 2020 and earn over $100k?",
        "How many active projects are there and what is their total budget?",
    ]

    with AgentRuntime() as runtime:
        for q in questions:
            print(f"\nQuestion: {q}")
            result = runtime.run(graph, q)
            result.print_result()
            print("-" * 60)
