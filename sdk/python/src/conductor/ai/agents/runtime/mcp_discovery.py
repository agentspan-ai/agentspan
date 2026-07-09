# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""MCP tool discovery — discovers individual tools from MCP servers at compile time.

Uses Conductor's ``LIST_MCP_TOOLS`` system task to query an MCP server and
expand a single ``mcp_tool()`` definition into individual ``ToolDef`` instances,
each with proper name, description, and input schema.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from conductor.ai.agents.tool import ToolDef
    from conductor.client.workflow.executor.workflow_executor import WorkflowExecutor

logger = logging.getLogger("conductor.ai.agents.runtime.mcp_discovery")

# Module-level cache: server_url -> list of discovered tool dicts
_discovery_cache: Dict[str, List[Dict[str, Any]]] = {}


def discover_mcp_tools(
    executor: "WorkflowExecutor",
    server_url: str,
    headers: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Discover tools from an MCP server via ``LIST_MCP_TOOLS``.

    Builds a minimal one-task workflow, executes it inline (no pre-registration),
    and returns the list of tool descriptors from the server output.

    Results are cached per *server_url* so repeated calls for the same server
    are free.

    Args:
        executor: A ``WorkflowExecutor`` used to run the discovery workflow.
        server_url: URL of the MCP server.
        headers: Optional HTTP headers for MCP server authentication.

    Returns:
        A list of dicts, each with ``name``, ``description``, and
        ``inputSchema`` keys.  Returns ``[]`` on failure (graceful fallback).
    """
    if server_url in _discovery_cache:
        logger.debug("MCP discovery cache hit for %s", server_url)
        return _discovery_cache[server_url]

    try:
        from conductor.client.workflow.conductor_workflow import ConductorWorkflow
        from conductor.client.workflow.task.llm_tasks.list_mcp_tools import ListMcpTools

        wf = ConductorWorkflow(
            executor=executor,
            name="__mcp_discovery__",
            version=1,
            description="MCP tool discovery (ephemeral)",
        )

        list_task = ListMcpTools(
            task_ref_name="list_tools",
            mcp_server=server_url,
            headers=headers,
        )

        wf >> list_task
        wf.output_parameters({"tools": "${list_tools.output.tools}"})

        run = wf.execute(wait_for_seconds=30)

        if not run.is_successful:
            reason = getattr(run, "reason_for_incompletion", None) or "unknown"
            logger.warning(
                "MCP discovery workflow failed for %s: %s",
                server_url,
                reason,
            )
            _discovery_cache[server_url] = []
            return []

        tools = (run.output or {}).get("tools") or []
        logger.info("Discovered %d tools from MCP server %s", len(tools), server_url)
        _discovery_cache[server_url] = tools
        return tools

    except Exception as exc:
        logger.warning("MCP discovery failed for %s: %s", server_url, exc)
        _discovery_cache[server_url] = []
        return []


def expand_mcp_tool_def(
    mcp_td: "ToolDef",
    discovered: List[Dict[str, Any]],
) -> List["ToolDef"]:
    """Expand a single MCP ``ToolDef`` into individual tool definitions.

    Each discovered tool becomes its own ``ToolDef`` with the correct name,
    description, and input schema, while inheriting the original MCP config
    (``server_url``, ``headers``).

    If *tool_names* is set in the original tool's config, only tools whose
    names appear in that whitelist are included.

    If nothing was discovered or everything was filtered out, the original
    ``ToolDef`` is returned unchanged (graceful fallback).

    Args:
        mcp_td: The original MCP ``ToolDef`` from ``mcp_tool()``.
        discovered: Tool descriptors from :func:`discover_mcp_tools`.

    Returns:
        A list of expanded ``ToolDef`` instances.
    """
    from conductor.ai.agents.tool import ToolDef

    if not discovered:
        return [mcp_td]

    # Apply tool_names whitelist if configured
    allowed_names = mcp_td.config.get("tool_names")
    if allowed_names is not None:
        allowed_set = set(allowed_names)
        discovered = [t for t in discovered if t.get("name") in allowed_set]

    if not discovered:
        return [mcp_td]

    expanded: List[ToolDef] = []
    for tool_info in discovered:
        name = tool_info.get("name", "")
        if not name:
            continue

        # Inherit server_url and headers from original config
        config = {
            "server_url": mcp_td.config["server_url"],
            "max_tools": mcp_td.config.get("max_tools", 64),
        }
        if "headers" in mcp_td.config:
            config["headers"] = mcp_td.config["headers"]

        td = ToolDef(
            name=name,
            description=tool_info.get("description", ""),
            input_schema=tool_info.get("inputSchema") or {},
            tool_type="mcp",
            config=config,
        )
        expanded.append(td)

    return expanded if expanded else [mcp_td]


def clear_discovery_cache() -> None:
    """Clear the MCP tool discovery cache.

    Useful in tests or when MCP server tool definitions change.
    """
    _discovery_cache.clear()
