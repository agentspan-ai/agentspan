# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tool registry — registers @tool functions as Conductor workers for polling."""

from __future__ import annotations

import logging
from typing import Any, List

from agentspan.agents.runtime._dispatch import (
    _mcp_servers,
    _tool_approval_flags,
    _tool_registry,
    _tool_task_names,
    _tool_type_registry,
    make_tool_worker,
)

logger = logging.getLogger("agentspan.agents.runtime.tool_registry")


class ToolRegistry:
    """Registers ``@tool``-decorated functions as Conductor worker tasks.

    With server-side compilation, the workflow JSON comes from the Java
    runtime, but Python worker functions still need to be registered
    locally for Conductor task polling.
    """

    def register_tool_workers(self, tools: List[Any], agent_name: str) -> None:
        """Register tool functions as Conductor workers and populate global registries.

        Registers each ``@tool`` function as a Conductor worker task so that
        ``DynamicTask`` can resolve to it at runtime.  Also populates
        ``_tool_type_registry`` for HTTP/MCP tools and ``_tool_approval_flags``
        for tools that require human approval.
        """
        from conductor.client.worker.worker_task import worker_task

        from agentspan.agents.runtime.runtime import _default_task_def
        from agentspan.agents.tool import get_tool_defs

        tool_defs = get_tool_defs(tools)
        task_name = f"{agent_name}_dispatch"
        tool_funcs = {td.name: td.func for td in tool_defs if td.func is not None}

        _tool_registry[task_name] = tool_funcs

        from agentspan.agents.tool import MEDIA_TOOL_TYPES, RAG_TOOL_TYPES

        server_side_types = {"http", "mcp", "human"} | MEDIA_TOOL_TYPES | RAG_TOOL_TYPES
        for td in tool_defs:
            if td.tool_type in server_side_types and td.func is None:
                _tool_type_registry[td.name] = {"type": td.tool_type, "config": td.config}
                logger.debug("Registered server-side tool '%s' (type=%s)", td.name, td.tool_type)
            if td.tool_type == "mcp" and td.config not in _mcp_servers:
                _mcp_servers.append(td.config)

        for td in tool_defs:
            if td.approval_required:
                _tool_approval_flags[td.name] = True
                logger.info("Tool '%s' registered with approval_required=True", td.name)

        for td in tool_defs:
            if td.func is not None and td.tool_type in ("worker", "cli"):
                guardrails = td.guardrails if td.guardrails else None
                wrapper = make_tool_worker(td.func, td.name, guardrails=guardrails, tool_def=td)
                worker_task(
                    task_definition_name=td.name,
                    task_def=_default_task_def(td.name),
                    register_task_def=True,
                    overwrite_task_def=True,
                )(wrapper)
                _tool_task_names[td.name] = td.name
                logger.debug("Registered tool worker '%s'", td.name)

        logger.debug(
            "Registered %d worker tools for agent '%s'",
            len(tool_funcs),
            agent_name,
        )
