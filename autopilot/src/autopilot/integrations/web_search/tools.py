"""Agentic web search tools — DDG + Brave + page fetch + content extraction."""

from __future__ import annotations

import os
from typing import Any, Dict, List

import httpx
import trafilatura
from ddgs import DDGS

from agentspan.agents import tool

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_DEFAULT_TIMEOUT = 15.0
_MAX_PAGE_CHARS = 10_000


# ── Internal helpers ─────────────────────────────────────────────────────


def _search_ddg(query: str, count: int) -> List[Dict[str, str]]:
    """Search DuckDuckGo using the ddgs library (no API key required).

    Runs in a subprocess to avoid fork() crashes with ddgs/primp's Rust bindings
    when called from Conductor worker processes (which are forked).
    """
    import json
    import subprocess
    import sys

    # Run DDG search in a clean subprocess to avoid fork+Rust crash
    script = f"""
import json
from ddgs import DDGS
results = list(DDGS().text({query!r}, max_results={count}))
out = [{{"title": r.get("title",""), "url": r.get("href",""), "snippet": r.get("body","")}} for r in results]
print(json.dumps(out))
"""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return json.loads(proc.stdout.strip())
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        pass

    # Fallback: try direct call (works in main process, may crash in forked workers)
    try:
        raw = list(DDGS().text(query, max_results=count))
        return [
            {"title": item.get("title", ""), "url": item.get("href", ""), "snippet": item.get("body", "")}
            for item in raw
        ]
    except Exception:
        return []


def _search_brave(query: str, count: int) -> List[Dict[str, str]]:
    """Search using Brave Search API (requires BRAVE_API_KEY)."""
    api_key = os.environ.get("BRAVE_API_KEY", "")
    if not api_key:
        return []

    resp = httpx.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": count},
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        },
        timeout=_DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()

    data = resp.json()
    results: List[Dict[str, str]] = []
    for item in data.get("web", {}).get("results", []):
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("description", ""),
        })

    return results


def _fetch_and_extract(url: str, max_chars: int = _MAX_PAGE_CHARS) -> Dict[str, str]:
    """Fetch a URL and extract clean text content using trafilatura."""
    try:
        resp = httpx.get(
            url,
            headers={"User-Agent": _USER_AGENT},
            timeout=_DEFAULT_TIMEOUT,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except httpx.TimeoutException:
        return {"url": url, "content": "", "error": f"Timeout fetching {url}"}
    except httpx.HTTPStatusError as exc:
        return {"url": url, "content": "", "error": f"HTTP {exc.response.status_code} for {url}"}
    except httpx.RequestError as exc:
        return {"url": url, "content": "", "error": f"Request error for {url}: {exc}"}

    content = trafilatura.extract(resp.text) or ""
    if len(content) > max_chars:
        content = content[:max_chars] + "\n\n[... truncated]"

    return {"url": url, "content": content, "error": ""}


# ── Public tool functions ────────────────────────────────────────────────


@tool
def web_search(query: str, count: int = 5) -> List[Dict[str, str]]:
    """Search the web and return result titles, URLs, and snippets.

    Uses DuckDuckGo (no API key needed) as the default source.
    If BRAVE_API_KEY is set, also queries Brave Search API and merges results
    (Brave results first, then DDG results for any URLs not already present).

    Args:
        query: The search query string.
        count: Number of results to return (default 5, max 20).

    Returns:
        List of dicts with ``title``, ``url``, and ``snippet`` keys.
    """
    count = min(max(count, 1), 20)

    # Always search DDG (no API key needed)
    ddg_results = _search_ddg(query, count)

    # Optionally augment with Brave results
    brave_results: List[Dict[str, str]] = []
    if os.environ.get("BRAVE_API_KEY"):
        try:
            brave_results = _search_brave(query, count)
        except Exception:
            pass  # Brave is optional; DDG is the fallback

    if not brave_results:
        return ddg_results[:count]

    # Merge: Brave first, then DDG for any unseen URLs
    seen_urls = {r["url"] for r in brave_results}
    merged = list(brave_results)
    for r in ddg_results:
        if r["url"] not in seen_urls:
            merged.append(r)
            seen_urls.add(r["url"])

    return merged[:count]


@tool
def fetch_page(url: str, max_chars: int = _MAX_PAGE_CHARS) -> Dict[str, str]:
    """Fetch a web page and extract its main text content.

    Uses trafilatura to extract clean, readable text from the HTML.
    This is the tool to use when you want to read the actual content of a page
    you found via web_search.

    Args:
        url: The URL to fetch.
        max_chars: Maximum characters to return (default 10000).

    Returns:
        Dict with ``url``, ``content`` (extracted text), and ``error`` (empty string if OK).
    """
    max_chars = min(max(max_chars, 100), 50_000)
    return _fetch_and_extract(url, max_chars=max_chars)


@tool
def search_and_read(query: str, count: int = 3, max_chars_per_page: int = 5000) -> List[Dict[str, str]]:
    """Search the web, then fetch and extract content from the top results.

    This is the power tool for deep research: it searches for the query,
    then fetches each result page and extracts its main text content.

    Args:
        query: The search query string.
        count: Number of top results to fetch and read (default 3, max 5).
        max_chars_per_page: Maximum characters per page (default 5000).

    Returns:
        List of dicts with ``title``, ``url``, ``snippet``, ``content``, and ``error`` keys.
    """
    count = min(max(count, 1), 5)
    max_chars_per_page = min(max(max_chars_per_page, 100), 20_000)

    search_results = web_search(query, count=count)

    enriched: List[Dict[str, str]] = []
    for result in search_results[:count]:
        page = _fetch_and_extract(result["url"], max_chars=max_chars_per_page)
        enriched.append({
            "title": result.get("title", ""),
            "url": result["url"],
            "snippet": result.get("snippet", ""),
            "content": page.get("content", ""),
            "error": page.get("error", ""),
        })

    return enriched


def get_tools() -> List[Any]:
    """Return all web_search tools."""
    return [web_search, fetch_page, search_and_read]
