"""MCP integration tools — wraps Agentspan's mcp_tool() for dynamic tool discovery.

Tier 2 integration: users or the orchestrator point to any MCP server URL,
and tools are discovered and exposed automatically via the MCP protocol.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agentspan.agents import mcp_tool, tool
from agentspan.agents.tool import ToolDef


# ---------------------------------------------------------------------------
# In-memory registry of configured MCP servers
# ---------------------------------------------------------------------------

_mcp_servers: Dict[str, Dict[str, Any]] = {}


def create_mcp_integration(
    server_url: str,
    credentials: Optional[List[str]] = None,
    tool_names: Optional[List[str]] = None,
) -> List[ToolDef]:
    """Create an MCP integration from a server URL.

    This wraps Agentspan's mcp_tool() to discover and expose tools from any
    MCP server.

    Args:
        server_url: URL of the MCP server.
        credentials: Optional credential names for header placeholders.
        tool_names: Optional whitelist of tool names to include.

    Returns:
        A list containing the ToolDef for the MCP server.

    Raises:
        ValueError: If server_url is empty.
    """
    if not server_url:
        raise ValueError("server_url is required")

    kwargs: Dict[str, Any] = {"server_url": server_url}
    if credentials:
        kwargs["credentials"] = credentials
    if tool_names:
        kwargs["tool_names"] = tool_names
    return [mcp_tool(**kwargs)]


def get_configured_servers() -> Dict[str, Dict[str, Any]]:
    """Return all configured MCP servers."""
    return dict(_mcp_servers)


def reset_servers() -> None:
    """Clear all configured servers. Used for test isolation."""
    _mcp_servers.clear()


@tool
def add_mcp_integration(server_url: str, name: str = "", credentials: str = "") -> str:
    """Add an MCP server as an integration source.

    The orchestrator calls this when a user wants to connect a custom MCP server.
    The server's tools become available for agent creation.

    Args:
        server_url: URL of the MCP server (e.g. "http://localhost:3001/mcp").
        name: Optional display name for the integration.
        credentials: Comma-separated credential names (e.g. "API_KEY,TOKEN").

    Returns:
        Confirmation message with the server details.

    Raises:
        ValueError: If server_url is empty.
    """
    if not server_url:
        raise ValueError("server_url is required — provide the MCP server URL")

    display_name = name or server_url
    cred_list = [c.strip() for c in credentials.split(",") if c.strip()] if credentials else []

    _mcp_servers[display_name] = {
        "server_url": server_url,
        "name": display_name,
        "credentials": cred_list,
    }

    cred_info = f" (credentials: {', '.join(cred_list)})" if cred_list else ""
    return (
        f"MCP integration '{display_name}' added successfully.\n"
        f"Server URL: {server_url}{cred_info}\n"
        f"Tools will be discovered from this server when creating agents."
    )


def get_mcp_tools_for_server(server_url: str) -> List[ToolDef]:
    """Discover and return tools from a configured MCP server.

    This is called during integration resolution (Tier 2 fallback) to check
    if an MCP server can provide a needed tool.

    Args:
        server_url: URL of the MCP server.

    Returns:
        List of ToolDef instances from the server.
    """
    return create_mcp_integration(server_url)
