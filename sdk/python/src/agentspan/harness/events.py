# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Event types yielded by ``HarnessRuntime.submit()``.

Since the conversation loop now runs server-side as an agentspan ``Agent``
execution, the harness yields the same :class:`AgentEvent` type the rest
of the SDK uses (re-exported from ``agentspan.agents``). We keep the
``RuntimeEvent`` name as an alias for documentation continuity.

The Conductor :class:`AgentEvent` carries a ``type`` (``THINKING``,
``MESSAGE``, ``TOOL_CALL``, ``TOOL_RESULT``, ``HANDOFF``, ``WAITING``,
``DONE``, ``ERROR``, ``GUARDRAIL_PASS``, ``GUARDRAIL_FAIL``) plus
``execution_id`` and event-specific fields (``content``, ``tool_name``,
``args``, ``result``, ``output``).
"""

from __future__ import annotations

from agentspan.agents.result import AgentEvent, EventType

# Backward-compat alias.
RuntimeEvent = AgentEvent

__all__ = ["AgentEvent", "EventType", "RuntimeEvent"]
