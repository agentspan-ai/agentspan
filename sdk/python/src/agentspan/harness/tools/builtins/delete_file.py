# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""``delete_file`` — destructive file removal."""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional

from ..contract import Tool, ToolResult, ToolUseContext


class DeleteFile(Tool[Dict[str, Any], str]):
    @property
    def name(self) -> str:
        return "delete_file"

    @property
    def description(self) -> str:
        return "Delete a file. Destructive; refuses to delete directories."

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
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
    ) -> ToolResult[str]:
        path = input["path"]
        if not os.path.isabs(path):
            path = os.path.normpath(os.path.join(context.cwd, path))

        sandbox = context.store.get("sandbox")
        if sandbox is not None:
            check = sandbox.check_path_write(path)
            if not check.allowed:
                return ToolResult.error(f"sandbox: {check.reason}")

        if not os.path.exists(path):
            return ToolResult.error(f"file not found: {path}")
        if os.path.isdir(path):
            return ToolResult.error(
                f"refusing to delete directory: {path} (use shell with explicit allow)"
            )
        try:
            os.unlink(path)
        except OSError as exc:
            return ToolResult.error(f"delete failed: {exc}")
        return ToolResult.ok(content=f"Deleted {path}", output=path)
