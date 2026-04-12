"""Tests for imessage integration tools."""

from __future__ import annotations

from unittest.mock import MagicMock

import platform

import pytest

from autopilot.integrations.imessage.tools import get_tools, imessage_send


class TestImessageSend:
    def test_non_macos_raises(self, monkeypatch):
        monkeypatch.setattr(
            "autopilot.integrations.imessage.tools.platform.system",
            lambda: "Linux",
        )
        with pytest.raises(RuntimeError, match="only available on macOS"):
            imessage_send("+1234567890", "hello")

    def test_non_macos_windows_raises(self, monkeypatch):
        monkeypatch.setattr(
            "autopilot.integrations.imessage.tools.platform.system",
            lambda: "Windows",
        )
        with pytest.raises(RuntimeError, match="only available on macOS"):
            imessage_send("+1234567890", "hello")

    def test_empty_to_raises(self, monkeypatch):
        monkeypatch.setattr(
            "autopilot.integrations.imessage.tools.platform.system",
            lambda: "Darwin",
        )
        with pytest.raises(ValueError, match="to is required"):
            imessage_send("", "hello")

    def test_empty_text_raises(self, monkeypatch):
        monkeypatch.setattr(
            "autopilot.integrations.imessage.tools.platform.system",
            lambda: "Darwin",
        )
        with pytest.raises(ValueError, match="text is required"):
            imessage_send("+1234567890", "")

    def test_successful_send_on_macos(self, monkeypatch):
        monkeypatch.setattr(
            "autopilot.integrations.imessage.tools.platform.system",
            lambda: "Darwin",
        )

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        monkeypatch.setattr(
            "autopilot.integrations.imessage.tools.subprocess.run",
            lambda *a, **kw: mock_result,
        )

        result = imessage_send("+1234567890", "Hello!")
        assert "+1234567890" in result

    def test_osascript_failure_raises(self, monkeypatch):
        monkeypatch.setattr(
            "autopilot.integrations.imessage.tools.platform.system",
            lambda: "Darwin",
        )

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Messages got an error: can't get participant"

        monkeypatch.setattr(
            "autopilot.integrations.imessage.tools.subprocess.run",
            lambda *a, **kw: mock_result,
        )

        with pytest.raises(RuntimeError, match="osascript failed"):
            imessage_send("+1234567890", "Hello!")

    def test_no_credentials_on_tool_def(self):
        """iMessage uses no credentials (local osascript only)."""
        creds = getattr(imessage_send._tool_def, "credentials", None)
        assert creds is None or creds == []


class TestGetTools:
    def test_returns_all_tools(self):
        tools = get_tools()
        names = [t._tool_def.name for t in tools]
        assert "imessage_send" in names
        assert len(tools) == 1
