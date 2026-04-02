# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Research Assistant — multi-source research with citation tracking.

Demonstrates:
    - Querying multiple knowledge sources
    - Citation and source tracking
    - Synthesizing findings from different domains

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime


@tool
def search_academic(query: str) -> str:
    """Search academic papers and return relevant findings.

    Args:
        query: The research query or topic.
    """
    papers = {
        "transformer": "Vaswani et al. (2017) 'Attention Is All You Need' introduced the Transformer architecture, enabling modern LLMs. [arxiv:1706.03762]",
        "reinforcement learning": "Sutton & Barto (2018) 'Reinforcement Learning: An Introduction' is the foundational textbook. Key concept: reward maximization via trial and error.",
        "neural network": "LeCun et al. (2015) 'Deep Learning' in Nature surveys convolutional and recurrent networks. [DOI: 10.1038/nature14539]",
        "climate": "IPCC AR6 (2021) confirms 1.5°C warming is likely by 2040 without significant emissions reductions. [ipcc.ch/report/ar6]",
    }
    for key, result in papers.items():
        if key in query.lower():
            return result
    return f"No academic papers indexed for '{query}'. Recommend searching Google Scholar or arXiv."


@tool
def search_news(topic: str) -> str:
    """Search recent news articles about a topic.

    Args:
        topic: The topic to search news for.
    """
    news = {
        "ai": "Recent: GPT-5 and Claude 4 compete on reasoning benchmarks (2025). AI regulation bills passed in EU and California.",
        "climate": "Recent: Record ocean temperatures in 2024. COP30 negotiations ongoing in Brazil.",
        "quantum": "Recent: Google claims 'quantum supremacy' milestone with 1000-qubit processor (2025).",
        "space": "Recent: SpaceX Starship completes first orbital mission. NASA Artemis III moon landing planned for 2026.",
    }
    for key, result in news.items():
        if key in topic.lower():
            return result
    return f"No recent news indexed for '{topic}'."


@tool
def get_statistics(domain: str) -> str:
    """Retrieve key statistics and figures for a research domain.

    Args:
        domain: The domain to get statistics for (e.g., 'ai market', 'renewable energy').
    """
    stats = {
        "ai market": "Global AI market size: $196B (2024), projected $1.8T by 2030. CAGR: ~37%. Top players: Microsoft, Google, AWS.",
        "renewable energy": "Renewables supplied 30% of global electricity in 2023. Solar capacity grew 45% YoY. Wind energy: 2,200 GW installed.",
        "global population": "World population: 8.1B (2024). Projected 9.7B by 2050. Fastest growth: Sub-Saharan Africa.",
        "internet": "Internet users: 5.4B (67% of world). Mobile internet: 92% of usage. Data created daily: 2.5 quintillion bytes.",
    }
    for key, result in stats.items():
        if key in domain.lower():
            return result
    return f"No statistics indexed for '{domain}'."


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [search_academic, search_news, get_statistics]

graph = create_agent(
    llm,
    tools=tools,
    name="research_assistant_agent",
    system_prompt=(
        "You are a thorough research assistant. When answering questions, "
        "search academic sources, recent news, and statistics to provide well-rounded answers. "
        "Always cite your sources."
    ),
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "Research the current state of AI: what does academic literature say, what are recent news developments, and what are the market statistics?",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.14_research_assistant
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
