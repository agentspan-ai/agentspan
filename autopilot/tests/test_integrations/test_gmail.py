"""Tests for gmail integration tools."""

from __future__ import annotations

from unittest.mock import MagicMock

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

    def test_successful_list(self, monkeypatch):
        monkeypatch.setenv("GMAIL_ACCESS_TOKEN", "test-token")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "messages": [
                {"id": "msg1", "threadId": "t1"},
                {"id": "msg2", "threadId": "t2"},
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        monkeypatch.setattr(
            "autopilot.integrations.gmail.tools.httpx.get",
            lambda *a, **kw: mock_resp,
        )

        results = gmail_list_messages(query="from:alice")
        assert len(results) == 2
        assert results[0]["id"] == "msg1"

    def test_max_results_clamped(self, monkeypatch):
        monkeypatch.setenv("GMAIL_ACCESS_TOKEN", "test-token")

        captured = {}

        def mock_get(*args, **kwargs):
            captured.update(kwargs.get("params", {}))
            resp = MagicMock()
            resp.json.return_value = {"messages": []}
            resp.raise_for_status = MagicMock()
            return resp

        monkeypatch.setattr("autopilot.integrations.gmail.tools.httpx.get", mock_get)

        gmail_list_messages(max_results=200)
        assert captured["maxResults"] == 100

    def test_credentials_on_tool_def(self):
        assert gmail_list_messages._tool_def.credentials == ["GMAIL_ACCESS_TOKEN"]


class TestGmailReadMessage:
    def test_missing_token_raises(self, monkeypatch):
        monkeypatch.delenv("GMAIL_ACCESS_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="GMAIL_ACCESS_TOKEN"):
            gmail_read_message("msg1")

    def test_empty_message_id_raises(self, monkeypatch):
        monkeypatch.setenv("GMAIL_ACCESS_TOKEN", "test-token")
        with pytest.raises(ValueError, match="message_id is required"):
            gmail_read_message("")

    def test_successful_read(self, monkeypatch):
        monkeypatch.setenv("GMAIL_ACCESS_TOKEN", "test-token")

        import base64

        body_data = base64.urlsafe_b64encode(b"Hello world").decode()

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "id": "msg1",
            "snippet": "Hello...",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "From", "value": "alice@test.com"},
                    {"name": "To", "value": "bob@test.com"},
                ],
                "body": {"data": body_data},
            },
        }
        mock_resp.raise_for_status = MagicMock()

        monkeypatch.setattr(
            "autopilot.integrations.gmail.tools.httpx.get",
            lambda *a, **kw: mock_resp,
        )

        result = gmail_read_message("msg1")
        assert result["id"] == "msg1"
        assert result["subject"] == "Test Subject"
        assert result["body"] == "Hello world"

    def test_credentials_on_tool_def(self):
        assert gmail_read_message._tool_def.credentials == ["GMAIL_ACCESS_TOKEN"]


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

    def test_successful_send(self, monkeypatch):
        monkeypatch.setenv("GMAIL_ACCESS_TOKEN", "test-token")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "sent1", "threadId": "t1"}
        mock_resp.raise_for_status = MagicMock()

        monkeypatch.setattr(
            "autopilot.integrations.gmail.tools.httpx.post",
            lambda *a, **kw: mock_resp,
        )

        result = gmail_send_message("bob@test.com", "Hi", "Hello Bob")
        assert result["id"] == "sent1"

    def test_credentials_on_tool_def(self):
        assert gmail_send_message._tool_def.credentials == ["GMAIL_ACCESS_TOKEN"]


class TestGmailSearch:
    def test_empty_query_raises(self, monkeypatch):
        monkeypatch.setenv("GMAIL_ACCESS_TOKEN", "test-token")
        with pytest.raises(ValueError, match="query is required"):
            gmail_search("")

    def test_credentials_on_tool_def(self):
        assert gmail_search._tool_def.credentials == ["GMAIL_ACCESS_TOKEN"]


class TestGetTools:
    def test_returns_all_tools(self):
        tools = get_tools()
        names = [t._tool_def.name for t in tools]
        assert "gmail_list_messages" in names
        assert "gmail_read_message" in names
        assert "gmail_send_message" in names
        assert "gmail_search" in names
        assert len(tools) == 4
