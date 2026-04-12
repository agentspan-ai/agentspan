"""Tests for whatsapp integration tools."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from autopilot.integrations.whatsapp.tools import (
    get_tools,
    whatsapp_send_message,
    whatsapp_send_template,
)


def _set_wa_creds(monkeypatch):
    monkeypatch.setenv("WHATSAPP_TOKEN", "wa-token-123")
    monkeypatch.setenv("WHATSAPP_PHONE_ID", "123456")


class TestWhatsappSendMessage:
    def test_missing_creds_raises(self, monkeypatch):
        monkeypatch.delenv("WHATSAPP_TOKEN", raising=False)
        monkeypatch.delenv("WHATSAPP_PHONE_ID", raising=False)
        with pytest.raises(RuntimeError, match="WHATSAPP_TOKEN"):
            whatsapp_send_message("+1234567890", "hello")

    def test_missing_phone_id_raises(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_TOKEN", "wa-token-123")
        monkeypatch.delenv("WHATSAPP_PHONE_ID", raising=False)
        with pytest.raises(RuntimeError, match="WHATSAPP_PHONE_ID"):
            whatsapp_send_message("+1234567890", "hello")

    def test_empty_to_raises(self, monkeypatch):
        _set_wa_creds(monkeypatch)
        with pytest.raises(ValueError, match="to is required"):
            whatsapp_send_message("", "hello")

    def test_empty_text_raises(self, monkeypatch):
        _set_wa_creds(monkeypatch)
        with pytest.raises(ValueError, match="text is required"):
            whatsapp_send_message("+1234567890", "")

    def test_successful_send(self, monkeypatch):
        _set_wa_creds(monkeypatch)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "messages": [{"id": "wamid.123"}]
        }
        mock_resp.raise_for_status = MagicMock()

        monkeypatch.setattr(
            "autopilot.integrations.whatsapp.tools.httpx.post",
            lambda *a, **kw: mock_resp,
        )

        result = whatsapp_send_message("+1234567890", "Hello!")
        assert "messages" in result
        assert result["messages"][0]["id"] == "wamid.123"

    def test_credentials_on_tool_def(self):
        assert whatsapp_send_message._tool_def.credentials == [
            "WHATSAPP_TOKEN",
            "WHATSAPP_PHONE_ID",
        ]


class TestWhatsappSendTemplate:
    def test_missing_creds_raises(self, monkeypatch):
        monkeypatch.delenv("WHATSAPP_TOKEN", raising=False)
        monkeypatch.delenv("WHATSAPP_PHONE_ID", raising=False)
        with pytest.raises(RuntimeError, match="WHATSAPP_TOKEN"):
            whatsapp_send_template("+1234567890", "hello_world")

    def test_empty_to_raises(self, monkeypatch):
        _set_wa_creds(monkeypatch)
        with pytest.raises(ValueError, match="to is required"):
            whatsapp_send_template("", "hello_world")

    def test_empty_template_name_raises(self, monkeypatch):
        _set_wa_creds(monkeypatch)
        with pytest.raises(ValueError, match="template_name is required"):
            whatsapp_send_template("+1234567890", "")

    def test_successful_template_send(self, monkeypatch):
        _set_wa_creds(monkeypatch)

        captured_payload = {}

        def mock_post(*args, **kwargs):
            captured_payload.update(kwargs.get("json", {}))
            resp = MagicMock()
            resp.json.return_value = {"messages": [{"id": "wamid.456"}]}
            resp.raise_for_status = MagicMock()
            return resp

        monkeypatch.setattr("autopilot.integrations.whatsapp.tools.httpx.post", mock_post)

        result = whatsapp_send_template("+1234567890", "hello_world", ["param1"])
        assert result["messages"][0]["id"] == "wamid.456"
        assert captured_payload["type"] == "template"
        assert captured_payload["template"]["name"] == "hello_world"
        assert len(captured_payload["template"]["components"][0]["parameters"]) == 1

    def test_credentials_on_tool_def(self):
        assert whatsapp_send_template._tool_def.credentials == [
            "WHATSAPP_TOKEN",
            "WHATSAPP_PHONE_ID",
        ]


class TestGetTools:
    def test_returns_all_tools(self):
        tools = get_tools()
        names = [t._tool_def.name for t in tools]
        assert "whatsapp_send_message" in names
        assert "whatsapp_send_template" in names
        assert len(tools) == 2
