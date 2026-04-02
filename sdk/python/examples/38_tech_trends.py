# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""
Tech Trend Analyzer — Multi-agent research + analysis + PDF pipeline.

Compares two programming languages using real data from:
  - HackerNews (community discussion, via Algolia search API)
  - PyPI Stats (Python package downloads)
  - NPM (JavaScript ecosystem downloads)
  - Wikipedia (background / ecosystem context)

Architecture:
    researcher >> analyst >> pdf_generator  (sequential pipeline)

    researcher tools:
        search_hackernews      — Algolia HN search API
        get_hn_story_comments  — HN item API (top comments)
        get_wikipedia_summary  — Wikipedia REST API

    analyst tools:
        fetch_pypi_downloads   — pypistats.org (pip package monthly downloads)
        fetch_npm_downloads    — api.npmjs.org (npm package monthly downloads)
        compare_numbers        — simple ratio / gap computation

    pdf_generator tools:
        generate_pdf           — Conductor GENERATE_PDF task (markdown → PDF)

Run:
    Export as environment variables:
        AGENTSPAN_SERVER_URL=https://developer.orkescloud.com/api
        AGENTSPAN_AUTH_KEY=<key>
        AGENTSPAN_AUTH_SECRET=<secret>
    python 38_tech_trends.py
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

from agentspan.agents import Agent, AgentRuntime, pdf_tool, tool
from settings import settings

# ── Researcher tools (HackerNews + Wikipedia) ────────────────────────────────


@tool
def search_hackernews(query: str, max_results: int = 8) -> dict:
    """Search HackerNews for stories about a technology topic.

    Returns a list of recent stories with title, points, comment count,
    author, and story ID. Use the story ID with get_hn_story_comments
    to fetch the top discussion threads.
    """
    url = (
        "https://hn.algolia.com/api/v1/search"
        f"?query={urllib.parse.quote(query)}"
        "&tags=story"
        f"&hitsPerPage={max(1, min(max_results, 20))}"
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        stories = [
            {
                "id": h.get("objectID", ""),
                "title": h.get("title", ""),
                "points": h.get("points") or 0,
                "num_comments": h.get("num_comments") or 0,
                "author": h.get("author", ""),
                "created_at": h.get("created_at", "")[:10],
                "story_url": h.get("url", ""),
            }
            for h in data.get("hits", [])
        ]
        return {
            "query": query,
            "total_found": data.get("nbHits", 0),
            "stories": stories,
        }
    except Exception as exc:
        return {"query": query, "error": str(exc), "stories": []}


@tool
def get_hn_story_comments(story_id: str) -> dict:
    """Fetch the top comments for a HackerNews story by its numeric ID.

    Returns the story title, score, and up to 8 top-level comment
    excerpts (first 400 chars each, HTML stripped).
    """
    url = f"https://hn.algolia.com/api/v1/items/{story_id}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        comments = []
        for child in (data.get("children") or [])[:8]:
            raw = child.get("text") or ""
            clean = re.sub(r"<[^>]+>", " ", raw).strip()
            clean = re.sub(r"\s+", " ", clean)[:400]
            if clean:
                comments.append({"author": child.get("author", ""), "text": clean})

        return {
            "story_id": story_id,
            "title": data.get("title", ""),
            "points": data.get("points") or 0,
            "comment_count": len(data.get("children") or []),
            "top_comments": comments,
        }
    except Exception as exc:
        return {"story_id": story_id, "error": str(exc), "top_comments": []}


@tool
def get_wikipedia_summary(topic: str) -> dict:
    """Fetch the Wikipedia introduction paragraph for a technology or topic.

    Returns the page title, a short description, and the first ~800
    characters of the article extract.
    """
    encoded = urllib.parse.quote(topic.replace(" ", "_"))
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
    req = urllib.request.Request(url, headers={"User-Agent": "TechTrendAnalyzer/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        return {
            "topic": topic,
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "extract": (data.get("extract") or "")[:800],
        }
    except Exception as exc:
        return {"topic": topic, "error": str(exc), "extract": ""}


# ── Analyst tools (package registries + math) ────────────────────────────────


@tool
def fetch_pypi_downloads(package: str) -> dict:
    """Fetch recent PyPI download statistics for a Python package.

    Returns last-day, last-week, and last-month download counts from
    pypistats.org. Use 'pip' for Python's package installer as a proxy
    for the Python ecosystem health.
    """
    url = f"https://pypistats.org/api/packages/{urllib.parse.quote(package)}/recent"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        row = data.get("data", {})
        return {
            "package": package,
            "last_day": row.get("last_day", 0),
            "last_week": row.get("last_week", 0),
            "last_month": row.get("last_month", 0),
        }
    except Exception as exc:
        return {"package": package, "error": str(exc)}


@tool
def fetch_npm_downloads(package: str) -> dict:
    """Fetch last-month download count for an npm package.

    Use this for JavaScript/TypeScript ecosystem packages. For example,
    'typescript' for TypeScript usage or 'react' for React adoption.
    """
    encoded = urllib.parse.quote(package)
    url = f"https://api.npmjs.org/downloads/point/last-month/{encoded}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        return {
            "package": package,
            "downloads_last_month": data.get("downloads", 0),
            "start": data.get("start", ""),
            "end": data.get("end", ""),
        }
    except Exception as exc:
        return {"package": package, "error": str(exc)}


@tool
def compare_numbers(
    label_a: str,
    value_a: float,
    label_b: str,
    value_b: float,
    metric: str,
) -> dict:
    """Compute ratio and percentage difference between two numeric values.

    Useful for comparing HN story counts, average engagement scores,
    download figures, or any two quantities head-to-head.
    """
    if value_b == 0:
        ratio = float("inf") if value_a > 0 else 1.0
        pct_diff = 100.0
    else:
        ratio = round(value_a / value_b, 3)
        pct_diff = round(abs(value_a - value_b) / value_b * 100, 1)

    winner = label_a if value_a >= value_b else label_b
    return {
        "metric": metric,
        label_a: value_a,
        label_b: value_b,
        "ratio": f"{label_a}/{label_b} = {ratio}",
        "pct_difference": f"{pct_diff}%",
        "winner": winner,
    }


# ── Agent definitions ─────────────────────────────────────────────────────────

researcher = Agent(
    name="hn_researcher",
    model=settings.llm_model,
    tools=[search_hackernews, get_hn_story_comments, get_wikipedia_summary],
    max_tokens=4000,
    instructions=(
        "You are a technology research assistant. You MUST call tools to gather real data. "
        "Do NOT describe what you are going to do — just call the tools immediately.\n\n"
        "REQUIRED STEPS (call tools in this exact order):\n"
        "1. Call search_hackernews(query='Python programming language', max_results=8)\n"
        "2. Call search_hackernews(query='Rust programming language', max_results=8)\n"
        "3. From the Python results, call get_hn_story_comments on the story with the most comments\n"
        "4. From the Rust results, call get_hn_story_comments on the story with the most comments\n"
        "5. Call get_wikipedia_summary(topic='Python (programming language)')\n"
        "6. Call get_wikipedia_summary(topic='Rust (programming language)')\n\n"
        "After ALL 6 tool calls are complete, write a structured report with REAL data:\n\n"
        "RESEARCH DATA: Python\n"
        "- HN stories found: [actual number from tool result]\n"
        "- Stories: [list each story title | points | num_comments]\n"
        "- Top discussion (story title): [actual comment excerpts]\n"
        "- Wikipedia: [actual description and extract]\n\n"
        "RESEARCH DATA: Rust\n"
        "- HN stories found: [actual number from tool result]\n"
        "- Stories: [list each story title | points | num_comments]\n"
        "- Top discussion (story title): [actual comment excerpts]\n"
        "- Wikipedia: [actual description and extract]\n\n"
        "Include REAL numbers and titles — no placeholders."
    ),
)

analyst = Agent(
    name="hn_analyst",
    model=settings.llm_model,
    tools=[fetch_pypi_downloads, fetch_npm_downloads, compare_numbers],
    max_tokens=4000,
    instructions=(
        "You are a technology trend analyst. You will receive real research data about Python and "
        "Rust gathered from HackerNews and Wikipedia. You MUST call tools — do not describe what "
        "you will do, just do it.\n\n"
        "REQUIRED STEPS:\n"
        "1. Call fetch_pypi_downloads(package='pip') — Python ecosystem proxy\n"
        "2. Call fetch_pypi_downloads(package='maturin') — Rust/Python interop proxy\n"
        "3. Call fetch_npm_downloads(package='wasm-pack') — Rust WebAssembly proxy\n"
        "4. Count the Python stories and compute average points/comments from the research data. "
        "   Then call compare_numbers(label_a='Python', value_a=<avg_points>, "
        "   label_b='Rust', value_b=<avg_points>, metric='avg_points_per_story')\n"
        "5. Call compare_numbers for avg_comments_per_story similarly\n\n"
        "After ALL tool calls, write a final markdown report:\n\n"
        "# Tech Trend Analysis: Python vs Rust\n\n"
        "## Executive Summary\n"
        "(2-3 sentence verdict using actual data)\n\n"
        "## Head-to-Head: HackerNews Engagement\n"
        "(table with real numbers: stories found, avg points, avg comments)\n\n"
        "## Ecosystem Adoption (Package Downloads)\n"
        "(pip, maturin, wasm-pack download counts and what they mean)\n\n"
        "## Top Stories on HackerNews\n"
        "(top 3 for each with real titles, points, comments)\n\n"
        "## Developer Sentiment\n"
        "(key themes from real comment excerpts)\n\n"
        "## Verdict\n"
        "(data-driven conclusion)\n"
    ),
)

# ── PDF generator agent ────────────────────────────────────────────────────────

pdf_generator = Agent(
    name="pdf_report_generator",
    model=settings.llm_model,
    tools=[pdf_tool()],
    max_tokens=4000,
    instructions=(
        "You receive a markdown report. Your ONLY job is to call the generate_pdf "
        "tool with the full markdown content to produce a PDF document. "
        "Pass the entire report as the 'markdown' parameter. "
        "Do not modify or summarize the content — pass it through as-is."
    ),
)

# ── Sequential pipeline: researcher feeds analyst, analyst feeds PDF generator ─

pipeline = researcher >> analyst >> pdf_generator


if __name__ == "__main__":
    print("Starting Tech Trend Analyzer: Python vs Rust")
    print("=" * 60)

    with AgentRuntime() as runtime:
        result = runtime.run(
            pipeline,
            "Compare Python and Rust: which has stronger developer mindshare and "
            "ecosystem momentum right now? Use real HackerNews data and package "
            "download statistics to support your analysis.",
        )
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(pipeline)
        # CLI alternative:
        # agentspan deploy --package examples.38_tech_trends
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(pipeline)
