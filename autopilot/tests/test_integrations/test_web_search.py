"""End-to-end tests for agentic web search tools.

All tests hit real endpoints — NO mocks. Tests requiring network access are
marked with ``@pytest.mark.network`` so they can be skipped in offline CI via
``pytest -m "not network"``.
"""

from __future__ import annotations

import pytest

from autopilot.integrations.web_search.tools import (
    fetch_page,
    get_tools,
    search_and_read,
    web_search,
)


@pytest.mark.network
class TestWebSearch:
    """web_search tool — real DDG queries."""

    def test_web_search_returns_results(self):
        results = web_search("python programming language", count=5)

        assert isinstance(results, list)
        assert len(results) >= 1, "Expected at least 1 search result"

        first = results[0]
        assert "title" in first
        assert "url" in first
        assert "snippet" in first
        assert first["url"].startswith("http")

    def test_web_search_results_are_relevant(self):
        results = web_search("python programming language", count=5)

        # At least one result should mention python somewhere in title, url, or snippet
        has_python = any(
            "python" in (r.get("title", "") + r.get("url", "") + r.get("snippet", "")).lower()
            for r in results
        )
        assert has_python, f"No result mentions 'python': {results}"

    def test_web_search_count_respected(self):
        results = web_search("wikipedia", count=3)
        assert len(results) <= 3

    def test_web_search_count_clamped(self):
        # count > 20 should be clamped to 20
        results = web_search("test", count=50)
        assert len(results) <= 20


@pytest.mark.network
class TestFetchPage:
    """fetch_page tool — real HTTP fetches."""

    def test_fetch_page_extracts_content(self):
        result = fetch_page("https://httpbin.org/html")

        assert result["url"] == "https://httpbin.org/html"
        assert result["error"] == ""
        assert len(result["content"]) > 0, "Expected non-empty extracted content"

    def test_fetch_page_bad_url(self):
        result = fetch_page("https://httpbin.org/status/404")

        assert result["url"] == "https://httpbin.org/status/404"
        assert result["error"] != "", "Expected a non-empty error for 404 URL"
        assert "404" in result["error"]

    def test_fetch_page_nonexistent_domain(self):
        result = fetch_page("https://this-domain-does-not-exist-12345.example.com/page")

        assert result["error"] != "", "Expected a non-empty error for nonexistent domain"

    def test_fetch_page_respects_max_chars(self):
        result = fetch_page("https://httpbin.org/html", max_chars=200)

        # Content should be truncated near the limit (with truncation marker)
        if result["content"]:
            assert len(result["content"]) <= 200 + len("\n\n[... truncated]") + 10


@pytest.mark.network
class TestSearchAndRead:
    """search_and_read tool — real search + fetch."""

    def test_search_and_read_returns_content(self):
        results = search_and_read("httpbin.org", count=1, max_chars_per_page=2000)

        assert isinstance(results, list)
        assert len(results) >= 1

        first = results[0]
        assert "title" in first
        assert "url" in first
        assert "snippet" in first
        assert "content" in first
        assert "error" in first

    def test_search_and_read_count_clamped(self):
        # count > 5 should be clamped to 5
        results = search_and_read("python", count=10)
        assert len(results) <= 5


@pytest.mark.network
class TestBraveSearchWithoutKey:
    """Verify that web_search works without BRAVE_API_KEY."""

    def test_works_without_brave_key(self, monkeypatch):
        monkeypatch.delenv("BRAVE_API_KEY", raising=False)

        results = web_search("python programming", count=3)

        assert isinstance(results, list)
        assert len(results) >= 1, "DDG fallback should return results even without Brave key"
        assert results[0]["url"].startswith("http")


class TestGetTools:
    """get_tools registry helper."""

    def test_returns_all_tools(self):
        tools = get_tools()
        names = {t._tool_def.name for t in tools}
        assert names == {"web_search", "fetch_page", "search_and_read"}

    def test_tool_count(self):
        tools = get_tools()
        assert len(tools) == 3
