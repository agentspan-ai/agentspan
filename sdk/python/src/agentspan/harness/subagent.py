# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Default subagent factory for ``spawn_agent``.

The ``spawn_agent`` tool delegates child-runtime construction to a
factory (so embedders can plug in their own scoping / model-selection /
prompt logic). Most users want the obvious default: child inherits the
parent's provider, model, sandbox, and shared store; the parent's tool
list is filtered by the requested ``allowed_tools``; permissions are
narrowed to the same allowlist; cwd switches to the worktree path when
``isolation="worktree"`` was requested.

This file ships that default. Use it directly:

    SpawnAgent(factory=default_subagent_factory)
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from .permission.engine import PermissionEngine
from .permission.rules import PermissionRule, RuleSource
from .runtime import HarnessConfig, HarnessRuntime
from .tools.contract import Tool, ToolUseContext


def default_subagent_factory(
    context: ToolUseContext,
    input: Dict[str, Any],
) -> HarnessRuntime:
    """Build a child ``HarnessRuntime`` from the parent's session_store.

    Reads from ``context.store``:
      * ``harness`` — parent HarnessRuntime (for inheriting provider/model/sandbox)
      * ``shared_store_dir`` — passed to the child so they share the kv store
      * ``_worktree_path`` — when ``isolation="worktree"``, this overrides cwd

    Reads from ``input``:
      * ``allowed_tools`` — tool name allowlist; default = all parent tools
      * ``model`` — override LLM model; default = parent's
      * ``system`` — override system prompt; default = parent's
      * ``max_turns`` — override; default = parent's
    """
    parent: HarnessRuntime = context.store.get("harness")
    if parent is None:
        raise RuntimeError("default_subagent_factory: no parent harness in context.store")

    parent_cfg = parent.config

    allowed = input.get("allowed_tools")
    parent_tools: List[Tool] = list(parent_cfg.tools)
    if allowed:
        allowed_set = set(allowed)
        child_tools = [t for t in parent_tools if t.name in allowed_set]
        # Permissions: narrow to allowlist explicitly (allow rules per name).
        rules = [
            PermissionRule(
                source=RuleSource.PROJECT, behavior="allow", tool_name=name,
            )
            for name in allowed_set
        ]
        permission = PermissionEngine(rules=rules, mode=parent_cfg.permission_mode)
    else:
        child_tools = parent_tools
        permission = parent_cfg.permission_engine or PermissionEngine(mode=parent_cfg.permission_mode)

    cwd = input.get("_worktree_path") or parent_cfg.cwd
    child_session_id = f"sub_{uuid.uuid4().hex[:12]}"

    config = HarnessConfig(
        model=input.get("model") or parent_cfg.model,
        tools=child_tools,
        cwd=cwd,
        sandbox=parent_cfg.sandbox,
        permission_engine=permission,
        permission_mode=parent_cfg.permission_mode,
        system=input.get("system") or parent_cfg.system,
        max_turns=int(input.get("max_turns", parent_cfg.max_turns)),
        max_tokens=parent_cfg.max_tokens,
        temperature=parent_cfg.temperature,
        session_id=child_session_id,
        # Share the kv store directory so parent + child see the same view.
        shared_store_dir=parent.session_store.get("shared_store_dir"),
        # Don't propagate worktree_repo — only the parent owns the manager.
    )
    return HarnessRuntime(config)
