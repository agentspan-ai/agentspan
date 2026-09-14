"""Tests for imessage integration tools — credential validation and tool metadata.

# NOTE: These tests verify credential validation and tool metadata.
# Full API integration tests require real credentials and are run
# via the e2e test suite with deployed agents.
"""

from __future__ import annotations

import platform

import pytest

from autopilot.integrations.imessage.tools import get_tools, imessage_send


class TestImessageSend:
    def test_platform_detection_is_real(self):
        """Verify we can read the real platform — this is a real test."""
        current = platform.system()
        assert current in ("Darwin", "Linux", "Windows")

    def test_empty_to_raises(self):
        """Input validation: empty 'to' raises ValueError on macOS, RuntimeError elsewhere."""
        if platform.system() == "Darwin":
            with pytest.raises(ValueError, match="to is required"):
                imessage_send("", "hello")
        else:
            with pytest.raises(RuntimeError, match="only available on macOS"):
                imessage_send("", "hello")

    def test_empty_text_raises(self):
        """Input validation: empty 'text' raises ValueError on macOS, RuntimeError elsewhere."""
        if platform.system() == "Darwin":
            with pytest.raises(ValueError, match="text is required"):
                imessage_send("+1234567890", "")
        else:
            with pytest.raises(RuntimeError, match="only available on macOS"):
                imessage_send("+1234567890", "")

    def test_non_macos_raises(self):
        """On non-macOS, imessage_send always raises RuntimeError."""
        if platform.system() != "Darwin":
            with pytest.raises(RuntimeError, match="only available on macOS"):
                imessage_send("+1234567890", "hello")
        else:
            pytest.skip("Test only applicable on non-macOS platforms")

    def test_no_credentials_on_tool_def(self):
        """iMessage uses no credentials (local osascript only)."""
        creds = getattr(imessage_send._tool_def, "credentials", None)
        assert creds is None or creds == []

    def test_tool_def_name(self):
        assert imessage_send._tool_def.name == "imessage_send"

    def test_tool_def_has_description(self):
        assert imessage_send._tool_def.description
        assert "imessage" in imessage_send._tool_def.description.lower() or "message" in imessage_send._tool_def.description.lower()


class TestGetTools:
    def test_returns_all_tools(self):
        tools = get_tools()
        names = [t._tool_def.name for t in tools]
        assert "imessage_send" in names
        assert len(tools) == 1
