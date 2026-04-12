"""Tests for outlook integration tools."""

from __future__ import annotations

from unittest.mock import MagicMock

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

    def test_successful_list(self, monkeypatch):
        monkeypatch.setenv("OUTLOOK_ACCESS_TOKEN", "test-token")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "value": [
                {"id": "m1", "subject": "Hello", "bodyPreview": "Hi there"},
                {"id": "m2", "subject": "Meeting", "bodyPreview": "Tomorrow"},
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        monkeypatch.setattr(
            "autopilot.integrations.outlook.tools.httpx.get",
            lambda *a, **kw: mock_resp,
        )

        results = outlook_list_messages()
        assert len(results) == 2
        assert results[0]["id"] == "m1"

    def test_top_clamped(self, monkeypatch):
        monkeypatch.setenv("OUTLOOK_ACCESS_TOKEN", "test-token")

        captured = {}

        def mock_get(*args, **kwargs):
            captured.update(kwargs.get("params", {}))
            resp = MagicMock()
            resp.json.return_value = {"value": []}
            resp.raise_for_status = MagicMock()
            return resp

        monkeypatch.setattr("autopilot.integrations.outlook.tools.httpx.get", mock_get)

        outlook_list_messages(top=200)
        assert captured["$top"] == 100

    def test_credentials_on_tool_def(self):
        assert outlook_list_messages._tool_def.credentials == ["OUTLOOK_ACCESS_TOKEN"]


class TestOutlookReadMessage:
    def test_missing_token_raises(self, monkeypatch):
        monkeypatch.delenv("OUTLOOK_ACCESS_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="OUTLOOK_ACCESS_TOKEN"):
            outlook_read_message("m1")

    def test_empty_message_id_raises(self, monkeypatch):
        monkeypatch.setenv("OUTLOOK_ACCESS_TOKEN", "test-token")
        with pytest.raises(ValueError, match="message_id is required"):
            outlook_read_message("")

    def test_successful_read(self, monkeypatch):
        monkeypatch.setenv("OUTLOOK_ACCESS_TOKEN", "test-token")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "id": "m1",
            "subject": "Test",
            "body": {"content": "Hello"},
        }
        mock_resp.raise_for_status = MagicMock()

        monkeypatch.setattr(
            "autopilot.integrations.outlook.tools.httpx.get",
            lambda *a, **kw: mock_resp,
        )

        result = outlook_read_message("m1")
        assert result["id"] == "m1"
        assert result["subject"] == "Test"

    def test_credentials_on_tool_def(self):
        assert outlook_read_message._tool_def.credentials == ["OUTLOOK_ACCESS_TOKEN"]


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

    def test_successful_send(self, monkeypatch):
        monkeypatch.setenv("OUTLOOK_ACCESS_TOKEN", "test-token")

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        monkeypatch.setattr(
            "autopilot.integrations.outlook.tools.httpx.post",
            lambda *a, **kw: mock_resp,
        )

        result = outlook_send_message("bob@test.com", "Hi", "Hello")
        assert "bob@test.com" in result

    def test_credentials_on_tool_def(self):
        assert outlook_send_message._tool_def.credentials == ["OUTLOOK_ACCESS_TOKEN"]


class TestOutlookSearch:
    def test_empty_query_raises(self, monkeypatch):
        monkeypatch.setenv("OUTLOOK_ACCESS_TOKEN", "test-token")
        with pytest.raises(ValueError, match="query is required"):
            outlook_search("")

    def test_credentials_on_tool_def(self):
        assert outlook_search._tool_def.credentials == ["OUTLOOK_ACCESS_TOKEN"]


class TestGetTools:
    def test_returns_all_tools(self):
        tools = get_tools()
        names = [t._tool_def.name for t in tools]
        assert "outlook_list_messages" in names
        assert "outlook_read_message" in names
        assert "outlook_send_message" in names
        assert "outlook_search" in names
        assert len(tools) == 4
