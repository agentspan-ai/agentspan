# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Subgraph — composing graphs within graphs.

Demonstrates:
    - Building a nested subgraph for a specific subtask
    - Connecting a subgraph as a node in a parent graph
    - Passing state between parent graph and subgraph
    - Practical use case: document processing pipeline with a nested analysis subgraph

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from typing import TypedDict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


# ── Subgraph ──────────────────────────────────────────────────────────────────

class AnalysisState(TypedDict):
    text: str
    sentiment: str
    keywords: List[str]
    summary: str


def analyze_sentiment(state: AnalysisState) -> AnalysisState:
    response = llm.invoke([
        SystemMessage(content="Classify the sentiment of the text. Return ONLY: positive, negative, or neutral."),
        HumanMessage(content=state["text"]),
    ])
    return {"sentiment": response.content.strip().lower()}


def extract_keywords(state: AnalysisState) -> AnalysisState:
    response = llm.invoke([
        SystemMessage(content="Extract 3-5 keywords from the text. Return a comma-separated list only."),
        HumanMessage(content=state["text"]),
    ])
    keywords = [k.strip() for k in response.content.split(",")]
    return {"keywords": keywords}


def summarize_text(state: AnalysisState) -> AnalysisState:
    response = llm.invoke([
        SystemMessage(content="Summarize this text in one sentence."),
        HumanMessage(content=state["text"]),
    ])
    return {"summary": response.content.strip()}


analysis_builder = StateGraph(AnalysisState)
analysis_builder.add_node("sentiment", analyze_sentiment)
analysis_builder.add_node("keywords", extract_keywords)
analysis_builder.add_node("summarize", summarize_text)
analysis_builder.add_edge(START, "sentiment")
analysis_builder.add_edge("sentiment", "keywords")
analysis_builder.add_edge("keywords", "summarize")
analysis_builder.add_edge("summarize", END)
analysis_subgraph = analysis_builder.compile()


# ── Parent graph ──────────────────────────────────────────────────────────────

class DocumentState(TypedDict):
    document: str
    analysis_text: str
    sentiment: str
    keywords: List[str]
    summary: str
    report: str


def prepare(state: DocumentState) -> DocumentState:
    """Extract the main body from the document for analysis."""
    # For simplicity, use the whole document as the analysis text
    return {"analysis_text": state["document"]}


def run_analysis(state: DocumentState) -> DocumentState:
    """Run the analysis subgraph on the extracted text."""
    result = analysis_subgraph.invoke({"text": state["analysis_text"]})
    return {
        "sentiment": result.get("sentiment", ""),
        "keywords": result.get("keywords", []),
        "summary": result.get("summary", ""),
    }


def build_report(state: DocumentState) -> DocumentState:
    keywords_str = ", ".join(state.get("keywords", []))
    report = (
        f"Document Analysis Report\n"
        f"========================\n"
        f"Sentiment:  {state.get('sentiment', 'unknown')}\n"
        f"Keywords:   {keywords_str}\n"
        f"Summary:    {state.get('summary', '')}\n"
    )
    return {"report": report}


parent_builder = StateGraph(DocumentState)
parent_builder.add_node("prepare", prepare)
parent_builder.add_node("analysis", run_analysis)
parent_builder.add_node("build_report", build_report)
parent_builder.add_edge(START, "prepare")
parent_builder.add_edge("prepare", "analysis")
parent_builder.add_edge("analysis", "build_report")
parent_builder.add_edge("build_report", END)

graph = parent_builder.compile(name="document_pipeline_with_subgraph")

if __name__ == "__main__":
    sample_doc = (
        "Quantum computing uses quantum bits (qubits) that can exist in superposition, "
        "enabling parallel computation. Unlike classical bits, qubits leverage entanglement "
        "and interference to solve certain problems exponentially faster."
    )
    with AgentRuntime() as runtime:
        result = runtime.run(graph, sample_doc)
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langgraph.21_subgraph
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
