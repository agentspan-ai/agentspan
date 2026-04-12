"""Tests for web_search integration tools."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from autopilot.integrations.web_search.tools import get_tools, web_search


class TestWebSearch:
    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("BRAVE_API_KEY", raising=False)

        with pytest.raises(RuntimeError, match="BRAVE_API_KEY"):
            web_search("test query")

    def test_successful_search(self, monkeypatch):
        monkeypatch.setenv("BRAVE_API_KEY", "test-key-123")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "web": {
                "results": [
                    {
                        "title": "Example",
                        "url": "https://example.com",
                        "description": "An example result",
                    },
                    {
                        "title": "Another",
                        "url": "https://another.com",
                        "description": "Another result",
                    },
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()

        monkeypatch.setattr("autopilot.integrations.web_search.tools.httpx.get", lambda *a, **kw: mock_response)

        results = web_search("test query")

        assert len(results) == 2
        assert results[0]["title"] == "Example"
        assert results[1]["url"] == "https://another.com"

    def test_count_clamped_to_range(self, monkeypatch):
        monkeypatch.setenv("BRAVE_API_KEY", "test-key")

        captured_params = {}

        def mock_get(*args, **kwargs):
            captured_params.update(kwargs.get("params", {}))
            resp = MagicMock()
            resp.json.return_value = {"web": {"results": []}}
            resp.raise_for_status = MagicMock()
            return resp

        monkeypatch.setattr("autopilot.integrations.web_search.tools.httpx.get", mock_get)

        # count=50 should be clamped to 20
        web_search("test", count=50)
        assert captured_params["count"] == 20

    def test_empty_results(self, monkeypatch):
        monkeypatch.setenv("BRAVE_API_KEY", "key")

        mock_response = MagicMock()
        mock_response.json.return_value = {"web": {"results": []}}
        mock_response.raise_for_status = MagicMock()

        monkeypatch.setattr("autopilot.integrations.web_search.tools.httpx.get", lambda *a, **kw: mock_response)

        results = web_search("nothing")
        assert results == []

    def test_credentials_on_tool_def(self):
        assert web_search._tool_def.credentials == ["BRAVE_API_KEY"]


class TestGetTools:
    def test_returns_web_search(self):
        tools = get_tools()
        assert len(tools) == 1
        assert tools[0]._tool_def.name == "web_search"
