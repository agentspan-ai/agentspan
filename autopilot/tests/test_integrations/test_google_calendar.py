"""Tests for Google Calendar integration tools."""

from __future__ import annotations

import pytest

from autopilot.integrations.google_calendar.tools import (
    gcal_create_event,
    gcal_list_events,
    gcal_search_events,
    get_tools,
)


class TestGCalCredentialValidation:
    """All Google Calendar tools require GOOGLE_CALENDAR_TOKEN and must raise when missing."""

    def test_list_events_requires_token(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_CALENDAR_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="GOOGLE_CALENDAR_TOKEN"):
            gcal_list_events()

    def test_create_event_requires_token(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_CALENDAR_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="GOOGLE_CALENDAR_TOKEN"):
            gcal_create_event("Meeting", "2025-01-15T09:00:00Z", "2025-01-15T10:00:00Z")

    def test_search_events_requires_token(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_CALENDAR_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="GOOGLE_CALENDAR_TOKEN"):
            gcal_search_events("standup")


class TestGCalToolDefs:
    """Verify tool_def metadata is correct."""

    def test_list_events_credentials(self):
        assert gcal_list_events._tool_def.credentials == ["GOOGLE_CALENDAR_TOKEN"]

    def test_create_event_credentials(self):
        assert gcal_create_event._tool_def.credentials == ["GOOGLE_CALENDAR_TOKEN"]

    def test_search_events_credentials(self):
        assert gcal_search_events._tool_def.credentials == ["GOOGLE_CALENDAR_TOKEN"]


class TestGetTools:
    def test_returns_all_tools(self):
        tools = get_tools()
        names = sorted(t._tool_def.name for t in tools)
        assert names == sorted([
            "gcal_list_events",
            "gcal_create_event",
            "gcal_search_events",
        ])

    def test_tool_count(self):
        assert len(get_tools()) == 3
