"""Tests for linear integration tools."""

from __future__ import annotations

from unittest.mock import MagicMock

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

    def test_successful_list(self, monkeypatch):
        monkeypatch.setenv("LINEAR_API_KEY", "lin_test_key")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {
                "issues": {
                    "nodes": [
                        {
                            "id": "issue1",
                            "title": "Fix bug",
                            "identifier": "ENG-1",
                            "priority": 2,
                            "state": {"name": "In Progress"},
                            "assignee": {"name": "Alice"},
                        }
                    ]
                }
            }
        }
        mock_resp.raise_for_status = MagicMock()

        monkeypatch.setattr(
            "autopilot.integrations.linear.tools.httpx.post",
            lambda *a, **kw: mock_resp,
        )

        results = linear_list_issues(team_key="ENG")
        assert len(results) == 1
        assert results[0]["title"] == "Fix bug"
        assert results[0]["state"] == "In Progress"

    def test_credentials_on_tool_def(self):
        assert linear_list_issues._tool_def.credentials == ["LINEAR_API_KEY"]


class TestLinearGetIssue:
    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("LINEAR_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="LINEAR_API_KEY"):
            linear_get_issue("issue1")

    def test_empty_issue_id_raises(self, monkeypatch):
        monkeypatch.setenv("LINEAR_API_KEY", "lin_test_key")
        with pytest.raises(ValueError, match="issue_id is required"):
            linear_get_issue("")

    def test_successful_get(self, monkeypatch):
        monkeypatch.setenv("LINEAR_API_KEY", "lin_test_key")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {
                "issue": {
                    "id": "issue1",
                    "title": "Fix bug",
                    "identifier": "ENG-1",
                    "description": "It's broken",
                    "priority": 2,
                    "state": {"name": "Todo"},
                    "assignee": None,
                    "labels": {"nodes": []},
                    "createdAt": "2024-01-01",
                    "updatedAt": "2024-01-02",
                }
            }
        }
        mock_resp.raise_for_status = MagicMock()

        monkeypatch.setattr(
            "autopilot.integrations.linear.tools.httpx.post",
            lambda *a, **kw: mock_resp,
        )

        result = linear_get_issue("issue1")
        assert result["title"] == "Fix bug"

    def test_credentials_on_tool_def(self):
        assert linear_get_issue._tool_def.credentials == ["LINEAR_API_KEY"]


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


class TestLinearUpdateIssue:
    def test_empty_issue_id_raises(self, monkeypatch):
        monkeypatch.setenv("LINEAR_API_KEY", "lin_test_key")
        with pytest.raises(ValueError, match="issue_id is required"):
            linear_update_issue("")

    def test_credentials_on_tool_def(self):
        assert linear_update_issue._tool_def.credentials == ["LINEAR_API_KEY"]


class TestGetTools:
    def test_returns_all_tools(self):
        tools = get_tools()
        names = [t._tool_def.name for t in tools]
        assert "linear_list_issues" in names
        assert "linear_get_issue" in names
        assert "linear_create_issue" in names
        assert "linear_update_issue" in names
        assert len(tools) == 4
