"""Tests for whatsapp integration tools — credential validation and tool metadata.

# NOTE: These tests verify credential validation and tool metadata.
# Full API integration tests require real credentials and are run
# via the e2e test suite with deployed agents.
"""

from __future__ import annotations

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

    def test_credentials_on_tool_def(self):
        assert whatsapp_send_message._tool_def.credentials == [
            "WHATSAPP_TOKEN",
            "WHATSAPP_PHONE_ID",
        ]

    def test_tool_def_name(self):
        assert whatsapp_send_message._tool_def.name == "whatsapp_send_message"

    def test_tool_def_has_description(self):
        assert whatsapp_send_message._tool_def.description
        assert len(whatsapp_send_message._tool_def.description) > 10


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

    def test_credentials_on_tool_def(self):
        assert whatsapp_send_template._tool_def.credentials == [
            "WHATSAPP_TOKEN",
            "WHATSAPP_PHONE_ID",
        ]

    def test_tool_def_name(self):
        assert whatsapp_send_template._tool_def.name == "whatsapp_send_template"


class TestGetTools:
    def test_returns_all_tools(self):
        tools = get_tools()
        names = [t._tool_def.name for t in tools]
        assert "whatsapp_send_message" in names
        assert "whatsapp_send_template" in names
        assert len(tools) == 2
