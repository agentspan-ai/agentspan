# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""``read_task_output`` — tail a registered task's output log."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from ..contract import Tool, ToolResult, ToolUseContext


class ReadTaskOutput(Tool[Dict[str, Any], Dict[str, Any]]):
    @property
    def name(self) -> str:
        return "read_task_output"

    @property
    def description(self) -> str:
        return (
            "Read output from a background task. Use the task_id returned "
            "by the spawning tool. ``offset`` lets you tail incrementally."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "offset": {"type": "integer", "description": "Default 0."},
                "max_bytes": {"type": "integer", "description": "Default 65536."},
            },
            "required": ["task_id"],
        }

    def is_read_only(self, input: Dict[str, Any]) -> bool:
        return True

    def is_concurrency_safe(self, input: Dict[str, Any]) -> bool:
        return True

    async def call(
        self,
        input: Dict[str, Any],
        context: ToolUseContext,
        parent_message: Any = None,
        on_progress: Optional[Callable[[Any], None]] = None,
    ) -> ToolResult[Dict[str, Any]]:
        tasks = context.store.get("task_manager")
        if tasks is None:
            return ToolResult.error("no task manager configured for this session")
        chunk = tasks.read_output(
            input["task_id"],
            offset=int(input.get("offset", 0)),
            max_bytes=int(input.get("max_bytes", 65536)),
        )
        if "error" in chunk:
            return ToolResult.error(chunk["error"])
        return ToolResult.ok(content=chunk, output=chunk)


class StopTask(Tool[Dict[str, Any], Dict[str, Any]]):
    @property
    def name(self) -> str:
        return "stop_task"

    @property
    def description(self) -> str:
        return "Kill a running background task by task_id."

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        }

    def is_read_only(self, input: Dict[str, Any]) -> bool:
        return False

    def is_destructive(self, input: Dict[str, Any]) -> bool:
        return True

    def is_concurrency_safe(self, input: Dict[str, Any]) -> bool:
        return False

    async def call(
        self,
        input: Dict[str, Any],
        context: ToolUseContext,
        parent_message: Any = None,
        on_progress: Optional[Callable[[Any], None]] = None,
    ) -> ToolResult[Dict[str, Any]]:
        tasks = context.store.get("task_manager")
        if tasks is None:
            return ToolResult.error("no task manager configured for this session")
        ok = await tasks.kill(input["task_id"])
        if not ok:
            return ToolResult.error(f"task {input['task_id']} not running or not found")
        state = tasks.get(input["task_id"])
        return ToolResult.ok(
            content={"task_id": state.id, "status": state.status},
            output={"task_id": state.id, "status": state.status},
        )
