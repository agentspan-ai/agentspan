# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Data Pipeline — StateGraph with load → clean → analyze → report nodes.

Demonstrates:
    - A multi-step ETL-style pipeline modelled as a StateGraph
    - Each node transforms the state as data flows through
    - Using an LLM at the analysis and reporting stages

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from typing import TypedDict, List, Dict, Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


class State(TypedDict):
    dataset_name: str
    raw_data: List[Dict[str, Any]]
    clean_data: List[Dict[str, Any]]
    analysis: str
    report: str


def load_data(state: State) -> State:
    """Load mock data for the requested dataset."""
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
    dataset = mock_datasets.get(state["dataset_name"].lower(), mock_datasets["sales"])
    return {"raw_data": dataset}


def clean_data(state: State) -> State:
    """Remove invalid rows and fill missing values."""
    cleaned = []
    for row in state["raw_data"]:
        # Skip rows with None revenue or negative units
        if row.get("revenue") is None or row.get("units", 0) < 0:
            continue
        # Replace zero-revenue rows with a sentinel
        if row.get("revenue", 0) == 0 and row.get("units", 0) == 0:
            continue
        cleaned.append(row)
    return {"clean_data": cleaned}


def analyze_data(state: State) -> State:
    """Run statistical analysis on the clean data using the LLM."""
    data_str = "\n".join(str(row) for row in state["clean_data"])
    response = llm.invoke([
        SystemMessage(
            content=(
                "You are a data analyst. Analyze the following dataset records and provide: "
                "1) Key statistics (totals, averages, ranges), "
                "2) Notable patterns or outliers, "
                "3) Business insights. Be concise."
            )
        ),
        HumanMessage(content=f"Dataset: {state['dataset_name']}\n\n{data_str}"),
    ])
    return {"analysis": response.content}


def generate_report(state: State) -> State:
    """Generate an executive summary report from the analysis."""
    response = llm.invoke([
        SystemMessage(
            content=(
                "You are a business report writer. "
                "Turn the following data analysis into a concise executive summary report "
                "with an introduction, key findings, and recommendations."
            )
        ),
        HumanMessage(content=state["analysis"]),
    ])
    return {"report": response.content}


builder = StateGraph(State)
builder.add_node("load", load_data)
builder.add_node("clean", clean_data)
builder.add_node("analyze", analyze_data)
builder.add_node("report", generate_report)

builder.add_edge(START, "load")
builder.add_edge("load", "clean")
builder.add_edge("clean", "analyze")
builder.add_edge("analyze", "report")
builder.add_edge("report", END)

graph = builder.compile(name="data_pipeline")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.langgraph.15_data_pipeline
        runtime.deploy(graph)
        runtime.serve(graph)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(graph, "sales")
        # print(f"Status: {result.status}")
        # result.print_result()
