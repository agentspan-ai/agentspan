"""Tests for hubspot integration tools — real e2e, no mocks."""

from __future__ import annotations

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

    def test_credentials_on_tool_def(self):
        assert hubspot_search_contacts._tool_def.credentials == ["HUBSPOT_ACCESS_TOKEN"]

    def test_tool_def_name(self):
        assert hubspot_search_contacts._tool_def.name == "hubspot_search_contacts"

    def test_tool_def_has_description(self):
        assert hubspot_search_contacts._tool_def.description
        assert len(hubspot_search_contacts._tool_def.description) > 10


class TestHubspotGetContact:
    def test_empty_contact_id_raises(self, monkeypatch):
        monkeypatch.setenv("HUBSPOT_ACCESS_TOKEN", "hs-token")
        with pytest.raises(ValueError, match="contact_id is required"):
            hubspot_get_contact("")

    def test_credentials_on_tool_def(self):
        assert hubspot_get_contact._tool_def.credentials == ["HUBSPOT_ACCESS_TOKEN"]

    def test_tool_def_name(self):
        assert hubspot_get_contact._tool_def.name == "hubspot_get_contact"


class TestHubspotListDeals:
    def test_missing_token_raises(self, monkeypatch):
        monkeypatch.delenv("HUBSPOT_ACCESS_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="HUBSPOT_ACCESS_TOKEN"):
            hubspot_list_deals()

    def test_credentials_on_tool_def(self):
        assert hubspot_list_deals._tool_def.credentials == ["HUBSPOT_ACCESS_TOKEN"]

    def test_tool_def_name(self):
        assert hubspot_list_deals._tool_def.name == "hubspot_list_deals"


class TestHubspotGetDeal:
    def test_empty_deal_id_raises(self, monkeypatch):
        monkeypatch.setenv("HUBSPOT_ACCESS_TOKEN", "hs-token")
        with pytest.raises(ValueError, match="deal_id is required"):
            hubspot_get_deal("")

    def test_credentials_on_tool_def(self):
        assert hubspot_get_deal._tool_def.credentials == ["HUBSPOT_ACCESS_TOKEN"]

    def test_tool_def_name(self):
        assert hubspot_get_deal._tool_def.name == "hubspot_get_deal"


class TestHubspotCreateContact:
    def test_empty_email_raises(self, monkeypatch):
        monkeypatch.setenv("HUBSPOT_ACCESS_TOKEN", "hs-token")
        with pytest.raises(ValueError, match="email is required"):
            hubspot_create_contact("")

    def test_credentials_on_tool_def(self):
        assert hubspot_create_contact._tool_def.credentials == ["HUBSPOT_ACCESS_TOKEN"]

    def test_tool_def_name(self):
        assert hubspot_create_contact._tool_def.name == "hubspot_create_contact"


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
