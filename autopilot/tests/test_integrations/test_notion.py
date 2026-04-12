"""Tests for notion integration tools."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from autopilot.integrations.notion.tools import (
    get_tools,
    notion_create_page,
    notion_query_database,
    notion_read_page,
    notion_search,
)


class TestNotionSearch:
    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("NOTION_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="NOTION_API_KEY"):
            notion_search("test")

    def test_empty_query_raises(self, monkeypatch):
        monkeypatch.setenv("NOTION_API_KEY", "ntn_test_key")
        with pytest.raises(ValueError, match="query is required"):
            notion_search("")

    def test_successful_search(self, monkeypatch):
        monkeypatch.setenv("NOTION_API_KEY", "ntn_test_key")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": [
                {
                    "id": "page1",
                    "object": "page",
                    "url": "https://notion.so/page1",
                    "properties": {
                        "Name": {
                            "title": [{"plain_text": "My Page"}]
                        }
                    },
                }
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        monkeypatch.setattr(
            "autopilot.integrations.notion.tools.httpx.post",
            lambda *a, **kw: mock_resp,
        )

        results = notion_search("My Page")
        assert len(results) == 1
        assert results[0]["title"] == "My Page"
        assert results[0]["type"] == "page"

    def test_credentials_on_tool_def(self):
        assert notion_search._tool_def.credentials == ["NOTION_API_KEY"]


class TestNotionReadPage:
    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("NOTION_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="NOTION_API_KEY"):
            notion_read_page("page1")

    def test_empty_page_id_raises(self, monkeypatch):
        monkeypatch.setenv("NOTION_API_KEY", "ntn_test_key")
        with pytest.raises(ValueError, match="page_id is required"):
            notion_read_page("")

    def test_successful_read(self, monkeypatch):
        monkeypatch.setenv("NOTION_API_KEY", "ntn_test_key")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": [
                {
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"plain_text": "Hello world"}]
                    },
                },
                {
                    "type": "heading_1",
                    "heading_1": {
                        "rich_text": [{"plain_text": "Title"}]
                    },
                },
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        monkeypatch.setattr(
            "autopilot.integrations.notion.tools.httpx.get",
            lambda *a, **kw: mock_resp,
        )

        result = notion_read_page("page1")
        assert "Hello world" in result
        assert "Title" in result

    def test_credentials_on_tool_def(self):
        assert notion_read_page._tool_def.credentials == ["NOTION_API_KEY"]


class TestNotionQueryDatabase:
    def test_empty_database_id_raises(self, monkeypatch):
        monkeypatch.setenv("NOTION_API_KEY", "ntn_test_key")
        with pytest.raises(ValueError, match="database_id is required"):
            notion_query_database("")

    def test_successful_query(self, monkeypatch):
        monkeypatch.setenv("NOTION_API_KEY", "ntn_test_key")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": [
                {"id": "row1", "properties": {}},
                {"id": "row2", "properties": {}},
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        monkeypatch.setattr(
            "autopilot.integrations.notion.tools.httpx.post",
            lambda *a, **kw: mock_resp,
        )

        results = notion_query_database("db1")
        assert len(results) == 2

    def test_credentials_on_tool_def(self):
        assert notion_query_database._tool_def.credentials == ["NOTION_API_KEY"]


class TestNotionCreatePage:
    def test_empty_parent_id_raises(self, monkeypatch):
        monkeypatch.setenv("NOTION_API_KEY", "ntn_test_key")
        with pytest.raises(ValueError, match="parent_id is required"):
            notion_create_page("", "Title")

    def test_empty_title_raises(self, monkeypatch):
        monkeypatch.setenv("NOTION_API_KEY", "ntn_test_key")
        with pytest.raises(ValueError, match="title is required"):
            notion_create_page("parent1", "")

    def test_successful_create(self, monkeypatch):
        monkeypatch.setenv("NOTION_API_KEY", "ntn_test_key")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "id": "new_page",
            "url": "https://notion.so/new_page",
        }
        mock_resp.raise_for_status = MagicMock()

        monkeypatch.setattr(
            "autopilot.integrations.notion.tools.httpx.post",
            lambda *a, **kw: mock_resp,
        )

        result = notion_create_page("parent1", "New Page", "Some content")
        assert result["id"] == "new_page"

    def test_credentials_on_tool_def(self):
        assert notion_create_page._tool_def.credentials == ["NOTION_API_KEY"]


class TestGetTools:
    def test_returns_all_tools(self):
        tools = get_tools()
        names = [t._tool_def.name for t in tools]
        assert "notion_search" in names
        assert "notion_read_page" in names
        assert "notion_query_database" in names
        assert "notion_create_page" in names
        assert len(tools) == 4
