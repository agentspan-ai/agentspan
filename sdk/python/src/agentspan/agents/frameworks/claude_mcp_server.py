# src/agentspan/agents/frameworks/claude_mcp_server.py
# Copyright (c) 2025 Agentspan
"""AgentspanMcpServer — in-process MCP bridge between Claude and Conductor.

Wraps FastMCP to expose:
  - @tool functions as MCP tools → dispatched to Conductor SIMPLE tasks
  - spawn_subagent              → Conductor SUB_WORKFLOW
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class AgentspanMcpServer:
    """Bridges the Agentspan/Conductor ecosystem to Claude via in-process MCP.

    Build once per worker execution, call build() to get the McpSdkServerConfig
    to pass into ClaudeAgentOptions(mcp_servers={"agentspan": ...}).
    """

    def __init__(
        self,
        *,
        tools: List[Callable],
        subagent_workflow_name: Optional[str],
        conductor_client: Any,
        event_client: Any,
        parent_workflow_id: str,
    ) -> None:
        self._tools = tools
        self._subagent_workflow_name = subagent_workflow_name
        self._conductor = conductor_client
        self._events = event_client
        self._parent_workflow_id = parent_workflow_id
        self._mcp: Any = None  # FastMCP instance, set by build()

    # ── Public API ────────────────────────────────────────────────────────────

    def build(self) -> Dict[str, Any]:
        """Build and return the McpSdkServerConfig dict for ClaudeAgentOptions.

        The ``instance`` field is set to the underlying low-level MCP Server
        (``FastMCP._mcp_server``) because ``claude_agent_sdk`` accesses
        ``instance.request_handlers`` directly.  In MCP SDK >= 1.2, FastMCP
        wraps a low-level ``mcp.server.lowlevel.Server`` which owns the
        ``request_handlers`` dict; exposing the FastMCP wrapper would cause a
        ``AttributeError`` inside the SDK's ``_handle_sdk_mcp_request`` method.
        """
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("agentspan")

        for tool_fn in self._tools:
            self._register_tool(mcp, tool_fn)

        if self._subagent_workflow_name is not None:
            self._register_spawn_subagent(mcp)

        self._mcp = mcp
        # The claude_agent_sdk accesses instance.request_handlers directly (from the
        # low-level MCP Server), but FastMCP wraps that in mcp._mcp_server.
        # Expose request_handlers on the FastMCP wrapper so the SDK can reach them.
        if hasattr(mcp, "_mcp_server") and not hasattr(mcp, "request_handlers"):
            mcp.request_handlers = mcp._mcp_server.request_handlers  # type: ignore[attr-defined]
        # claude_agent_sdk reads server.version in the MCP initialize response.
        # FastMCP does not expose version at the top level; patch it so the SDK
        # gets a valid value and does not silently skip tool discovery.
        if not hasattr(mcp, "version"):
            mcp.version = getattr(getattr(mcp, "_mcp_server", None), "version", None) or "1.0.0"  # type: ignore[attr-defined]
        return {"type": "sdk", "name": "agentspan", "instance": mcp}

    # ── Internal dispatch (also tested directly) ──────────────────────────────

    async def _dispatch_tool(self, tool_name: str, input_data: Dict[str, Any]) -> str:
        """Dispatch a tool call to Conductor and return the result.

        Emits tool_call and tool_result events around the dispatch.
        Event failures are non-fatal (logged and swallowed).
        """
        try:
            await self._events.push(
                self._parent_workflow_id,
                "tool_call",
                {"source": "mcp", "toolName": tool_name, "args": input_data},
            )
        except Exception as exc:
            logger.debug("Event push failed (tool_call/%s): %s", tool_name, exc)

        workflow_id = await self._conductor.start_tool_workflow(tool_name, input_data)
        result = await self._conductor.poll_until_done(workflow_id)

        try:
            await self._events.push(
                self._parent_workflow_id,
                "tool_result",
                {
                    "source": "mcp",
                    "toolName": tool_name,
                    "conductorTaskId": workflow_id,
                    "result": result,
                },
            )
        except Exception as exc:
            logger.debug("Event push failed (tool_result/%s): %s", tool_name, exc)

        return result

    async def _dispatch_subagent(self, prompt: str) -> str:
        """Start a Conductor SUB_WORKFLOW for the subagent and return its result."""
        if self._subagent_workflow_name is None:
            raise RuntimeError(
                "conductor_subagents=False — cannot spawn Conductor sub-workflow"
            )

        sub_id = await self._conductor.start_workflow(
            self._subagent_workflow_name,
            {"prompt": prompt, "_is_subagent": True},
        )

        try:
            await self._events.push(
                self._parent_workflow_id,
                "subagent_start",
                {"subWorkflowId": sub_id, "parentWorkflowId": self._parent_workflow_id, "prompt": prompt},
            )
        except Exception as exc:
            logger.debug("Event push failed (subagent_start): %s", exc)

        result = await self._conductor.poll_until_done(sub_id)

        try:
            await self._events.push(
                self._parent_workflow_id,
                "subagent_stop",
                {"subWorkflowId": sub_id, "parentWorkflowId": self._parent_workflow_id, "result": result},
            )
        except Exception as exc:
            logger.debug("Event push failed (subagent_stop): %s", exc)

        return result

    # ── Private helpers ───────────────────────────────────────────────────────

    def _register_tool(self, mcp: Any, tool_fn: Callable) -> None:
        """Register a @tool function as a FastMCP tool with Conductor dispatch.

        The wrapper preserves the original function's signature and annotations so
        FastMCP builds the correct Pydantic argument schema.  Without this, FastMCP
        would generate a schema with a single ``kwargs`` field (from ``**kwargs``),
        and Claude would send arguments that don't match the expected schema.
        """
        import functools
        import inspect

        td = getattr(tool_fn, "_tool_def", None)
        if td is None:
            logger.warning("Skipping %s: no _tool_def attribute", tool_fn)
            return

        tool_name = td.name
        description = td.description or f"Run {tool_name}"

        # Capture tool_name in closure
        dispatch = self._dispatch_tool

        # Build a wrapper that preserves the original signature so FastMCP can
        # generate the correct Pydantic argument schema for the tool.
        orig_sig = inspect.signature(tool_fn)
        orig_annotations = getattr(tool_fn, "__annotations__", {}).copy()

        async def _mcp_wrapper(**kwargs: Any) -> str:
            return await dispatch(tool_name, kwargs)

        # Copy signature and annotations so FastMCP uses the right schema.
        _mcp_wrapper.__signature__ = orig_sig  # type: ignore[attr-defined]
        _mcp_wrapper.__annotations__ = {**orig_annotations, "return": str}
        _mcp_wrapper.__name__ = tool_name
        _mcp_wrapper.__doc__ = description

        mcp.add_tool(_mcp_wrapper, name=tool_name, description=description)
        logger.debug("Registered MCP tool: %s", tool_name)

    def _register_spawn_subagent(self, mcp: Any) -> None:
        """Register spawn_subagent as a FastMCP tool."""
        dispatch = self._dispatch_subagent

        async def spawn_subagent(prompt: str) -> str:
            """Spawn a subagent as a Conductor sub-workflow and return its result."""
            return await dispatch(prompt)

        mcp.add_tool(spawn_subagent, name="spawn_subagent", description="Spawn a subagent as a Conductor sub-workflow and return its result.")
        logger.debug("Registered MCP tool: spawn_subagent")
