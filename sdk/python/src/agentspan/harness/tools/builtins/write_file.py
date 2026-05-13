# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""``write_file`` — atomic file write."""

from __future__ import annotations

import os
import tempfile
from typing import Any, Callable, Dict, Optional

from ..contract import Tool, ToolResult, ToolUseContext


class WriteFile(Tool[Dict[str, Any], str]):
    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return (
            "Create or overwrite a file with the given content. Atomic "
            "(writes to temp + rename). Creates parent directories if "
            "create_dirs=true (default false)."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "create_dirs": {"type": "boolean"},
            },
            "required": ["path", "content"],
        }

    def is_read_only(self, input: Dict[str, Any]) -> bool:
        return False

    def is_concurrency_safe(self, input: Dict[str, Any]) -> bool:
        return False  # writes serialize

    async def call(
        self,
        input: Dict[str, Any],
        context: ToolUseContext,
        parent_message: Any = None,
        on_progress: Optional[Callable[[Any], None]] = None,
    ) -> ToolResult[str]:
        path = input["path"]
        content = input["content"]
        create_dirs = bool(input.get("create_dirs", False))

        if not os.path.isabs(path):
            path = os.path.normpath(os.path.join(context.cwd, path))

        sandbox = context.store.get("sandbox")
        if sandbox is not None:
            check = sandbox.check_path_write(path)
            if not check.allowed:
                return ToolResult.error(f"sandbox: {check.reason}")

        parent = os.path.dirname(path)
        if parent and not os.path.exists(parent):
            if create_dirs:
                os.makedirs(parent, exist_ok=True)
            else:
                return ToolResult.error(
                    f"parent directory does not exist: {parent} "
                    "(set create_dirs=true to auto-create)"
                )

        # Snapshot the original (if any) into the session content_dir so the
        # model — or a hook / undo flow — can recover it. Best-effort.
        snapshot_path = None
        if os.path.exists(path) and not os.path.isdir(path):
            content_dir = context.store.get("content_dir")
            if content_dir:
                snap_dir = os.path.join(content_dir, "snapshots")
                os.makedirs(snap_dir, exist_ok=True)
                # Stable per-path filename so repeated writes overwrite the
                # snapshot for that path (only the immediately-prior version
                # is kept; deeper history lives in git).
                safe = path.replace(os.sep, "__").lstrip("__")
                snapshot_path = os.path.join(snap_dir, safe + ".before")
                try:
                    with open(path, "rb") as src, open(snapshot_path, "wb") as dst:
                        dst.write(src.read())
                except OSError:
                    snapshot_path = None

        # Atomic write: temp + rename.
        size = len(content.encode("utf-8"))
        try:
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=parent or context.cwd, prefix=".write_file_", suffix=".tmp"
            )
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as fp:
                    fp.write(content)
                    fp.flush()
                    os.fsync(fp.fileno())
                os.replace(tmp_path, path)
            except Exception:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise
        except OSError as exc:
            return ToolResult.error(f"write failed: {exc}")

        msg = f"Wrote {size} bytes to {path}"
        if snapshot_path:
            msg += f" (prior version snapshotted to {snapshot_path})"
        return ToolResult.ok(content=msg, output=path)
