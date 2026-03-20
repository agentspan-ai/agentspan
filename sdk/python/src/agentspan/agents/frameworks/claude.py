# sdk/python/src/agentspan/agents/frameworks/claude.py
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Claude Agent SDK integration for Agentspan."""
from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Optional, Tuple


@dataclasses.dataclass
class ClaudeCodeAgent:
    """A Claude Agent SDK agent that runs as an Agentspan passthrough worker.

    Tiers:
      - Tier 1 (default): Full session durability + SSE event observability.
      - Tier 2 (conductor_subagents=True): Claude's internal Agent tool spawns real
        Conductor SUB_WORKFLOWs instead of in-process subagents.
      - Tier 3 (agentspan_routing=True): All tool execution routed through Conductor
        SIMPLE tasks via AgentspanTransport. Implies conductor_subagents=True.
    """

    name: str = "claude_agent"
    prompt: str = ""
    cwd: str = "."
    allowed_tools: List[str] = dataclasses.field(default_factory=list)
    max_turns: int = 100
    model: str = "claude-opus-4-6"
    max_tokens: int = 8192
    system_prompt: Optional[str] = None
    conductor_subagents: bool = False
    agentspan_routing: bool = False
    subagent_overrides: Dict[str, Any] = dataclasses.field(default_factory=dict)


def serialize_claude(agent: ClaudeCodeAgent) -> Tuple[Dict[str, Any], List]:
    """Serialize a ClaudeCodeAgent to (raw_config, [WorkerInfo]).

    Returns func=None in WorkerInfo — filled later by _build_passthrough_func().
    Follows the same pattern as serialize_langgraph().
    """
    from agentspan.agents.frameworks.serializer import WorkerInfo

    worker_name = f"_fw_claude_{agent.name}"
    raw_config = {
        "_worker_name": worker_name,
        "cwd": agent.cwd,
        "allowed_tools": agent.allowed_tools,
        "max_turns": agent.max_turns,
        "model": agent.model,
        "max_tokens": agent.max_tokens,
        "system_prompt": agent.system_prompt,
        "conductor_subagents": agent.conductor_subagents,
        "agentspan_routing": agent.agentspan_routing,
        "subagent_overrides": agent.subagent_overrides,
    }
    worker = WorkerInfo(
        name=worker_name,
        description=f"Claude Agent SDK passthrough worker ({agent.name})",
        input_schema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "cwd": {"type": "string"},
            },
        },
        func=None,
    )
    return raw_config, [worker]
