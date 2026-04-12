"""Tests for jira integration tools."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from autopilot.integrations.jira.tools import (
    get_tools,
    jira_add_comment,
    jira_create_issue,
    jira_get_issue,
    jira_search,
    jira_update_issue,
)


def _set_jira_creds(monkeypatch):
    monkeypatch.setenv("JIRA_URL", "https://test.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "user@test.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "jira-token-123")


class TestJiraSearch:
    def test_missing_url_raises(self, monkeypatch):
        monkeypatch.delenv("JIRA_URL", raising=False)
        monkeypatch.delenv("JIRA_EMAIL", raising=False)
        monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="JIRA_URL"):
            jira_search("project = ENG")

    def test_missing_partial_creds_raises(self, monkeypatch):
        monkeypatch.setenv("JIRA_URL", "https://test.atlassian.net")
        monkeypatch.delenv("JIRA_EMAIL", raising=False)
        monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="JIRA_EMAIL"):
            jira_search("project = ENG")

    def test_empty_jql_raises(self, monkeypatch):
        _set_jira_creds(monkeypatch)
        with pytest.raises(ValueError, match="jql is required"):
            jira_search("")

    def test_successful_search(self, monkeypatch):
        _set_jira_creds(monkeypatch)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "issues": [
                {
                    "key": "ENG-1",
                    "fields": {
                        "summary": "Fix login",
                        "status": {"name": "Open"},
                        "assignee": {"displayName": "Bob"},
                        "priority": {"name": "High"},
                    },
                }
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        monkeypatch.setattr(
            "autopilot.integrations.jira.tools.httpx.get",
            lambda *a, **kw: mock_resp,
        )

        results = jira_search("project = ENG")
        assert len(results) == 1
        assert results[0]["key"] == "ENG-1"
        assert results[0]["summary"] == "Fix login"

    def test_max_results_clamped(self, monkeypatch):
        _set_jira_creds(monkeypatch)

        captured = {}

        def mock_get(*args, **kwargs):
            captured.update(kwargs.get("params", {}))
            resp = MagicMock()
            resp.json.return_value = {"issues": []}
            resp.raise_for_status = MagicMock()
            return resp

        monkeypatch.setattr("autopilot.integrations.jira.tools.httpx.get", mock_get)

        jira_search("project = ENG", max_results=200)
        assert captured["maxResults"] == 100

    def test_credentials_on_tool_def(self):
        assert jira_search._tool_def.credentials == ["JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"]


class TestJiraGetIssue:
    def test_empty_issue_key_raises(self, monkeypatch):
        _set_jira_creds(monkeypatch)
        with pytest.raises(ValueError, match="issue_key is required"):
            jira_get_issue("")

    def test_successful_get(self, monkeypatch):
        _set_jira_creds(monkeypatch)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "key": "ENG-1",
            "fields": {
                "summary": "Fix login",
                "description": "Login is broken",
                "status": {"name": "Open"},
                "assignee": {"displayName": "Bob"},
                "priority": {"name": "High"},
                "created": "2024-01-01",
                "updated": "2024-01-02",
            },
        }
        mock_resp.raise_for_status = MagicMock()

        monkeypatch.setattr(
            "autopilot.integrations.jira.tools.httpx.get",
            lambda *a, **kw: mock_resp,
        )

        result = jira_get_issue("ENG-1")
        assert result["key"] == "ENG-1"
        assert result["summary"] == "Fix login"

    def test_credentials_on_tool_def(self):
        assert jira_get_issue._tool_def.credentials == ["JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"]


class TestJiraCreateIssue:
    def test_empty_project_key_raises(self, monkeypatch):
        _set_jira_creds(monkeypatch)
        with pytest.raises(ValueError, match="project_key is required"):
            jira_create_issue("", "summary")

    def test_empty_summary_raises(self, monkeypatch):
        _set_jira_creds(monkeypatch)
        with pytest.raises(ValueError, match="summary is required"):
            jira_create_issue("ENG", "")

    def test_successful_create(self, monkeypatch):
        _set_jira_creds(monkeypatch)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"key": "ENG-2", "id": "10001"}
        mock_resp.raise_for_status = MagicMock()

        monkeypatch.setattr(
            "autopilot.integrations.jira.tools.httpx.post",
            lambda *a, **kw: mock_resp,
        )

        result = jira_create_issue("ENG", "New feature")
        assert result["key"] == "ENG-2"

    def test_credentials_on_tool_def(self):
        assert jira_create_issue._tool_def.credentials == ["JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"]


class TestJiraUpdateIssue:
    def test_empty_issue_key_raises(self, monkeypatch):
        _set_jira_creds(monkeypatch)
        with pytest.raises(ValueError, match="issue_key is required"):
            jira_update_issue("", {"summary": "new"})

    def test_empty_fields_raises(self, monkeypatch):
        _set_jira_creds(monkeypatch)
        with pytest.raises(ValueError, match="fields is required"):
            jira_update_issue("ENG-1", {})

    def test_credentials_on_tool_def(self):
        assert jira_update_issue._tool_def.credentials == ["JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"]


class TestJiraAddComment:
    def test_empty_issue_key_raises(self, monkeypatch):
        _set_jira_creds(monkeypatch)
        with pytest.raises(ValueError, match="issue_key is required"):
            jira_add_comment("", "comment")

    def test_empty_body_raises(self, monkeypatch):
        _set_jira_creds(monkeypatch)
        with pytest.raises(ValueError, match="body is required"):
            jira_add_comment("ENG-1", "")

    def test_successful_comment(self, monkeypatch):
        _set_jira_creds(monkeypatch)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "comment1"}
        mock_resp.raise_for_status = MagicMock()

        monkeypatch.setattr(
            "autopilot.integrations.jira.tools.httpx.post",
            lambda *a, **kw: mock_resp,
        )

        result = jira_add_comment("ENG-1", "This is a comment")
        assert result["id"] == "comment1"

    def test_credentials_on_tool_def(self):
        assert jira_add_comment._tool_def.credentials == ["JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"]


class TestGetTools:
    def test_returns_all_tools(self):
        tools = get_tools()
        names = [t._tool_def.name for t in tools]
        assert "jira_search" in names
        assert "jira_get_issue" in names
        assert "jira_create_issue" in names
        assert "jira_update_issue" in names
        assert "jira_add_comment" in names
        assert len(tools) == 5
