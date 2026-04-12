"""Tests for hubspot integration tools."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from autopilot.integrations.hubspot.tools import (
    get_tools,
    hubspot_create_contact,
    hubspot_get_contact,
    hubspot_get_deal,
    hubspot_list_deals,
    hubspot_search_contacts,
)


class TestHubspotSearchContacts:
    def test_missing_token_raises(self, monkeypatch):
        monkeypatch.delenv("HUBSPOT_ACCESS_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="HUBSPOT_ACCESS_TOKEN"):
            hubspot_search_contacts("alice")

    def test_empty_query_raises(self, monkeypatch):
        monkeypatch.setenv("HUBSPOT_ACCESS_TOKEN", "hs-token")
        with pytest.raises(ValueError, match="query is required"):
            hubspot_search_contacts("")

    def test_successful_search(self, monkeypatch):
        monkeypatch.setenv("HUBSPOT_ACCESS_TOKEN", "hs-token")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": [
                {
                    "id": "c1",
                    "properties": {
                        "email": "alice@test.com",
                        "firstname": "Alice",
                        "lastname": "Smith",
                    },
                }
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        monkeypatch.setattr(
            "autopilot.integrations.hubspot.tools.httpx.post",
            lambda *a, **kw: mock_resp,
        )

        results = hubspot_search_contacts("alice")
        assert len(results) == 1
        assert results[0]["email"] == "alice@test.com"

    def test_credentials_on_tool_def(self):
        assert hubspot_search_contacts._tool_def.credentials == ["HUBSPOT_ACCESS_TOKEN"]


class TestHubspotGetContact:
    def test_empty_contact_id_raises(self, monkeypatch):
        monkeypatch.setenv("HUBSPOT_ACCESS_TOKEN", "hs-token")
        with pytest.raises(ValueError, match="contact_id is required"):
            hubspot_get_contact("")

    def test_successful_get(self, monkeypatch):
        monkeypatch.setenv("HUBSPOT_ACCESS_TOKEN", "hs-token")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "id": "c1",
            "properties": {"email": "alice@test.com"},
        }
        mock_resp.raise_for_status = MagicMock()

        monkeypatch.setattr(
            "autopilot.integrations.hubspot.tools.httpx.get",
            lambda *a, **kw: mock_resp,
        )

        result = hubspot_get_contact("c1")
        assert result["id"] == "c1"

    def test_credentials_on_tool_def(self):
        assert hubspot_get_contact._tool_def.credentials == ["HUBSPOT_ACCESS_TOKEN"]


class TestHubspotListDeals:
    def test_missing_token_raises(self, monkeypatch):
        monkeypatch.delenv("HUBSPOT_ACCESS_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="HUBSPOT_ACCESS_TOKEN"):
            hubspot_list_deals()

    def test_successful_list(self, monkeypatch):
        monkeypatch.setenv("HUBSPOT_ACCESS_TOKEN", "hs-token")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": [
                {
                    "id": "d1",
                    "properties": {
                        "dealname": "Big Deal",
                        "amount": "50000",
                        "dealstage": "closedwon",
                    },
                }
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        monkeypatch.setattr(
            "autopilot.integrations.hubspot.tools.httpx.get",
            lambda *a, **kw: mock_resp,
        )

        results = hubspot_list_deals()
        assert len(results) == 1
        assert results[0]["dealname"] == "Big Deal"

    def test_limit_clamped(self, monkeypatch):
        monkeypatch.setenv("HUBSPOT_ACCESS_TOKEN", "hs-token")

        captured = {}

        def mock_get(*args, **kwargs):
            captured.update(kwargs.get("params", {}))
            resp = MagicMock()
            resp.json.return_value = {"results": []}
            resp.raise_for_status = MagicMock()
            return resp

        monkeypatch.setattr("autopilot.integrations.hubspot.tools.httpx.get", mock_get)

        hubspot_list_deals(limit=200)
        assert captured["limit"] == 100

    def test_credentials_on_tool_def(self):
        assert hubspot_list_deals._tool_def.credentials == ["HUBSPOT_ACCESS_TOKEN"]


class TestHubspotGetDeal:
    def test_empty_deal_id_raises(self, monkeypatch):
        monkeypatch.setenv("HUBSPOT_ACCESS_TOKEN", "hs-token")
        with pytest.raises(ValueError, match="deal_id is required"):
            hubspot_get_deal("")

    def test_credentials_on_tool_def(self):
        assert hubspot_get_deal._tool_def.credentials == ["HUBSPOT_ACCESS_TOKEN"]


class TestHubspotCreateContact:
    def test_empty_email_raises(self, monkeypatch):
        monkeypatch.setenv("HUBSPOT_ACCESS_TOKEN", "hs-token")
        with pytest.raises(ValueError, match="email is required"):
            hubspot_create_contact("")

    def test_successful_create(self, monkeypatch):
        monkeypatch.setenv("HUBSPOT_ACCESS_TOKEN", "hs-token")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "c_new"}
        mock_resp.raise_for_status = MagicMock()

        monkeypatch.setattr(
            "autopilot.integrations.hubspot.tools.httpx.post",
            lambda *a, **kw: mock_resp,
        )

        result = hubspot_create_contact("new@test.com", "New", "User")
        assert result["id"] == "c_new"

    def test_credentials_on_tool_def(self):
        assert hubspot_create_contact._tool_def.credentials == ["HUBSPOT_ACCESS_TOKEN"]


class TestGetTools:
    def test_returns_all_tools(self):
        tools = get_tools()
        names = [t._tool_def.name for t in tools]
        assert "hubspot_search_contacts" in names
        assert "hubspot_get_contact" in names
        assert "hubspot_list_deals" in names
        assert "hubspot_get_deal" in names
        assert "hubspot_create_contact" in names
        assert len(tools) == 5
