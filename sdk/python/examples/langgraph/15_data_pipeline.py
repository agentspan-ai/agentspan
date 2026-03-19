# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Data Pipeline — create_agent with load, clean, analyze, and report tools.

Demonstrates:
    - An ETL-style pipeline modelled as tools called by the agent
    - Each tool represents a stage: load → clean → analyze → report
    - The LLM orchestrates the pipeline server-side via tool calls
    - LLM-based analysis and report generation run inside tool functions

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import json
from typing import List, Dict, Any

from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from agentspan.agents.langchain import create_agent
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


@tool
def load_data(dataset_name: str) -> str:
    """Load a named mock dataset and return it as JSON.

    Args:
        dataset_name: Name of the dataset to load — 'sales' or 'users'.
    """
    mock_datasets = {
        "sales": [
            {"product": "Widget A", "revenue": 15000, "units": 300, "region": "North"},
            {"product": "Widget B", "revenue": None, "units": 150, "region": "South"},
            {"product": "Widget C", "revenue": 8000, "units": -5, "region": "East"},
            {"product": "Widget D", "revenue": 22000, "units": 440, "region": "West"},
            {"product": "Widget E", "revenue": 0, "units": 0, "region": "North"},
        ],
        "users": [
            {"id": 1, "name": "Alice", "age": 28, "active": True},
            {"id": 2, "name": "", "age": -1, "active": False},
            {"id": 3, "name": "Bob", "age": 34, "active": True},
        ],
    }
    dataset = mock_datasets.get(dataset_name.lower(), mock_datasets["sales"])
    return f"Loaded {len(dataset)} records from '{dataset_name}':\n{json.dumps(dataset, indent=2)}"


@tool
def clean_data(raw_json: str) -> str:
    """Clean a JSON dataset by removing invalid rows and returning the cleaned result.

    Removes rows with None revenue, negative units, or zero-revenue/zero-unit rows.

    Args:
        raw_json: JSON string containing a list of records to clean.
    """
    try:
        records = json.loads(raw_json)
    except json.JSONDecodeError:
        # Try to extract JSON array from larger text
        import re
        match = re.search(r'\[.*\]', raw_json, re.DOTALL)
        if match:
            records = json.loads(match.group())
        else:
            return "Error: Could not parse JSON from input."

    cleaned = []
    for row in records:
        if row.get("revenue") is None or row.get("units", 0) < 0:
            continue
        if row.get("revenue", 0) == 0 and row.get("units", 0) == 0:
            continue
        if "name" in row and not row.get("name"):
            continue
        cleaned.append(row)

    return f"Cleaned data ({len(cleaned)} valid records):\n{json.dumps(cleaned, indent=2)}"


@tool
def analyze_data(dataset_name: str, clean_json: str) -> str:
    """Analyze a cleaned dataset and return key statistics and business insights.

    Args:
        dataset_name: Name of the dataset being analyzed.
        clean_json: JSON string of cleaned records to analyze.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a data analyst. Analyze the following dataset records and provide: "
            "1) Key statistics (totals, averages, ranges), "
            "2) Notable patterns or outliers, "
            "3) Business insights. Be concise."
        )),
        ("human", "Dataset: {dataset_name}\n\n{data}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"dataset_name": dataset_name, "data": clean_json})
    return response.content


@tool
def generate_report(analysis: str) -> str:
    """Generate an executive summary report from a data analysis.

    Args:
        analysis: The data analysis text to turn into an executive report.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a business report writer. "
            "Turn the following data analysis into a concise executive summary report "
            "with an introduction, key findings, and recommendations."
        )),
        ("human", "{analysis}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"analysis": analysis})
    return response.content


PIPELINE_SYSTEM = """You are a data pipeline orchestrator.

For each dataset analysis request:
1. Load the dataset using load_data
2. Clean the raw data using clean_data (pass the raw JSON from step 1)
3. Analyze the cleaned data using analyze_data
4. Generate an executive report using generate_report

Always complete all four steps and present the final report.
"""

graph = create_agent(
    llm,
    tools=[load_data, clean_data, analyze_data, generate_report],
    name="data_pipeline",
    system_prompt=PIPELINE_SYSTEM,
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(graph, "Run the full pipeline on the sales dataset.")
        print(f"Status: {result.status}")
        result.print_result()
