# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Research Assistant — structured research agent with citations.

Demonstrates:
    - Multi-step research: search → extract → synthesize → cite
    - Tools that simulate a knowledge retrieval pipeline
    - Generating a well-structured research report with citations
    - Practical use case: automated literature review / research briefing

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


# ── Mock knowledge base ───────────────────────────────────────────────────────

_PAPERS = {
    "transformer": [
        {"id": "paper_001", "title": "Attention Is All You Need", "authors": "Vaswani et al.", "year": 2017, "abstract": "Proposes the Transformer architecture based solely on attention mechanisms, eliminating recurrence and convolutions. Achieves state-of-the-art results on machine translation tasks."},
        {"id": "paper_002", "title": "BERT: Pre-training of Deep Bidirectional Transformers", "authors": "Devlin et al.", "year": 2018, "abstract": "Introduces bidirectional pre-training for language models. BERT achieves new state-of-the-art on 11 NLP tasks."},
    ],
    "reinforcement learning": [
        {"id": "paper_003", "title": "Playing Atari with Deep Reinforcement Learning", "authors": "Mnih et al.", "year": 2013, "abstract": "Demonstrates learning control policies directly from raw pixels using deep Q-networks (DQN). Achieves human-level performance on several Atari games."},
        {"id": "paper_004", "title": "Proximal Policy Optimization Algorithms", "authors": "Schulman et al.", "year": 2017, "abstract": "Proposes PPO, a practical on-policy reinforcement learning algorithm that is stable and computationally efficient."},
    ],
    "diffusion model": [
        {"id": "paper_005", "title": "Denoising Diffusion Probabilistic Models", "authors": "Ho et al.", "year": 2020, "abstract": "Presents a class of latent variable models for image synthesis using a diffusion process. Achieves high quality image generation."},
    ],
}

_STATS = {
    "transformer": {"adoption_rate": "95% of modern NLP models", "papers_per_year": "12,000+", "top_frameworks": "PyTorch, TensorFlow, JAX"},
    "reinforcement learning": {"adoption_rate": "Growing in robotics and games", "papers_per_year": "5,000+", "top_frameworks": "Stable Baselines, RLlib, OpenAI Gym"},
    "diffusion model": {"adoption_rate": "Dominant for image generation", "papers_per_year": "3,000+", "top_frameworks": "Diffusers (HuggingFace), DALL-E, Stable Diffusion"},
}


@tool
def search_papers(topic: str, max_results: int = 3) -> str:
    """Search for academic papers on a research topic.

    Args:
        topic: Research topic or keyword.
        max_results: Maximum number of papers to return (1-5).
    """
    topic_lower = topic.lower()
    results = []
    for key, papers in _PAPERS.items():
        if key in topic_lower or any(w in key for w in topic_lower.split()):
            results.extend(papers)

    if not results:
        return f"No papers found for '{topic}'. Try a more specific term."

    papers_json = json.dumps(results[:max_results], indent=2)
    return f"Found {min(len(results), max_results)} paper(s):\n{papers_json}"


@tool
def get_field_statistics(field: str) -> str:
    """Get statistics and trends for a research field.

    Args:
        field: Research field name (e.g., 'transformer', 'reinforcement learning').
    """
    field_lower = field.lower()
    for key, stats in _STATS.items():
        if key in field_lower:
            return (
                f"Field statistics for '{key}':\n"
                f"  Adoption rate: {stats['adoption_rate']}\n"
                f"  Papers/year:   {stats['papers_per_year']}\n"
                f"  Top frameworks: {stats['top_frameworks']}"
            )
    return f"No statistics found for '{field}'."


@tool
def summarize_paper(paper_id: str) -> str:
    """Get a detailed summary of a specific paper by its ID.

    Args:
        paper_id: Paper ID from search results (e.g., 'paper_001').
    """
    for papers in _PAPERS.values():
        for p in papers:
            if p["id"] == paper_id:
                return (
                    f"Paper: {p['title']} ({p['year']})\n"
                    f"Authors: {p['authors']}\n"
                    f"Summary: {p['abstract']}"
                )
    return f"Paper {paper_id} not found."


@tool
def format_citations(paper_ids: str) -> str:
    """Format papers as academic citations (APA style).

    Args:
        paper_ids: Comma-separated list of paper IDs.
    """
    ids = [pid.strip() for pid in paper_ids.split(",")]
    citations = []
    for paper_id in ids:
        for papers in _PAPERS.values():
            for p in papers:
                if p["id"] == paper_id:
                    citations.append(f"{p['authors']} ({p['year']}). {p['title']}.")
    if citations:
        return "References:\n" + "\n".join(f"[{i+1}] {c}" for i, c in enumerate(citations))
    return "No valid paper IDs found."


RESEARCH_SYSTEM = """You are a systematic research assistant. For each research request:
1. Search for relevant papers on the topic
2. Get field statistics to understand the landscape
3. Summarize the most important paper(s)
4. Format proper citations
5. Write a concise 3-paragraph research brief covering: background, key findings, implications
"""

graph = create_agent(
    llm,
    tools=[search_papers, get_field_statistics, summarize_paper, format_citations],
    name="research_assistant_agent",
    system_prompt=RESEARCH_SYSTEM,
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "Research the transformer architecture and its impact on modern AI.",
        )
        print(f"Status: {result.status}")
        result.print_result()
