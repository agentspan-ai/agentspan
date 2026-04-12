"""Tests for jira integration tools — real e2e, no mocks."""

from __future__ import annotations

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

    def test_credentials_on_tool_def(self):
        assert jira_search._tool_def.credentials == ["JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"]

    def test_tool_def_name(self):
        assert jira_search._tool_def.name == "jira_search"

    def test_tool_def_has_description(self):
        assert jira_search._tool_def.description
        assert len(jira_search._tool_def.description) > 10


class TestJiraGetIssue:
    def test_empty_issue_key_raises(self, monkeypatch):
        _set_jira_creds(monkeypatch)
        with pytest.raises(ValueError, match="issue_key is required"):
            jira_get_issue("")

    def test_credentials_on_tool_def(self):
        assert jira_get_issue._tool_def.credentials == ["JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"]

    def test_tool_def_name(self):
        assert jira_get_issue._tool_def.name == "jira_get_issue"


class TestJiraCreateIssue:
    def test_empty_project_key_raises(self, monkeypatch):
        _set_jira_creds(monkeypatch)
        with pytest.raises(ValueError, match="project_key is required"):
            jira_create_issue("", "summary")

    def test_empty_summary_raises(self, monkeypatch):
        _set_jira_creds(monkeypatch)
        with pytest.raises(ValueError, match="summary is required"):
            jira_create_issue("ENG", "")

    def test_credentials_on_tool_def(self):
        assert jira_create_issue._tool_def.credentials == ["JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"]

    def test_tool_def_name(self):
        assert jira_create_issue._tool_def.name == "jira_create_issue"


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

    def test_tool_def_name(self):
        assert jira_update_issue._tool_def.name == "jira_update_issue"


class TestJiraAddComment:
    def test_empty_issue_key_raises(self, monkeypatch):
        _set_jira_creds(monkeypatch)
        with pytest.raises(ValueError, match="issue_key is required"):
            jira_add_comment("", "comment")

    def test_empty_body_raises(self, monkeypatch):
        _set_jira_creds(monkeypatch)
        with pytest.raises(ValueError, match="body is required"):
            jira_add_comment("ENG-1", "")

    def test_credentials_on_tool_def(self):
        assert jira_add_comment._tool_def.credentials == ["JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"]

    def test_tool_def_name(self):
        assert jira_add_comment._tool_def.name == "jira_add_comment"


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
