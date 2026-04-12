"""Tests for Slack integration tools."""

from __future__ import annotations

import pytest

from autopilot.integrations.slack.tools import (
    get_tools,
    slack_list_channels,
    slack_read_messages,
    slack_search_messages,
    slack_send_message,
)


class TestSlackCredentialValidation:
    """All Slack tools require SLACK_BOT_TOKEN and must raise when missing."""

    def test_send_message_requires_token(self, monkeypatch):
        monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="SLACK_BOT_TOKEN"):
            slack_send_message("#general", "hello")

    def test_list_channels_requires_token(self, monkeypatch):
        monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="SLACK_BOT_TOKEN"):
            slack_list_channels()

    def test_read_messages_requires_token(self, monkeypatch):
        monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="SLACK_BOT_TOKEN"):
            slack_read_messages("C01234", 10)

    def test_search_messages_requires_token(self, monkeypatch):
        monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="SLACK_BOT_TOKEN"):
            slack_search_messages("test query")


class TestSlackToolDefs:
    """Verify tool_def metadata is correct."""

    def test_send_message_credentials(self):
        assert slack_send_message._tool_def.credentials == ["SLACK_BOT_TOKEN"]

    def test_list_channels_credentials(self):
        assert slack_list_channels._tool_def.credentials == ["SLACK_BOT_TOKEN"]

    def test_read_messages_credentials(self):
        assert slack_read_messages._tool_def.credentials == ["SLACK_BOT_TOKEN"]

    def test_search_messages_credentials(self):
        assert slack_search_messages._tool_def.credentials == ["SLACK_BOT_TOKEN"]


class TestGetTools:
    def test_returns_all_tools(self):
        tools = get_tools()
        names = sorted(t._tool_def.name for t in tools)
        assert names == sorted([
            "slack_send_message",
            "slack_list_channels",
            "slack_read_messages",
            "slack_search_messages",
        ])

    def test_tool_count(self):
        assert len(get_tools()) == 4
