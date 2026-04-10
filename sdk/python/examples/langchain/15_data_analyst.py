# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Data Analyst — agent that analyzes tabular data and computes statistics.

Demonstrates:
    - Parsing CSV data from strings
    - Computing descriptive statistics
    - Identifying trends and anomalies

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import csv
import io
import statistics as stats

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime


@tool
def analyze_column(csv_data: str, column_name: str) -> str:
    """Compute descriptive statistics for a numeric column in CSV data.

    Args:
        csv_data: CSV-formatted string with headers in the first row.
        column_name: The column header to analyze.
    """
    try:
        reader = csv.DictReader(io.StringIO(csv_data.strip()))
        values = []
        for row in reader:
            val = row.get(column_name, "").strip()
            if val:
                values.append(float(val))
        if not values:
            return f"Column '{column_name}' not found or has no numeric values."
        return (
            f"Column '{column_name}': n={len(values)}, "
            f"mean={stats.mean(values):.2f}, "
            f"median={stats.median(values):.2f}, "
            f"stdev={stats.stdev(values):.2f}, "
            f"min={min(values):.2f}, max={max(values):.2f}"
        )
    except Exception as e:
        return f"Error: {e}"


@tool
def find_top_rows(csv_data: str, column_name: str, n: int = 3) -> str:
    """Return the top N rows sorted by a numeric column (descending).

    Args:
        csv_data: CSV-formatted string with headers.
        column_name: The column to sort by.
        n: Number of top rows to return (default 3).
    """
    try:
        reader = csv.DictReader(io.StringIO(csv_data.strip()))
        rows = [row for row in reader if row.get(column_name, "").strip()]
        rows.sort(key=lambda r: float(r[column_name]), reverse=True)
        headers = rows[0].keys() if rows else []
        result = ", ".join(headers) + "\n"
        for row in rows[:n]:
            result += ", ".join(str(row[h]) for h in headers) + "\n"
        return result.strip()
    except Exception as e:
        return f"Error: {e}"


@tool
def detect_outliers(csv_data: str, column_name: str) -> str:
    """Detect outliers in a numeric column using the IQR method.

    Args:
        csv_data: CSV-formatted string with headers.
        column_name: The column to check for outliers.
    """
    try:
        reader = csv.DictReader(io.StringIO(csv_data.strip()))
        values = []
        for row in reader:
            val = row.get(column_name, "").strip()
            if val:
                values.append(float(val))
        if len(values) < 4:
            return "Not enough data points for outlier detection (need at least 4)."
        values.sort()
        n = len(values)
        q1 = values[n // 4]
        q3 = values[3 * n // 4]
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        outliers = [v for v in values if v < lower or v > upper]
        if not outliers:
            return f"No outliers detected in '{column_name}' (IQR bounds: [{lower:.2f}, {upper:.2f}])."
        return f"Outliers in '{column_name}': {outliers} (IQR bounds: [{lower:.2f}, {upper:.2f}])."
    except Exception as e:
        return f"Error: {e}"


SALES_DATA = """product,units_sold,revenue,margin
Widget A,150,4500.00,0.35
Widget B,89,2670.00,0.42
Gadget Pro,312,15600.00,0.28
Gadget Lite,201,6030.00,0.31
Premium Kit,45,9000.00,0.55
Basic Kit,520,7800.00,0.18
Super Widget,8,400.00,0.50"""

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [analyze_column, find_top_rows, detect_outliers]

graph = create_agent(
    llm,
    tools=tools,
    name="data_analyst_agent",
    system_prompt=(
        "You are a data analyst. Analyze the provided data using statistical tools "
        "and present your findings clearly with insights and recommendations."
    ),
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            f"Analyze this sales data. What are the revenue statistics, the top 3 products by revenue, and any outliers?\n\n{SALES_DATA}",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.15_data_analyst
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
