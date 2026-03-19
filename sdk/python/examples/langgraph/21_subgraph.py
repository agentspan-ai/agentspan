# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Subgraph — composing analysis sub-tasks as tools within a parent agent.

Demonstrates:
    - Each analysis sub-task (sentiment, keywords, summary) is a tool
    - A report-building tool combines all sub-task outputs
    - The LLM orchestrates the full pipeline server-side via tool calls
    - Practical use case: document processing pipeline with nested analysis

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from agentspan.agents.langchain import create_agent
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


@tool
def analyze_sentiment(text: str) -> str:
    """Classify the sentiment of the given text.

    Returns one of: positive, negative, or neutral.

    Args:
        text: Text to classify sentiment for.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Classify the sentiment of the text. Return ONLY: positive, negative, or neutral."),
        ("human", "{text}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"text": text})
    return response.content.strip().lower()


@tool
def extract_keywords(text: str) -> str:
    """Extract 3-5 keywords from the text as a comma-separated list.

    Args:
        text: Text to extract keywords from.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Extract 3-5 keywords from the text. Return a comma-separated list only."),
        ("human", "{text}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"text": text})
    return response.content.strip()


@tool
def summarize_text(text: str) -> str:
    """Summarize the given text in one concise sentence.

    Args:
        text: Text to summarize.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Summarize this text in one sentence."),
        ("human", "{text}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"text": text})
    return response.content.strip()


@tool
def build_report(sentiment: str, keywords: str, summary: str) -> str:
    """Combine analysis results into a formatted document analysis report.

    Args:
        sentiment: The sentiment classification result.
        keywords: The extracted keywords (comma-separated).
        summary: The one-sentence summary.
    """
    return (
        f"Document Analysis Report\n"
        f"========================\n"
        f"Sentiment:  {sentiment}\n"
        f"Keywords:   {keywords}\n"
        f"Summary:    {summary}\n"
    )


PIPELINE_SYSTEM = """You are a document analysis orchestrator.

For each document:
1. Call analyze_sentiment with the document text
2. Call extract_keywords with the document text
3. Call summarize_text with the document text
4. Call build_report with the sentiment, keywords, and summary from steps 1-3
5. Return the report to the user

Always complete all four analysis steps before building the report.
"""

graph = create_agent(
    llm,
    tools=[analyze_sentiment, extract_keywords, summarize_text, build_report],
    name="document_pipeline_with_subgraph",
    system_prompt=PIPELINE_SYSTEM,
)

if __name__ == "__main__":
    sample_doc = (
        "LangGraph makes it easy to build stateful, multi-actor applications with LLMs. "
        "The framework provides first-class support for persistence, streaming, and human-in-the-loop "
        "workflows. Developers love its flexibility and the ability to compose complex pipelines "
        "using simple Python functions."
    )

    with AgentRuntime() as runtime:
        result = runtime.run(graph, sample_doc)
        print(f"Status: {result.status}")
        result.print_result()
