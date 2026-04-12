"""Tests for linear integration tools — real e2e, no mocks."""

from __future__ import annotations

import pytest

from autopilot.integrations.linear.tools import (
    get_tools,
    linear_create_issue,
    linear_get_issue,
    linear_list_issues,
    linear_update_issue,
)


class TestLinearListIssues:
    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("LINEAR_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="LINEAR_API_KEY"):
            linear_list_issues()

    def test_credentials_on_tool_def(self):
        assert linear_list_issues._tool_def.credentials == ["LINEAR_API_KEY"]

    def test_tool_def_name(self):
        assert linear_list_issues._tool_def.name == "linear_list_issues"

    def test_tool_def_has_description(self):
        assert linear_list_issues._tool_def.description
        assert len(linear_list_issues._tool_def.description) > 10


class TestLinearGetIssue:
    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("LINEAR_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="LINEAR_API_KEY"):
            linear_get_issue("issue1")

    def test_empty_issue_id_raises(self, monkeypatch):
        monkeypatch.setenv("LINEAR_API_KEY", "lin_test_key")
        with pytest.raises(ValueError, match="issue_id is required"):
            linear_get_issue("")

    def test_credentials_on_tool_def(self):
        assert linear_get_issue._tool_def.credentials == ["LINEAR_API_KEY"]

    def test_tool_def_name(self):
        assert linear_get_issue._tool_def.name == "linear_get_issue"


class TestLinearCreateIssue:
    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("LINEAR_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="LINEAR_API_KEY"):
            linear_create_issue("ENG", "Title")

    def test_empty_team_key_raises(self, monkeypatch):
        monkeypatch.setenv("LINEAR_API_KEY", "lin_test_key")
        with pytest.raises(ValueError, match="team_key is required"):
            linear_create_issue("", "Title")

    def test_empty_title_raises(self, monkeypatch):
        monkeypatch.setenv("LINEAR_API_KEY", "lin_test_key")
        with pytest.raises(ValueError, match="title is required"):
            linear_create_issue("ENG", "")

    def test_credentials_on_tool_def(self):
        assert linear_create_issue._tool_def.credentials == ["LINEAR_API_KEY"]

    def test_tool_def_name(self):
        assert linear_create_issue._tool_def.name == "linear_create_issue"


class TestLinearUpdateIssue:
    def test_empty_issue_id_raises(self, monkeypatch):
        monkeypatch.setenv("LINEAR_API_KEY", "lin_test_key")
        with pytest.raises(ValueError, match="issue_id is required"):
            linear_update_issue("")

    def test_credentials_on_tool_def(self):
        assert linear_update_issue._tool_def.credentials == ["LINEAR_API_KEY"]

    def test_tool_def_name(self):
        assert linear_update_issue._tool_def.name == "linear_update_issue"


class TestGetTools:
    def test_returns_all_tools(self):
        tools = get_tools()
        names = [t._tool_def.name for t in tools]
        assert "linear_list_issues" in names
        assert "linear_get_issue" in names
        assert "linear_create_issue" in names
        assert "linear_update_issue" in names
        assert len(tools) == 4
