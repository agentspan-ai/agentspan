"""Tests for google_analytics integration tools — credential validation and tool metadata.

# NOTE: These tests verify credential validation and tool metadata.
# Full API integration tests require real credentials and are run
# via the e2e test suite with deployed agents.
"""

from __future__ import annotations

import pytest

from autopilot.integrations.google_analytics.tools import (
    ga_get_realtime,
    ga_run_report,
    get_tools,
)


def _set_ga_creds(monkeypatch):
    monkeypatch.setenv("GA_ACCESS_TOKEN", "ga-token-123")
    monkeypatch.setenv("GA_PROPERTY_ID", "123456789")


class TestGaRunReport:
    def test_missing_creds_raises(self, monkeypatch):
        monkeypatch.delenv("GA_ACCESS_TOKEN", raising=False)
        monkeypatch.delenv("GA_PROPERTY_ID", raising=False)
        with pytest.raises(RuntimeError, match="GA_ACCESS_TOKEN"):
            ga_run_report(["activeUsers"])

    def test_missing_property_id_raises(self, monkeypatch):
        monkeypatch.setenv("GA_ACCESS_TOKEN", "ga-token-123")
        monkeypatch.delenv("GA_PROPERTY_ID", raising=False)
        with pytest.raises(RuntimeError, match="GA_PROPERTY_ID"):
            ga_run_report(["activeUsers"])

    def test_empty_metrics_raises(self, monkeypatch):
        _set_ga_creds(monkeypatch)
        with pytest.raises(ValueError, match="metrics is required"):
            ga_run_report([])

    def test_credentials_on_tool_def(self):
        assert ga_run_report._tool_def.credentials == ["GA_ACCESS_TOKEN", "GA_PROPERTY_ID"]

    def test_tool_def_name(self):
        assert ga_run_report._tool_def.name == "ga_run_report"

    def test_tool_def_has_description(self):
        assert ga_run_report._tool_def.description
        assert len(ga_run_report._tool_def.description) > 10


class TestGaGetRealtime:
    def test_missing_creds_raises(self, monkeypatch):
        monkeypatch.delenv("GA_ACCESS_TOKEN", raising=False)
        monkeypatch.delenv("GA_PROPERTY_ID", raising=False)
        with pytest.raises(RuntimeError, match="GA_ACCESS_TOKEN"):
            ga_get_realtime()

    def test_credentials_on_tool_def(self):
        assert ga_get_realtime._tool_def.credentials == ["GA_ACCESS_TOKEN", "GA_PROPERTY_ID"]

    def test_tool_def_name(self):
        assert ga_get_realtime._tool_def.name == "ga_get_realtime"


class TestGetTools:
    def test_returns_all_tools(self):
        tools = get_tools()
        names = [t._tool_def.name for t in tools]
        assert "ga_run_report" in names
        assert "ga_get_realtime" in names
        assert len(tools) == 2
