# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""``patch_file`` — exact-text edit (Anthropic-style old_string/new_string)."""

from __future__ import annotations

import os
import tempfile
from typing import Any, Callable, Dict, List, Optional

from ..contract import Tool, ToolResult, ToolUseContext


class PatchFile(Tool[Dict[str, Any], str]):
    @property
    def name(self) -> str:
        return "patch_file"

    @property
    def description(self) -> str:
        return (
            "Apply exact-text replacements to a file. Each edit specifies "
            "old_string and new_string. old_string must match EXACTLY in "
            "the current file (whitespace-sensitive). Atomic write."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "edits": {
                    "type": "array",
                    "description": (
                        "List of edits, each with old_string and new_string."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "old_string": {"type": "string"},
                            "new_string": {"type": "string"},
                        },
                        "required": ["old_string", "new_string"],
                    },
                },
            },
            "required": ["path", "edits"],
        }

    def is_read_only(self, input: Dict[str, Any]) -> bool:
        return False

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
        edits = input.get("edits") or []

        if not isinstance(edits, list) or not edits:
            return ToolResult.error("edits must be a non-empty list")

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
            return ToolResult.error(f"path is a directory: {path}")

        try:
            with open(path, "r", encoding="utf-8") as fp:
                original = fp.read()
        except OSError as exc:
            return ToolResult.error(f"read failed: {exc}")

        current = original
        applied: List[str] = []
        for i, edit in enumerate(edits):
            if not isinstance(edit, dict):
                return ToolResult.error(f"edit {i}: not an object")
            old = edit.get("old_string")
            new = edit.get("new_string")
            if not isinstance(old, str) or not isinstance(new, str):
                return ToolResult.error(
                    f"edit {i}: old_string and new_string must be strings"
                )
            count = current.count(old)
            if count == 0:
                return ToolResult.error(
                    f"edit {i}: old_string not found in current file content. "
                    "The model should re-read the file before retrying."
                )
            if count > 1:
                return ToolResult.error(
                    f"edit {i}: old_string matches {count} places in the file; "
                    "include more surrounding context to make the match unique."
                )
            current = current.replace(old, new, 1)
            applied.append(f"edit {i}: replaced {len(old)} bytes → {len(new)} bytes")

        # Atomic write.
        try:
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=os.path.dirname(path) or context.cwd,
                prefix=".patch_file_",
                suffix=".tmp",
            )
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fp:
                fp.write(current)
                fp.flush()
                os.fsync(fp.fileno())
            os.replace(tmp_path, path)
        except OSError as exc:
            return ToolResult.error(f"write failed: {exc}")

        diff = _unified_diff(original, current, path)
        return ToolResult.ok(
            content=(
                f"Applied {len(applied)} edits to {path}.\n"
                + "\n".join(applied)
                + ("\n\n" + diff if diff else "")
            ),
            output=path,
        )


def _unified_diff(old: str, new: str, path: str, *, context: int = 3) -> str:
    """Return a small unified diff for the model to verify its change.

    Bounded at 200 lines to keep tool-result size in check; if larger,
    callers should re-read the file directly.
    """
    import difflib
    diff_lines = list(
        difflib.unified_diff(
            old.splitlines(keepends=False),
            new.splitlines(keepends=False),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            n=context,
            lineterm="",
        )
    )
    if not diff_lines:
        return ""
    if len(diff_lines) > 200:
        diff_lines = diff_lines[:200] + ["[diff truncated; use read_file to verify]"]
    return "\n".join(diff_lines)
