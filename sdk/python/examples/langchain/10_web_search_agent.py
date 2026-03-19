# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Web Search Agent — agent that simulates web search and summarization.

Demonstrates:
    - Simulated search tool returning structured mock results
    - Agent combining multiple search results into a coherent answer
    - Citation-aware summarization
    - Practical use case: research assistant with web search capability

    NOTE: This example uses mock search results. For production, integrate
    Tavily, SerpAPI, or Brave Search with their respective API keys.

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import json
from typing import List

from langchain_core.tools import tool
from agentspan.agents.langchain import create_agent
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


# Mock search index
_SEARCH_INDEX = {
    "langchain": [
        {"title": "LangChain Documentation", "url": "https://docs.langchain.com", "snippet": "LangChain is a framework for building applications with LLMs. It provides modules for chains, agents, memory, and retrieval."},
        {"title": "LangChain GitHub", "url": "https://github.com/langchain-ai/langchain", "snippet": "Open-source Python and JavaScript library with 80k+ GitHub stars."},
    ],
    "langgraph": [
        {"title": "LangGraph Docs", "url": "https://langchain-ai.github.io/langgraph/", "snippet": "LangGraph is a library for building stateful multi-actor applications with LLMs, built on top of LangChain."},
        {"title": "LangGraph Tutorial", "url": "https://blog.langchain.dev/langgraph/", "snippet": "LangGraph introduces graph-based orchestration of LLM workflows with support for cycles, branching, and persistence."},
    ],
    "python": [
        {"title": "Python.org", "url": "https://www.python.org", "snippet": "Python is a versatile, high-level programming language. The latest version is Python 3.13."},
        {"title": "Python Tutorial", "url": "https://docs.python.org/3/tutorial/", "snippet": "The official Python tutorial covering syntax, data structures, modules, and standard library."},
    ],
    "openai": [
        {"title": "OpenAI API", "url": "https://platform.openai.com/docs", "snippet": "The OpenAI API provides access to GPT-4, DALL-E, Whisper, and Embeddings models via REST API."},
        {"title": "OpenAI Models", "url": "https://platform.openai.com/docs/models", "snippet": "Available models include GPT-4o, GPT-4 Turbo, GPT-3.5 Turbo, and the o1 reasoning series."},
    ],
}


@tool
def web_search(query: str, num_results: int = 3) -> str:
    """Search the web for information about a topic.

    Returns a list of search results with titles, URLs, and snippets.
    Use this tool to find current information about any topic.

    Args:
        query: The search query string.
        num_results: Number of results to return (1-5, default 3).
    """
    # Find best matching index entries
    query_lower = query.lower()
    results = []
    for keyword, entries in _SEARCH_INDEX.items():
        if keyword in query_lower:
            results.extend(entries)

    if not results:
        # Generic fallback
        return json.dumps([{
            "title": f"Search results for '{query}'",
            "url": f"https://search.example.com/?q={query.replace(' ', '+')}",
            "snippet": f"No cached results for '{query}'. In production, this would return live search results.",
        }])

    results = results[:num_results]
    return json.dumps(results, indent=2)


@tool
def fetch_page_summary(url: str) -> str:
    """Fetch and summarize the content of a web page.

    Args:
        url: The URL to fetch.
    """
    # Mock page content based on URL patterns
    content_map = {
        "docs.langchain.com": "LangChain provides components including LLMs, PromptTemplates, Chains, Agents, and Memory. The LCEL (LangChain Expression Language) allows composing these components with the | operator.",
        "langchain-ai.github.io/langgraph": "LangGraph is built on top of LangChain and uses a graph-based approach where nodes are Python functions and edges define the flow between them.",
        "python.org": "Python 3.13 is the latest stable release. Key features include improved error messages, a free-threaded build option, and incremental GC improvements.",
        "platform.openai.com": "GPT-4o is OpenAI's most capable and efficient model. The API supports text, images, and function calling. Rate limits vary by tier.",
    }
    for key, content in content_map.items():
        if key in url:
            return f"Page content from {url}:\n{content}"
    return f"Page at {url} contains general information about the topic. (Mock result)"


graph = create_agent(
    llm,
    tools=[web_search, fetch_page_summary],
    name="web_search_agent",
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "Search for information about LangGraph and summarize what you find.",
        )
        print(f"Status: {result.status}")
        result.print_result()
