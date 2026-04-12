"""Tests for outlook integration tools — real e2e, no mocks."""

from __future__ import annotations

import pytest

from autopilot.integrations.outlook.tools import (
    get_tools,
    outlook_list_messages,
    outlook_read_message,
    outlook_search,
    outlook_send_message,
)


class TestOutlookListMessages:
    def test_missing_token_raises(self, monkeypatch):
        monkeypatch.delenv("OUTLOOK_ACCESS_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="OUTLOOK_ACCESS_TOKEN"):
            outlook_list_messages()

    def test_credentials_on_tool_def(self):
        assert outlook_list_messages._tool_def.credentials == ["OUTLOOK_ACCESS_TOKEN"]

    def test_tool_def_name(self):
        assert outlook_list_messages._tool_def.name == "outlook_list_messages"

    def test_tool_def_has_description(self):
        assert outlook_list_messages._tool_def.description
        assert len(outlook_list_messages._tool_def.description) > 10


class TestOutlookReadMessage:
    def test_missing_token_raises(self, monkeypatch):
        monkeypatch.delenv("OUTLOOK_ACCESS_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="OUTLOOK_ACCESS_TOKEN"):
            outlook_read_message("m1")

    def test_empty_message_id_raises(self, monkeypatch):
        monkeypatch.setenv("OUTLOOK_ACCESS_TOKEN", "test-token")
        with pytest.raises(ValueError, match="message_id is required"):
            outlook_read_message("")

    def test_credentials_on_tool_def(self):
        assert outlook_read_message._tool_def.credentials == ["OUTLOOK_ACCESS_TOKEN"]

    def test_tool_def_name(self):
        assert outlook_read_message._tool_def.name == "outlook_read_message"


class TestOutlookSendMessage:
    def test_missing_token_raises(self, monkeypatch):
        monkeypatch.delenv("OUTLOOK_ACCESS_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="OUTLOOK_ACCESS_TOKEN"):
            outlook_send_message("to@test.com", "sub", "body")

    def test_empty_to_raises(self, monkeypatch):
        monkeypatch.setenv("OUTLOOK_ACCESS_TOKEN", "test-token")
        with pytest.raises(ValueError, match="to is required"):
            outlook_send_message("", "sub", "body")

    def test_empty_subject_raises(self, monkeypatch):
        monkeypatch.setenv("OUTLOOK_ACCESS_TOKEN", "test-token")
        with pytest.raises(ValueError, match="subject is required"):
            outlook_send_message("to@test.com", "", "body")

    def test_credentials_on_tool_def(self):
        assert outlook_send_message._tool_def.credentials == ["OUTLOOK_ACCESS_TOKEN"]

    def test_tool_def_name(self):
        assert outlook_send_message._tool_def.name == "outlook_send_message"


class TestOutlookSearch:
    def test_empty_query_raises(self, monkeypatch):
        monkeypatch.setenv("OUTLOOK_ACCESS_TOKEN", "test-token")
        with pytest.raises(ValueError, match="query is required"):
            outlook_search("")

    def test_credentials_on_tool_def(self):
        assert outlook_search._tool_def.credentials == ["OUTLOOK_ACCESS_TOKEN"]

    def test_tool_def_name(self):
        assert outlook_search._tool_def.name == "outlook_search"


class TestGetTools:
    def test_returns_all_tools(self):
        tools = get_tools()
        names = [t._tool_def.name for t in tools]
        assert "outlook_list_messages" in names
        assert "outlook_read_message" in names
        assert "outlook_send_message" in names
        assert "outlook_search" in names
        assert len(tools) == 4
