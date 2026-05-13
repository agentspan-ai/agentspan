# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""``spawn_agent`` — delegate scoped work to a child harness.

The child runs as its own ``HarnessRuntime`` with explicitly-scoped tools
and permission rules. Two modes:

  * ``run_in_background=False`` (default) — parent awaits completion and
    receives the child's structured output (or final assistant text).
  * ``run_in_background=True`` — registered with the TaskManager and a
    task_id is returned immediately. The parent polls/notifies via
    ``read_task_output`` and ``list`` task state.

Optional ``isolation="worktree"`` creates a git worktree under the
session's WorktreeManager and runs the child with cwd set to the
worktree path. On completion, the worktree is kept (with path/branch
returned to parent) or cleaned up depending on ``has_changes``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

from ..contract import Tool, ToolResult, ToolUseContext

logger = logging.getLogger("agentspan.harness.tools.spawn_agent")


class SpawnAgent(Tool[Dict[str, Any], Dict[str, Any]]):
    """Spawn a subagent.

    Construction takes a ``factory`` callable that, given the parent's
    context + the spawn input, returns a constructed child HarnessRuntime.
    The factory is responsible for:

      * Scoping the child's tool list (``allowed_tools`` filter)
      * Scoping the child's permission rules
      * Setting child cwd to the worktree path when isolation is requested
      * Building the child's system prompt

    This separation keeps the tool implementation generic — different
    embeddings (issue-fixer harness vs. CLI harness) can supply their own
    factory without subclassing.
    """

    def __init__(
        self,
        *,
        factory: Callable[
            [ToolUseContext, Dict[str, Any]],
            Any,  # returns a HarnessRuntime
        ],
    ) -> None:
        self._factory = factory

    @property
    def name(self) -> str:
        return "spawn_agent"

    @property
    def description(self) -> str:
        return (
            "Delegate a scoped task to a subagent. The subagent runs as a "
            "child harness with its own tools and permissions. Set "
            "run_in_background=true to get a task_id back immediately and "
            "poll output via read_task_output. Set isolation='worktree' "
            "for parallel-safe file edits in a git worktree."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Short description of the work being delegated.",
                },
                "prompt": {
                    "type": "string",
                    "description": "Initial prompt sent to the subagent.",
                },
                "agent_type": {
                    "type": "string",
                    "description": "Optional named agent profile (factory-defined).",
                },
                "model": {
                    "type": "string",
                    "description": "Override LLM model for the subagent.",
                },
                "allowed_tools": {
                    "type": "array",
                    "description": "List of tool names the subagent may use.",
                    "items": {"type": "string"},
                },
                "isolation": {
                    "type": "string",
                    "description": "'same_workspace' (default) | 'worktree'",
                },
                "run_in_background": {
                    "type": "boolean",
                    "description": "Default false. True returns task_id immediately.",
                },
            },
            "required": ["description", "prompt"],
        }

    def is_read_only(self, input: Dict[str, Any]) -> bool:
        return False

    def is_concurrency_safe(self, input: Dict[str, Any]) -> bool:
        # Spawning is exclusive at the moment of registration; the actual
        # subagent runs independently.
        return False

    async def call(
        self,
        input: Dict[str, Any],
        context: ToolUseContext,
        parent_message: Any = None,
        on_progress: Optional[Callable[[Any], None]] = None,
    ) -> ToolResult[Dict[str, Any]]:
        run_in_background = bool(input.get("run_in_background", False))
        description = input.get("description", "")
        prompt = input.get("prompt", "")

        # If isolation="worktree", create the worktree up-front and pass
        # its path to the factory via the input dict so the factory can
        # set the child runtime's cwd accordingly.
        worktree_info = None
        if input.get("isolation") == "worktree":
            wm = context.store.get("worktree_manager")
            if wm is None:
                return ToolResult.error(
                    "isolation='worktree' requires a worktree_manager on the parent session "
                    "(set HarnessConfig.worktree_repo)"
                )
            try:
                worktree_info = await wm.create()
            except Exception as exc:  # noqa: BLE001
                logger.exception("worktree create failed")
                return ToolResult.error(f"worktree create failed: {exc}")
            input = {**input, "_worktree_path": worktree_info.path,
                     "_worktree_branch": worktree_info.branch}

        try:
            child_runtime = self._factory(context, input)
        except Exception as exc:  # noqa: BLE001
            logger.exception("spawn_agent factory raised")
            if worktree_info is not None:
                wm = context.store.get("worktree_manager")
                if wm is not None:
                    try:
                        await wm.cleanup(worktree_info.path, force=True)
                    except Exception:  # noqa: BLE001
                        pass
            return ToolResult.error(f"factory failed: {exc}")

        if run_in_background:
            # Register with the task manager and return immediately.
            tasks = context.store.get("task_manager")
            if tasks is None:
                return ToolResult.error("background spawn requires a task manager")

            async def _runner(abort: asyncio.Event) -> Dict[str, Any]:
                final_text: List[str] = []
                final_structured: Optional[Dict[str, Any]] = None
                async for event in child_runtime.submit(prompt):
                    if abort.is_set():
                        child_runtime.abort()
                    text = getattr(event, "content", None)
                    if text and getattr(event, "type", "") in ("message", "done"):
                        final_text.append(text)
                if "structured_output" in child_runtime.session_store:
                    final_structured = child_runtime.session_store["structured_output"]
                child_runtime.close()
                return {
                    "session_id": child_runtime.session_id,
                    "execution_id": child_runtime.last_execution_id or "",
                    "final_text": "\n".join(final_text),
                    "structured": final_structured,
                }

            state = await tasks.register(
                task_type="agent",
                description=description,
                runner=_runner,
            )
            return ToolResult.ok(
                content={
                    "task_id": state.id,
                    "session_id": child_runtime.session_id,
                    "description": description,
                },
                output={"task_id": state.id},
            )

        # Foreground: run to completion.
        final_text: List[str] = []
        try:
            async for event in child_runtime.submit(prompt):
                text = getattr(event, "content", None)
                if text and getattr(event, "type", "") in ("message", "done"):
                    final_text.append(text)
        finally:
            structured = child_runtime.session_store.get("structured_output")
            execution_id = child_runtime.last_execution_id or ""
            child_session_id = child_runtime.session_id
            child_runtime.close()

        result = {
            "session_id": child_session_id,
            "execution_id": execution_id,
            "final_text": "\n".join(final_text),
            "structured": structured,
        }
        if worktree_info is not None:
            result["worktree_path"] = worktree_info.path
            result["worktree_branch"] = worktree_info.branch
        return ToolResult.ok(content=result, output=result)
