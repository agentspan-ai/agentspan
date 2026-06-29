# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for MCP tool discovery, expansion, and caching."""

from unittest.mock import MagicMock, patch

import pytest

from conductor.ai.agents.runtime.mcp_discovery import (
    _discovery_cache,
    clear_discovery_cache,
    discover_mcp_tools,
    expand_mcp_tool_def,
)
from conductor.ai.agents.tool import mcp_tool

# Patch targets — these are the *source* modules for deferred imports
_CW_PATH = "conductor.client.workflow.conductor_workflow.ConductorWorkflow"
_LIST_PATH = "conductor.client.workflow.task.llm_tasks.list_mcp_tools.ListMcpTools"
_DISCOVER_PATH = "conductor.ai.agents.runtime.mcp_discovery.discover_mcp_tools"


@pytest.fixture(autouse=True)
def _clean_cache():
    """Clear the discovery cache between tests."""
    clear_discovery_cache()
    yield
    clear_discovery_cache()


def _mock_wf(fake_run):
    """Create a MagicMock ConductorWorkflow that returns *fake_run* on execute()."""
    mock_wf = MagicMock()
    mock_wf.execute.return_value = fake_run
    mock_wf.__rshift__ = MagicMock(return_value=mock_wf)
    return mock_wf


# ── discover_mcp_tools() ─────────────────────────────────────────────


class TestDiscoverMcpTools:
    """Test the discover_mcp_tools() function."""

    def test_successful_discovery(self):
        """Successful workflow run returns discovered tools."""
        mock_executor = MagicMock()

        fake_tools = [
            {
                "name": "get_weather",
                "description": "Get weather",
                "inputSchema": {"type": "object"},
            },
            {"name": "get_forecast", "description": "Get forecast", "inputSchema": {}},
        ]
        fake_run = MagicMock(is_successful=True, output={"tools": fake_tools})

        with patch(_CW_PATH, return_value=_mock_wf(fake_run)):
            result = discover_mcp_tools(mock_executor, "http://mcp.example.com/sse")

        assert len(result) == 2
        assert result[0]["name"] == "get_weather"
        assert result[1]["name"] == "get_forecast"

    def test_cache_hit(self):
        """Second call for same server returns cached result."""
        _discovery_cache["http://cached.example.com"] = [
            {"name": "cached_tool", "description": "Cached", "inputSchema": {}},
        ]

        mock_executor = MagicMock()
        result = discover_mcp_tools(mock_executor, "http://cached.example.com")

        assert len(result) == 1
        assert result[0]["name"] == "cached_tool"
        mock_executor.assert_not_called()

    def test_failed_workflow_returns_empty(self):
        """Failed workflow execution returns empty list and caches it."""
        mock_executor = MagicMock()
        fake_run = MagicMock(is_successful=False, reason_for_incompletion="Server error")

        with patch(_CW_PATH, return_value=_mock_wf(fake_run)):
            result = discover_mcp_tools(mock_executor, "http://fail.example.com")

        assert result == []
        assert "http://fail.example.com" in _discovery_cache

    def test_exception_returns_empty(self):
        """Exception during discovery returns empty list."""
        mock_executor = MagicMock()

        with patch(_CW_PATH, side_effect=RuntimeError("connection refused")):
            result = discover_mcp_tools(mock_executor, "http://broken.example.com")

        assert result == []
        assert "http://broken.example.com" in _discovery_cache

    def test_none_output_returns_empty(self):
        """Workflow completes but output is None."""
        mock_executor = MagicMock()
        fake_run = MagicMock(is_successful=True, output=None)

        with patch(_CW_PATH, return_value=_mock_wf(fake_run)):
            result = discover_mcp_tools(mock_executor, "http://empty.example.com")

        assert result == []

    def test_headers_passed_to_list_mcp_tools(self):
        """Headers are forwarded to the ListMcpTools task."""
        mock_executor = MagicMock()
        fake_run = MagicMock(is_successful=True, output={"tools": []})

        with patch(_CW_PATH, return_value=_mock_wf(fake_run)), patch(_LIST_PATH) as MockList:
            discover_mcp_tools(
                mock_executor,
                "http://auth.example.com",
                headers={"Authorization": "Bearer token123"},
            )

            MockList.assert_called_once_with(
                task_ref_name="list_tools",
                mcp_server="http://auth.example.com",
                headers={"Authorization": "Bearer token123"},
            )


class TestClearDiscoveryCache:
    """Test clear_discovery_cache() utility."""

    def test_clears_all_entries(self):
        _discovery_cache["http://a.com"] = [{"name": "a"}]
        _discovery_cache["http://b.com"] = [{"name": "b"}]

        clear_discovery_cache()

        assert len(_discovery_cache) == 0


# ── expand_mcp_tool_def() ────────────────────────────────────────────


class TestExpandMcpToolDef:
    """Test the expand_mcp_tool_def() function."""

    def _make_mcp_td(self, **kwargs):
        return mcp_tool(
            server_url=kwargs.get("server_url", "http://mcp.example.com"),
            headers=kwargs.get("headers"),
            tool_names=kwargs.get("tool_names"),
            max_tools=kwargs.get("max_tools", 64),
        )

    def test_expand_discovered_tools(self):
        """Discovered tools are expanded into individual ToolDefs."""
        td = self._make_mcp_td()
        discovered = [
            {
                "name": "get_weather",
                "description": "Get weather",
                "inputSchema": {"type": "object", "properties": {"city": {"type": "string"}}},
            },
            {
                "name": "get_forecast",
                "description": "Get forecast",
                "inputSchema": {"type": "object"},
            },
        ]

        result = expand_mcp_tool_def(td, discovered)

        assert len(result) == 2
        assert result[0].name == "get_weather"
        assert result[0].description == "Get weather"
        assert result[0].input_schema["properties"]["city"]["type"] == "string"
        assert result[0].tool_type == "mcp"
        assert result[0].config["server_url"] == "http://mcp.example.com"
        assert result[1].name == "get_forecast"

    def test_empty_discovered_returns_original(self):
        """Empty discovered list falls back to original ToolDef."""
        td = self._make_mcp_td()
        result = expand_mcp_tool_def(td, [])
        assert len(result) == 1
        assert result[0] is td

    def test_tool_names_whitelist(self):
        """Only tools in tool_names whitelist are included."""
        td = self._make_mcp_td(tool_names=["get_weather"])
        discovered = [
            {"name": "get_weather", "description": "Get weather", "inputSchema": {}},
            {"name": "get_forecast", "description": "Get forecast", "inputSchema": {}},
            {"name": "get_alerts", "description": "Get alerts", "inputSchema": {}},
        ]

        result = expand_mcp_tool_def(td, discovered)

        assert len(result) == 1
        assert result[0].name == "get_weather"

    def test_tool_names_all_filtered_falls_back(self):
        """If whitelist filters out everything, fall back to original."""
        td = self._make_mcp_td(tool_names=["nonexistent_tool"])
        discovered = [
            {"name": "get_weather", "description": "Get weather", "inputSchema": {}},
        ]

        result = expand_mcp_tool_def(td, discovered)

        assert len(result) == 1
        assert result[0] is td

    def test_headers_inherited(self):
        """Expanded tools inherit headers from original config."""
        td = self._make_mcp_td(headers={"Authorization": "Bearer xyz"})
        discovered = [
            {"name": "get_weather", "description": "Weather", "inputSchema": {}},
        ]

        result = expand_mcp_tool_def(td, discovered)

        assert result[0].config["headers"] == {"Authorization": "Bearer xyz"}

    def test_skips_tools_with_empty_name(self):
        """Tools without a name are skipped."""
        td = self._make_mcp_td()
        discovered = [
            {"name": "", "description": "No name", "inputSchema": {}},
            {"name": "valid_tool", "description": "Valid", "inputSchema": {}},
        ]

        result = expand_mcp_tool_def(td, discovered)

        assert len(result) == 1
        assert result[0].name == "valid_tool"

    def test_missing_input_schema_defaults_to_empty(self):
        """Tools without inputSchema get empty dict."""
        td = self._make_mcp_td()
        discovered = [
            {"name": "no_schema_tool", "description": "No schema"},
        ]

        result = expand_mcp_tool_def(td, discovered)

        assert result[0].input_schema == {}


# Compiler-specific tests removed — compilation is now server-side only.
