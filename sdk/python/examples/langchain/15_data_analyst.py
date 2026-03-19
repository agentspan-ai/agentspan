# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Data Analyst Agent — analyze data and generate insights.

Demonstrates:
    - Tools for data operations (filter, sort, aggregate, describe)
    - Working with tabular data represented as JSON
    - LLM-generated natural language insights from raw numbers
    - Practical use case: automated data analysis and reporting

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import json
import statistics
from typing import List

from langchain_core.tools import tool
from agentspan.agents.langchain import create_agent
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# Sample dataset: monthly sales data
SALES_DATA = [
    {"month": "Jan", "region": "North", "product": "Widget A", "sales": 12500, "units": 250},
    {"month": "Jan", "region": "South", "product": "Widget A", "sales": 9800, "units": 196},
    {"month": "Jan", "region": "North", "product": "Widget B", "sales": 8200, "units": 164},
    {"month": "Feb", "region": "North", "product": "Widget A", "sales": 15300, "units": 306},
    {"month": "Feb", "region": "South", "product": "Widget A", "sales": 11200, "units": 224},
    {"month": "Feb", "region": "North", "product": "Widget B", "sales": 9100, "units": 182},
    {"month": "Mar", "region": "North", "product": "Widget A", "sales": 18700, "units": 374},
    {"month": "Mar", "region": "South", "product": "Widget A", "sales": 13400, "units": 268},
    {"month": "Mar", "region": "South", "product": "Widget B", "sales": 7600, "units": 152},
]


@tool
def describe_dataset() -> str:
    """Get a summary description of the sales dataset."""
    total_sales = sum(r["sales"] for r in SALES_DATA)
    total_units = sum(r["units"] for r in SALES_DATA)
    months = sorted(set(r["month"] for r in SALES_DATA))
    regions = sorted(set(r["region"] for r in SALES_DATA))
    products = sorted(set(r["product"] for r in SALES_DATA))
    return (
        f"Dataset: Monthly Sales Data\n"
        f"Records: {len(SALES_DATA)}\n"
        f"Months: {', '.join(months)}\n"
        f"Regions: {', '.join(regions)}\n"
        f"Products: {', '.join(products)}\n"
        f"Total Sales: ${total_sales:,.2f}\n"
        f"Total Units: {total_units:,}"
    )


@tool
def aggregate_by(column: str, metric: str = "sales") -> str:
    """Aggregate sales data by a column (month, region, or product).

    Args:
        column: Column to group by — 'month', 'region', or 'product'.
        metric: Metric to sum — 'sales' or 'units'.
    """
    if column not in ("month", "region", "product"):
        return f"Invalid column '{column}'. Choose from: month, region, product."
    if metric not in ("sales", "units"):
        return f"Invalid metric '{metric}'. Choose from: sales, units."

    groups: dict = {}
    for row in SALES_DATA:
        key = row[column]
        groups[key] = groups.get(key, 0) + row[metric]

    label = "$" if metric == "sales" else ""
    lines = [f"Total {metric} by {column}:"]
    for k, v in sorted(groups.items(), key=lambda x: -x[1]):
        lines.append(f"  {k}: {label}{v:,.2f}" if metric == "sales" else f"  {k}: {v:,} units")
    return "\n".join(lines)


@tool
def find_top_performers(n: int = 3, metric: str = "sales") -> str:
    """Find the top N performing records by sales or units.

    Args:
        n: Number of top records to return (1-10).
        metric: Ranking metric — 'sales' or 'units'.
    """
    sorted_data = sorted(SALES_DATA, key=lambda x: x.get(metric, 0), reverse=True)
    top = sorted_data[:min(n, 10)]
    lines = [f"Top {len(top)} by {metric}:"]
    for i, row in enumerate(top, 1):
        lines.append(
            f"  {i}. {row['month']} {row['region']} {row['product']}: "
            f"${row['sales']:,} / {row['units']} units"
        )
    return "\n".join(lines)


@tool
def calculate_growth(product: str) -> str:
    """Calculate month-over-month sales growth for a product.

    Args:
        product: Product name (e.g., 'Widget A').
    """
    monthly = {}
    for row in SALES_DATA:
        if row["product"] == product:
            monthly[row["month"]] = monthly.get(row["month"], 0) + row["sales"]

    if len(monthly) < 2:
        return f"Not enough data to calculate growth for '{product}'."

    months_order = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
    sorted_months = sorted(monthly.keys(), key=lambda m: months_order.index(m) if m in months_order else 99)

    lines = [f"Month-over-month growth for {product}:"]
    prev_val = None
    for month in sorted_months:
        val = monthly[month]
        if prev_val is not None:
            growth = ((val - prev_val) / prev_val) * 100
            lines.append(f"  {month}: ${val:,} ({'+' if growth >= 0 else ''}{growth:.1f}%)")
        else:
            lines.append(f"  {month}: ${val:,} (baseline)")
        prev_val = val
    return "\n".join(lines)


ANALYST_SYSTEM = """You are a data analyst assistant. When asked to analyze data:
1. Start by describing the dataset
2. Aggregate data by relevant dimensions
3. Identify top performers
4. Calculate trends/growth where relevant
5. Summarize insights in a clear executive narrative (3-4 sentences)
"""

graph = create_agent(
    llm,
    tools=[describe_dataset, aggregate_by, find_top_performers, calculate_growth],
    name="data_analyst_agent",
    system_prompt=ANALYST_SYSTEM,
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "Analyze the sales data and give me a full report including trends and top performers.",
        )
        print(f"Status: {result.status}")
        result.print_result()
