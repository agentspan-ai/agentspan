"""Tests for gmail integration tools — real e2e, no mocks."""

from __future__ import annotations

import pytest

from autopilot.integrations.gmail.tools import (
    get_tools,
    gmail_list_messages,
    gmail_read_message,
    gmail_search,
    gmail_send_message,
)


class TestGmailListMessages:
    def test_missing_token_raises(self, monkeypatch):
        monkeypatch.delenv("GMAIL_ACCESS_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="GMAIL_ACCESS_TOKEN"):
            gmail_list_messages()

    def test_credentials_on_tool_def(self):
        assert gmail_list_messages._tool_def.credentials == ["GMAIL_ACCESS_TOKEN"]

    def test_tool_def_name(self):
        assert gmail_list_messages._tool_def.name == "gmail_list_messages"

    def test_tool_def_has_description(self):
        assert gmail_list_messages._tool_def.description
        assert len(gmail_list_messages._tool_def.description) > 10


class TestGmailReadMessage:
    def test_missing_token_raises(self, monkeypatch):
        monkeypatch.delenv("GMAIL_ACCESS_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="GMAIL_ACCESS_TOKEN"):
            gmail_read_message("msg1")

    def test_empty_message_id_raises(self, monkeypatch):
        monkeypatch.setenv("GMAIL_ACCESS_TOKEN", "test-token")
        with pytest.raises(ValueError, match="message_id is required"):
            gmail_read_message("")

    def test_credentials_on_tool_def(self):
        assert gmail_read_message._tool_def.credentials == ["GMAIL_ACCESS_TOKEN"]

    def test_tool_def_name(self):
        assert gmail_read_message._tool_def.name == "gmail_read_message"


class TestGmailSendMessage:
    def test_missing_token_raises(self, monkeypatch):
        monkeypatch.delenv("GMAIL_ACCESS_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="GMAIL_ACCESS_TOKEN"):
            gmail_send_message("to@test.com", "subject", "body")

    def test_empty_to_raises(self, monkeypatch):
        monkeypatch.setenv("GMAIL_ACCESS_TOKEN", "test-token")
        with pytest.raises(ValueError, match="to is required"):
            gmail_send_message("", "subject", "body")

    def test_empty_subject_raises(self, monkeypatch):
        monkeypatch.setenv("GMAIL_ACCESS_TOKEN", "test-token")
        with pytest.raises(ValueError, match="subject is required"):
            gmail_send_message("to@test.com", "", "body")

    def test_credentials_on_tool_def(self):
        assert gmail_send_message._tool_def.credentials == ["GMAIL_ACCESS_TOKEN"]

    def test_tool_def_name(self):
        assert gmail_send_message._tool_def.name == "gmail_send_message"


class TestGmailSearch:
    def test_empty_query_raises(self, monkeypatch):
        monkeypatch.setenv("GMAIL_ACCESS_TOKEN", "test-token")
        with pytest.raises(ValueError, match="query is required"):
            gmail_search("")

    def test_credentials_on_tool_def(self):
        assert gmail_search._tool_def.credentials == ["GMAIL_ACCESS_TOKEN"]

    def test_tool_def_name(self):
        assert gmail_search._tool_def.name == "gmail_search"


class TestGetTools:
    def test_returns_all_tools(self):
        tools = get_tools()
        names = [t._tool_def.name for t in tools]
        assert "gmail_list_messages" in names
        assert "gmail_read_message" in names
        assert "gmail_send_message" in names
        assert "gmail_search" in names
        assert len(tools) == 4
