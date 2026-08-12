"""Tests for notion integration tools — credential validation and tool metadata.

# NOTE: These tests verify credential validation and tool metadata.
# Full API integration tests require real credentials and are run
# via the e2e test suite with deployed agents.
"""

from __future__ import annotations

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

    def test_credentials_on_tool_def(self):
        assert notion_search._tool_def.credentials == ["NOTION_API_KEY"]

    def test_tool_def_name(self):
        assert notion_search._tool_def.name == "notion_search"

    def test_tool_def_has_description(self):
        assert notion_search._tool_def.description
        assert len(notion_search._tool_def.description) > 10


class TestNotionReadPage:
    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("NOTION_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="NOTION_API_KEY"):
            notion_read_page("page1")

    def test_empty_page_id_raises(self, monkeypatch):
        monkeypatch.setenv("NOTION_API_KEY", "ntn_test_key")
        with pytest.raises(ValueError, match="page_id is required"):
            notion_read_page("")

    def test_credentials_on_tool_def(self):
        assert notion_read_page._tool_def.credentials == ["NOTION_API_KEY"]

    def test_tool_def_name(self):
        assert notion_read_page._tool_def.name == "notion_read_page"


class TestNotionQueryDatabase:
    def test_empty_database_id_raises(self, monkeypatch):
        monkeypatch.setenv("NOTION_API_KEY", "ntn_test_key")
        with pytest.raises(ValueError, match="database_id is required"):
            notion_query_database("")

    def test_credentials_on_tool_def(self):
        assert notion_query_database._tool_def.credentials == ["NOTION_API_KEY"]

    def test_tool_def_name(self):
        assert notion_query_database._tool_def.name == "notion_query_database"


class TestNotionCreatePage:
    def test_empty_parent_id_raises(self, monkeypatch):
        monkeypatch.setenv("NOTION_API_KEY", "ntn_test_key")
        with pytest.raises(ValueError, match="parent_id is required"):
            notion_create_page("", "Title")

    def test_empty_title_raises(self, monkeypatch):
        monkeypatch.setenv("NOTION_API_KEY", "ntn_test_key")
        with pytest.raises(ValueError, match="title is required"):
            notion_create_page("parent1", "")

    def test_credentials_on_tool_def(self):
        assert notion_create_page._tool_def.credentials == ["NOTION_API_KEY"]

    def test_tool_def_name(self):
        assert notion_create_page._tool_def.name == "notion_create_page"


class TestGetTools:
    def test_returns_all_tools(self):
        tools = get_tools()
        names = [t._tool_def.name for t in tools]
        assert "notion_search" in names
        assert "notion_read_page" in names
        assert "notion_query_database" in names
        assert "notion_create_page" in names
        assert len(tools) == 4
