# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Web Search Agent — agent that simulates web search and page retrieval.

Demonstrates:
    - Simulated search result tools
    - Multi-step research: search → select → retrieve
    - Synthesizing information from multiple sources

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime


@tool
def web_search(query: str) -> str:
    """Search the web and return top 3 result summaries.

    Args:
        query: The search query string.
    """
    results = {
        "python history": [
            "Python was created by Guido van Rossum in 1989 and first released in 1991.",
            "Python 2.0 introduced list comprehensions and garbage collection (2000).",
            "Python 3.0, a major breaking change, was released in December 2008.",
        ],
        "machine learning": [
            "Machine learning is a branch of AI that enables systems to learn from data.",
            "Supervised learning uses labeled data; unsupervised learning finds hidden patterns.",
            "Deep learning uses neural networks with many layers for complex pattern recognition.",
        ],
        "climate change": [
            "Global average temperature has risen ~1.1°C above pre-industrial levels.",
            "CO2 levels reached 421 ppm in 2023, the highest in 3.6 million years.",
            "The Paris Agreement aims to limit warming to 1.5°C by reducing emissions.",
        ],
    }
    for key, items in results.items():
        if key in query.lower():
            return "\n".join(f"{i+1}. {item}" for i, item in enumerate(items))
    return f"Search results for '{query}': No cached results. (Demo mode — add more entries to results dict.)"


@tool
def get_page_content(url: str) -> str:
    """Retrieve the main content of a web page by URL.

    Args:
        url: The page URL to retrieve content from.
    """
    pages = {
        "python.org": "Python is a versatile, high-level programming language emphasizing readability. Used in web development, data science, AI, automation, and more.",
        "wikipedia.org/ml": "Machine learning (ML) is a field of AI research dedicated to developing systems that learn from data. Key techniques include regression, classification, clustering, and neural networks.",
    }
    for key, content in pages.items():
        if key in url.lower():
            return content
    return f"Content from {url}: (Demo mode — page content not cached.)"


@tool
def summarize_results(text: str) -> str:
    """Summarize a block of text into 2-3 key bullet points.

    Args:
        text: The text to summarize.
    """
    sentences = [s.strip() for s in text.split(".") if len(s.strip()) > 20]
    bullets = sentences[:3]
    return "\n".join(f"• {b}." for b in bullets) if bullets else "No content to summarize."


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [web_search, get_page_content, summarize_results]

graph = create_agent(
    llm,
    tools=tools,
    name="web_search_agent",
    system_prompt="You are a research assistant. Use search and retrieval tools to answer questions thoroughly.",
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "Research the history of Python programming language and give me a brief summary.",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.10_web_search_agent
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
