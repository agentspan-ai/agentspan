# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Document Analysis Agent — create_agent with document processing tools.

Demonstrates:
    - A suite of document analysis tools: read, extract entities, summarize, classify sentiment
    - Realistic mock implementations returning structured data
    - Chaining multiple tools to produce a comprehensive document report

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from typing import List

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from agentspan.agents import AgentRuntime

# Mock document store
_DOCUMENTS = {
    "quarterly_report": (
        "Q3 2024 Performance Report: Our revenue grew 23% year-over-year to $4.2 billion. "
        "CEO Jane Smith announced the acquisition of TechCorp Ltd for $800 million. "
        "Product launches in APAC markets exceeded expectations. "
        "CFO John Doe highlighted cost-cutting measures saving $120 million annually. "
        "Headcount increased by 1,200 employees across North America and Europe."
    ),
    "product_review": (
        "This smartphone is absolutely fantastic! The camera quality is stunning and the battery "
        "lasts two full days. However, the price point is too high for most consumers. "
        "Customer service was responsive when I had questions about setup. "
        "Overall, a premium device that delivers on its promises, though not for budget shoppers."
    ),
    "incident_report": (
        "On March 15, 2024, a service outage occurred affecting systems in region US-EAST-1. "
        "Root cause: database connection pool exhaustion due to an unoptimized query in v2.3.1. "
        "Engineering lead Sarah Chen resolved the issue within 90 minutes. "
        "Impact: 3,400 users affected, $45,000 estimated revenue loss. "
        "Mitigation: query optimization deployed, connection limits increased."
    ),
}


@tool
def read_document(document_id: str) -> str:
    """Load the full text of a document by its ID.

    Available IDs: 'quarterly_report', 'product_review', 'incident_report'.
    """
    content = _DOCUMENTS.get(document_id.lower().replace(" ", "_"))
    if not content:
        available = ", ".join(_DOCUMENTS.keys())
        return f"Document '{document_id}' not found. Available: {available}"
    return content


@tool
def extract_entities(text: str) -> str:
    """Extract named entities (people, organizations, monetary values, dates) from text.

    Returns a formatted list of entities found in the text.
    """
    # Mock entity extraction (in production, use spaCy or an NER model)
    entities = {
        "people": [],
        "organizations": [],
        "monetary": [],
        "dates": [],
    }
    import re

    # Simple heuristic patterns for mock extraction
    money_pattern = re.findall(r'\$[\d,.]+ (?:billion|million|thousand)?', text)
    date_pattern = re.findall(r'\b(?:Q[1-4] \d{4}|\w+ \d{1,2},? \d{4})\b', text)

    if "Jane Smith" in text:
        entities["people"].append("Jane Smith (CEO)")
    if "John Doe" in text:
        entities["people"].append("John Doe (CFO)")
    if "Sarah Chen" in text:
        entities["people"].append("Sarah Chen (Engineering Lead)")
    if "TechCorp" in text:
        entities["organizations"].append("TechCorp Ltd")

    entities["monetary"] = money_pattern[:5]
    entities["dates"] = date_pattern[:5]

    lines = []
    for category, items in entities.items():
        if items:
            lines.append(f"{category.title()}: {', '.join(items)}")
    return "\n".join(lines) if lines else "No named entities detected."


@tool
def summarize_document(text: str, max_words: int = 50) -> str:
    """Summarize the given text in approximately max_words words.

    Returns the most important points in a condensed form.
    """
    sentences = [s.strip() for s in text.split(".") if len(s.strip()) > 20]
    # Take first 2 sentences as a simple extractive summary
    selected = sentences[:2]
    summary = ". ".join(selected) + "."
    words = summary.split()
    if len(words) > max_words:
        summary = " ".join(words[:max_words]) + "..."
    return summary


@tool
def classify_sentiment(text: str) -> str:
    """Classify the overall sentiment of text as positive, negative, neutral, or mixed.

    Returns a structured sentiment report with confidence indicators.
    """
    text_lower = text.lower()
    positive_words = ["grew", "exceeded", "fantastic", "stunning", "resolved", "success"]
    negative_words = ["outage", "loss", "affected", "high price", "exhaustion"]

    pos_count = sum(1 for w in positive_words if w in text_lower)
    neg_count = sum(1 for w in negative_words if w in text_lower)

    if pos_count > neg_count * 2:
        sentiment = "POSITIVE"
        confidence = "high"
    elif neg_count > pos_count:
        sentiment = "NEGATIVE"
        confidence = "medium"
    elif pos_count > 0 and neg_count > 0:
        sentiment = "MIXED"
        confidence = "medium"
    else:
        sentiment = "NEUTRAL"
        confidence = "low"

    return (
        f"Sentiment: {sentiment}\n"
        f"Confidence: {confidence}\n"
        f"Positive signals: {pos_count}, Negative signals: {neg_count}"
    )


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

graph = create_agent(
    llm,
    tools=[read_document, extract_entities, summarize_document, classify_sentiment],
    system_prompt=(
        "You are a professional document analyst. When asked to analyze a document: "
        "1) Read it using read_document, "
        "2) Extract entities, "
        "3) Summarize the key points, "
        "4) Classify sentiment. "
        "Combine findings into a structured report."
    ),
    name="document_analysis_agent",
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
        graph,
        "Please provide a full analysis of the 'quarterly_report' document.",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langgraph.19_document_analysis
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
