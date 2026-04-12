"""Tests for google_analytics integration tools."""

from __future__ import annotations

from unittest.mock import MagicMock

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

    def test_successful_report(self, monkeypatch):
        _set_ga_creds(monkeypatch)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "rows": [{"dimensionValues": [{"value": "20240101"}], "metricValues": [{"value": "100"}]}],
            "metricHeaders": [{"name": "activeUsers"}],
        }
        mock_resp.raise_for_status = MagicMock()

        monkeypatch.setattr(
            "autopilot.integrations.google_analytics.tools.httpx.post",
            lambda *a, **kw: mock_resp,
        )

        result = ga_run_report(["activeUsers"], dimensions=["date"])
        assert "rows" in result
        assert len(result["rows"]) == 1

    def test_credentials_on_tool_def(self):
        assert ga_run_report._tool_def.credentials == ["GA_ACCESS_TOKEN", "GA_PROPERTY_ID"]


class TestGaGetRealtime:
    def test_missing_creds_raises(self, monkeypatch):
        monkeypatch.delenv("GA_ACCESS_TOKEN", raising=False)
        monkeypatch.delenv("GA_PROPERTY_ID", raising=False)
        with pytest.raises(RuntimeError, match="GA_ACCESS_TOKEN"):
            ga_get_realtime()

    def test_successful_realtime(self, monkeypatch):
        _set_ga_creds(monkeypatch)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "rows": [{"metricValues": [{"value": "42"}]}],
        }
        mock_resp.raise_for_status = MagicMock()

        monkeypatch.setattr(
            "autopilot.integrations.google_analytics.tools.httpx.post",
            lambda *a, **kw: mock_resp,
        )

        result = ga_get_realtime()
        assert "rows" in result

    def test_credentials_on_tool_def(self):
        assert ga_get_realtime._tool_def.credentials == ["GA_ACCESS_TOKEN", "GA_PROPERTY_ID"]


class TestGetTools:
    def test_returns_all_tools(self):
        tools = get_tools()
        names = [t._tool_def.name for t in tools]
        assert "ga_run_report" in names
        assert "ga_get_realtime" in names
        assert len(tools) == 2
