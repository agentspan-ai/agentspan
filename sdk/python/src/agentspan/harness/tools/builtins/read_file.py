# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""``read_file`` — bounded file read with optional line range.

Read-only and concurrency-safe. Honours the sandbox's ``check_path_read``.
Defaults to a max of 256 KB (per design §33 operational limits); larger
files require an explicit byte/line range.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional

from ..contract import Tool, ToolResult, ToolUseContext


_MAX_BYTES_DEFAULT = 256 * 1024
_DEFAULT_HEAD_LINES = 2000


class ReadFile(Tool[Dict[str, Any], str]):
    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "Read the contents of a file. Returns text content, optionally "
            "limited to a line range. Use offset/limit for large files."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file.",
                },
                "offset": {
                    "type": "integer",
                    "description": "Optional 1-based starting line number.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional max number of lines to return.",
                },
            },
            "required": ["path"],
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
    ) -> ToolResult[str]:
        path = _resolve(input["path"], context.cwd)
        offset = int(input.get("offset", 1))
        limit = int(input.get("limit", _DEFAULT_HEAD_LINES))

        sandbox = context.store.get("sandbox")
        if sandbox is not None:
            check = sandbox.check_path_read(path)
            if not check.allowed:
                return ToolResult.error(f"sandbox: {check.reason}")

        if not os.path.exists(path):
            return ToolResult.error(f"file not found: {path}")
        if os.path.isdir(path):
            return ToolResult.error(f"path is a directory: {path}")

        try:
            size = os.path.getsize(path)
        except OSError as exc:
            return ToolResult.error(f"stat failed: {exc}")

        if size > _MAX_BYTES_DEFAULT and offset == 1 and limit >= _DEFAULT_HEAD_LINES:
            return ToolResult.error(
                f"file is {size} bytes (>256KB); read with explicit "
                f"offset/limit or use search_text instead"
            )

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fp:
                lines = fp.readlines()
        except OSError as exc:
            return ToolResult.error(f"read failed: {exc}")

        if offset < 1:
            offset = 1
        start = offset - 1
        end = start + max(0, limit)
        slice_ = lines[start:end]

        # Number lines for model legibility.
        numbered = "".join(f"{i + start + 1:>6}\t{line}" for i, line in enumerate(slice_))
        if not numbered.endswith("\n"):
            numbered += "\n"

        truncated = end < len(lines)
        suffix = (
            f"\n[truncated; {len(lines) - end} more lines, "
            f"total {len(lines)} lines]"
            if truncated
            else ""
        )

        return ToolResult.ok(content=numbered + suffix, output=numbered + suffix)


def _resolve(path: str, cwd: str) -> str:
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(cwd, path))
