"""Tests for salesforce integration tools."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from autopilot.integrations.salesforce.tools import (
    get_tools,
    sf_create_record,
    sf_get_record,
    sf_query,
    sf_update_record,
)


def _set_sf_creds(monkeypatch):
    monkeypatch.setenv("SALESFORCE_INSTANCE_URL", "https://test.salesforce.com")
    monkeypatch.setenv("SALESFORCE_ACCESS_TOKEN", "sf-token-123")


class TestSfQuery:
    def test_missing_creds_raises(self, monkeypatch):
        monkeypatch.delenv("SALESFORCE_INSTANCE_URL", raising=False)
        monkeypatch.delenv("SALESFORCE_ACCESS_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="SALESFORCE_INSTANCE_URL"):
            sf_query("SELECT Id FROM Account")

    def test_missing_token_only_raises(self, monkeypatch):
        monkeypatch.setenv("SALESFORCE_INSTANCE_URL", "https://test.salesforce.com")
        monkeypatch.delenv("SALESFORCE_ACCESS_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="SALESFORCE_ACCESS_TOKEN"):
            sf_query("SELECT Id FROM Account")

    def test_empty_soql_raises(self, monkeypatch):
        _set_sf_creds(monkeypatch)
        with pytest.raises(ValueError, match="soql is required"):
            sf_query("")

    def test_successful_query(self, monkeypatch):
        _set_sf_creds(monkeypatch)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "records": [
                {"Id": "001", "Name": "Acme Corp"},
                {"Id": "002", "Name": "Globex"},
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        monkeypatch.setattr(
            "autopilot.integrations.salesforce.tools.httpx.get",
            lambda *a, **kw: mock_resp,
        )

        results = sf_query("SELECT Id, Name FROM Account")
        assert len(results) == 2
        assert results[0]["Name"] == "Acme Corp"

    def test_credentials_on_tool_def(self):
        assert sf_query._tool_def.credentials == [
            "SALESFORCE_INSTANCE_URL",
            "SALESFORCE_ACCESS_TOKEN",
        ]


class TestSfGetRecord:
    def test_empty_sobject_raises(self, monkeypatch):
        _set_sf_creds(monkeypatch)
        with pytest.raises(ValueError, match="sobject is required"):
            sf_get_record("", "001")

    def test_empty_record_id_raises(self, monkeypatch):
        _set_sf_creds(monkeypatch)
        with pytest.raises(ValueError, match="record_id is required"):
            sf_get_record("Account", "")

    def test_successful_get(self, monkeypatch):
        _set_sf_creds(monkeypatch)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"Id": "001", "Name": "Acme Corp"}
        mock_resp.raise_for_status = MagicMock()

        monkeypatch.setattr(
            "autopilot.integrations.salesforce.tools.httpx.get",
            lambda *a, **kw: mock_resp,
        )

        result = sf_get_record("Account", "001")
        assert result["Name"] == "Acme Corp"

    def test_credentials_on_tool_def(self):
        assert sf_get_record._tool_def.credentials == [
            "SALESFORCE_INSTANCE_URL",
            "SALESFORCE_ACCESS_TOKEN",
        ]


class TestSfCreateRecord:
    def test_empty_sobject_raises(self, monkeypatch):
        _set_sf_creds(monkeypatch)
        with pytest.raises(ValueError, match="sobject is required"):
            sf_create_record("", {"Name": "Test"})

    def test_empty_fields_raises(self, monkeypatch):
        _set_sf_creds(monkeypatch)
        with pytest.raises(ValueError, match="fields is required"):
            sf_create_record("Account", {})

    def test_successful_create(self, monkeypatch):
        _set_sf_creds(monkeypatch)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "003", "success": True}
        mock_resp.raise_for_status = MagicMock()

        monkeypatch.setattr(
            "autopilot.integrations.salesforce.tools.httpx.post",
            lambda *a, **kw: mock_resp,
        )

        result = sf_create_record("Account", {"Name": "New Corp"})
        assert result["id"] == "003"

    def test_credentials_on_tool_def(self):
        assert sf_create_record._tool_def.credentials == [
            "SALESFORCE_INSTANCE_URL",
            "SALESFORCE_ACCESS_TOKEN",
        ]


class TestSfUpdateRecord:
    def test_empty_sobject_raises(self, monkeypatch):
        _set_sf_creds(monkeypatch)
        with pytest.raises(ValueError, match="sobject is required"):
            sf_update_record("", "001", {"Name": "new"})

    def test_empty_record_id_raises(self, monkeypatch):
        _set_sf_creds(monkeypatch)
        with pytest.raises(ValueError, match="record_id is required"):
            sf_update_record("Account", "", {"Name": "new"})

    def test_empty_fields_raises(self, monkeypatch):
        _set_sf_creds(monkeypatch)
        with pytest.raises(ValueError, match="fields is required"):
            sf_update_record("Account", "001", {})

    def test_successful_update(self, monkeypatch):
        _set_sf_creds(monkeypatch)

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        monkeypatch.setattr(
            "autopilot.integrations.salesforce.tools.httpx.patch",
            lambda *a, **kw: mock_resp,
        )

        result = sf_update_record("Account", "001", {"Name": "Updated"})
        assert "Account/001" in result

    def test_credentials_on_tool_def(self):
        assert sf_update_record._tool_def.credentials == [
            "SALESFORCE_INSTANCE_URL",
            "SALESFORCE_ACCESS_TOKEN",
        ]


class TestGetTools:
    def test_returns_all_tools(self):
        tools = get_tools()
        names = [t._tool_def.name for t in tools]
        assert "sf_query" in names
        assert "sf_get_record" in names
        assert "sf_create_record" in names
        assert "sf_update_record" in names
        assert len(tools) == 4
