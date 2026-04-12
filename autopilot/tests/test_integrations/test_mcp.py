"""Tests for MCP integration tools."""

from __future__ import annotations

import pytest

from agentspan.agents.tool import ToolDef

from autopilot.integrations.mcp.tools import (
    add_mcp_integration,
    create_mcp_integration,
    get_configured_servers,
    reset_servers,
)


@pytest.fixture(autouse=True)
def _clean_mcp_servers():
    """Reset MCP server state before and after each test."""
    reset_servers()
    yield
    reset_servers()


class TestCreateMcpIntegration:
    """Tests for create_mcp_integration()."""

    def test_returns_list_with_tool_def(self):
        result = create_mcp_integration("http://localhost:3001/mcp")
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], ToolDef)

    def test_tool_def_has_mcp_type(self):
        result = create_mcp_integration("http://localhost:3001/mcp")
        td = result[0]
        assert td.tool_type == "mcp"

    def test_tool_def_config_contains_server_url(self):
        url = "http://example.com:9090/mcp"
        result = create_mcp_integration(url)
        td = result[0]
        assert td.config["server_url"] == url

    def test_with_credentials(self):
        result = create_mcp_integration(
            "http://localhost:3001/mcp",
            credentials=["API_KEY"],
        )
        td = result[0]
        assert "API_KEY" in td.credentials

    def test_with_tool_names_whitelist(self):
        result = create_mcp_integration(
            "http://localhost:3001/mcp",
            tool_names=["search", "read"],
        )
        td = result[0]
        assert td.config["tool_names"] == ["search", "read"]

    def test_empty_url_raises_value_error(self):
        with pytest.raises(ValueError, match="server_url is required"):
            create_mcp_integration("")


class TestAddMcpIntegration:
    """Tests for the add_mcp_integration @tool function."""

    def test_adds_server_to_configured_list(self):
        result = add_mcp_integration(
            server_url="http://localhost:3001/mcp",
            name="my-tools",
        )
        assert "my-tools" in result
        assert "added successfully" in result
        servers = get_configured_servers()
        assert "my-tools" in servers
        assert servers["my-tools"]["server_url"] == "http://localhost:3001/mcp"

    def test_uses_url_as_name_when_name_empty(self):
        url = "http://localhost:3001/mcp"
        add_mcp_integration(server_url=url)
        servers = get_configured_servers()
        assert url in servers

    def test_validates_url_empty_raises(self):
        with pytest.raises(ValueError, match="server_url is required"):
            add_mcp_integration(server_url="")

    def test_parses_comma_separated_credentials(self):
        add_mcp_integration(
            server_url="http://localhost:3001/mcp",
            name="creds-test",
            credentials="API_KEY, TOKEN",
        )
        servers = get_configured_servers()
        assert servers["creds-test"]["credentials"] == ["API_KEY", "TOKEN"]

    def test_empty_credentials_string_results_in_empty_list(self):
        add_mcp_integration(
            server_url="http://localhost:3001/mcp",
            name="no-creds",
            credentials="",
        )
        servers = get_configured_servers()
        assert servers["no-creds"]["credentials"] == []


class TestToolDefType:
    """Verify the tool_type field is correctly set."""

    def test_mcp_tool_def_has_correct_type(self):
        result = create_mcp_integration("http://localhost:3001/mcp")
        td = result[0]
        assert td.tool_type == "mcp", f"Expected tool_type='mcp', got '{td.tool_type}'"

    def test_mcp_tool_def_is_not_worker_type(self):
        result = create_mcp_integration("http://localhost:3001/mcp")
        td = result[0]
        assert td.tool_type != "worker"

    def test_mcp_tool_def_is_not_http_type(self):
        result = create_mcp_integration("http://localhost:3001/mcp")
        td = result[0]
        assert td.tool_type != "http"
