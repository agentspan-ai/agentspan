"""Web search tools — Brave Search API integration."""

from __future__ import annotations

import os
from typing import Any, Dict, List

import httpx

from agentspan.agents import tool


@tool(credentials=["BRAVE_API_KEY"])
def web_search(query: str, count: int = 5) -> List[Dict[str, str]]:
    """Search the web using the Brave Search API.

    Args:
        query: The search query string.
        count: Number of results to return (default 5, max 20).

    Returns:
        List of dicts with ``title``, ``url``, and ``description`` keys.
    """
    api_key = os.environ.get("BRAVE_API_KEY", "")
    if not api_key:
        raise RuntimeError("BRAVE_API_KEY environment variable is not set")

    count = min(max(count, 1), 20)

    resp = httpx.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": count},
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        },
        timeout=15.0,
    )
    resp.raise_for_status()

    data = resp.json()
    results: List[Dict[str, str]] = []
    for item in data.get("web", {}).get("results", []):
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "description": item.get("description", ""),
        })

    return results


def get_tools() -> List[Any]:
    """Return all web_search tools."""
    return [web_search]
