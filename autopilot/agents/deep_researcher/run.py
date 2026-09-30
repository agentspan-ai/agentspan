#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Deep Researcher — multi-agent research pipeline.

A sequential pipeline of four agents:
  Research Planner >> Web Researcher >> Analyst >> Report Writer

Usage:
    python run.py "What are the latest advances in quantum computing?"

Requirements:
    - Conductor server at AGENTSPAN_SERVER_URL (default http://localhost:6767/api)
    - AGENTSPAN_LLM_MODEL (default openai/gpt-4o)
    - BRAVE_API_KEY (optional — falls back to simulated web search)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Ensure the agentspan SDK is importable from the local source tree.
_SDK_SRC = str(Path(__file__).resolve().parent.parent.parent.parent / "sdk" / "python" / "src")
if _SDK_SRC not in sys.path:
    sys.path.insert(0, _SDK_SRC)

os.environ.setdefault("AGENTSPAN_LOG_LEVEL", "WARNING")

from agentspan.agents import Agent, AgentRuntime, Strategy, tool

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

LLM_MODEL = os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o")
SECONDARY_LLM_MODEL = os.environ.get("AGENTSPAN_SECONDARY_LLM_MODEL", "openai/gpt-4o")
BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def _brave_search(query: str, count: int = 5) -> list[dict]:
    """Call Brave Search API. Returns a list of {title, url, snippet} dicts."""
    import httpx

    resp = httpx.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": count},
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": BRAVE_API_KEY,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    results = []
    for item in data.get("web", {}).get("results", []):
        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("description", ""),
            }
        )
    return results


def _simulated_search(query: str, count: int = 5) -> list[dict]:
    """Return placeholder results when no Brave API key is configured."""
    return [
        {
            "title": f"Result {i + 1} for: {query}",
            "url": f"https://example.com/search?q={query.replace(' ', '+')}&r={i + 1}",
            "snippet": (
                f"This is a simulated search result for '{query}'. "
                f"In production, this would contain real content from the web. "
                f"Set BRAVE_API_KEY to enable live web search."
            ),
        }
        for i in range(count)
    ]


@tool
def web_search(query: str, num_results: int = 5) -> str:
    """Search the web for information on a topic. Returns titles, URLs, and snippets."""
    try:
        if BRAVE_API_KEY:
            results = _brave_search(query, count=num_results)
        else:
            results = _simulated_search(query, count=num_results)
    except Exception as exc:
        return f"Search error: {exc}"

    if not results:
        return f"No results found for: {query}"

    lines = []
    for r in results:
        lines.append(f"**{r['title']}**")
        lines.append(f"  URL: {r['url']}")
        lines.append(f"  {r['snippet']}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

planner = Agent(
    name="research_planner",
    model=LLM_MODEL,
    instructions="""\
You are a research planner. Given a research topic, break it down into 3-5
focused sub-questions that together will provide comprehensive coverage.

For each sub-question, briefly explain why it matters to the overall topic.

Output your plan as a numbered list in this exact format:

1. [Sub-question here]
   Why: [Brief rationale]

2. [Sub-question here]
   Why: [Brief rationale]

...

Be specific and actionable. Each sub-question should be something that can be
answered through web research. Do not include vague or overly broad questions.
""",
)

researcher = Agent(
    name="web_researcher",
    model=SECONDARY_LLM_MODEL,
    instructions="""\
You are a web researcher. You receive a research plan with numbered sub-questions.

For EACH sub-question in the plan:
1. Use the web_search tool to find relevant information.
2. Extract key facts, data points, and quotes from the results.
3. Note the source URLs for attribution.

After searching all sub-questions, compile your findings in this format:

## Findings for Sub-question 1: [question text]
- [Key finding with source URL]
- [Key finding with source URL]
...

## Findings for Sub-question 2: [question text]
- [Key finding with source URL]
...

(continue for all sub-questions)

Be thorough. Search for each sub-question individually. Include specific data,
dates, names, and numbers when available.
""",
    tools=[web_search],
    max_turns=15,
)

analyst = Agent(
    name="analyst",
    model=LLM_MODEL,
    instructions="""\
You are a research analyst. You receive raw research findings organized by
sub-question.

Your job is to synthesize these findings into coherent analysis:

1. **Key Themes**: Identify 3-5 major themes that emerge across the findings.
2. **Consensus Views**: What do most sources agree on?
3. **Contradictions**: Where do sources disagree? Why might that be?
4. **Knowledge Gaps**: What important aspects lack good evidence?
5. **Implications**: What are the broader implications of these findings?

Write your analysis in clear, professional prose. Reference specific findings
to support your points. Do not simply repeat the raw findings — add analytical
value by connecting dots and drawing insights.
""",
)

report_writer = Agent(
    name="report_writer",
    model=LLM_MODEL,
    instructions="""\
You are a report writer. You receive an analytical synthesis and must produce
a polished, well-structured research report.

Structure your report as follows:

# [Research Topic Title]

## Executive Summary
A 2-3 paragraph overview of the key findings and conclusions.

## Background
Brief context on why this topic matters.

## Key Findings
Organized thematically with clear headers for each major finding area.

## Analysis
Deeper exploration of implications, trends, and connections.

## Conclusion
Summary of the most important takeaways and potential future developments.

## Sources
List of source URLs referenced in the findings.

Write in a clear, authoritative tone. Use specific data and examples.
Keep the report focused and avoid unnecessary padding.
""",
)

# ── Sequential pipeline ──────────────────────────────────────────────
pipeline = planner >> researcher >> analyst >> report_writer


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python run.py \"<research topic>\"")
        print("Example: python run.py \"What are the latest advances in quantum computing?\"")
        sys.exit(1)

    topic = " ".join(sys.argv[1:])
    search_mode = "Brave API" if BRAVE_API_KEY else "simulated (set BRAVE_API_KEY for live search)"

    print(f"Deep Researcher")
    print(f"{'=' * 62}")
    print(f"  Topic  : {topic}")
    print(f"  Model  : {LLM_MODEL}")
    print(f"  Search : {search_mode}")
    print(f"  Server : {os.environ.get('AGENTSPAN_SERVER_URL', 'http://localhost:6767/api')}")
    print(f"{'=' * 62}")
    print()
    print("Running pipeline: Planner >> Researcher >> Analyst >> Report Writer")
    print("This may take a few minutes...\n")

    with AgentRuntime() as runtime:
        result = runtime.run(pipeline, topic)
        print()
        print("=" * 62)
        print("RESEARCH REPORT")
        print("=" * 62)
        print()
        result.print_result()


if __name__ == "__main__":
    main()
