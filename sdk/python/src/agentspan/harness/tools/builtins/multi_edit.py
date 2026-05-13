# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""``multi_edit`` — apply patches across multiple files in one tool call.

The model's per-turn budget makes single-file ``patch_file`` calls
expensive when a refactor touches N files. ``multi_edit`` accepts a list
of ``{path, edits: [{old_string, new_string}]}`` records and applies them
in order. All edits to one file are atomic per file (temp + rename).

Failure semantics: stop at the first file whose edits don't match. The
files already patched stay patched (best-effort, mirrors `git add`-style
incremental edits). Per-file results are returned so the model can
recover.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional

from ..contract import Tool, ToolResult, ToolUseContext
from .patch_file import _unified_diff


class MultiEdit(Tool[Dict[str, Any], List[Dict[str, Any]]]):
    @property
    def name(self) -> str:
        return "multi_edit"

    @property
    def description(self) -> str:
        return (
            "Apply edits to multiple files in one call. Each entry has "
            "{path, edits: [{old_string, new_string}, ...]}. Stops at the "
            "first failing file but keeps prior files' changes. Returns a "
            "per-file result list with diffs so you can verify."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "description": "List of {path, edits} records.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "edits": {
                                "type": "array",
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
                    },
                },
            },
            "required": ["files"],
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
    ) -> ToolResult[List[Dict[str, Any]]]:
        files = input.get("files") or []
        if not isinstance(files, list) or not files:
            return ToolResult.error("files must be a non-empty list")

        sandbox = context.store.get("sandbox")
        results: List[Dict[str, Any]] = []
        any_failure = False

        for entry in files:
            if not isinstance(entry, dict):
                results.append({"ok": False, "error": "entry not an object"})
                any_failure = True
                break
            path = entry.get("path")
            edits = entry.get("edits") or []
            if not isinstance(path, str) or not isinstance(edits, list) or not edits:
                results.append({
                    "path": path, "ok": False,
                    "error": "missing path or edits",
                })
                any_failure = True
                break

            full = path if os.path.isabs(path) else os.path.normpath(
                os.path.join(context.cwd, path)
            )

            if sandbox is not None:
                check = sandbox.check_path_write(full)
                if not check.allowed:
                    results.append({"path": full, "ok": False, "error": f"sandbox: {check.reason}"})
                    any_failure = True
                    break
            if not os.path.exists(full):
                results.append({"path": full, "ok": False, "error": "file not found"})
                any_failure = True
                break

            try:
                with open(full, "r", encoding="utf-8") as fp:
                    original = fp.read()
            except OSError as exc:
                results.append({"path": full, "ok": False, "error": f"read failed: {exc}"})
                any_failure = True
                break

            current = original
            applied = 0
            err: Optional[str] = None
            for j, ed in enumerate(edits):
                old = ed.get("old_string")
                new = ed.get("new_string")
                if not isinstance(old, str) or not isinstance(new, str):
                    err = f"edit {j}: old_string/new_string must be strings"
                    break
                count = current.count(old)
                if count == 0:
                    err = f"edit {j}: old_string not found"
                    break
                if count > 1:
                    err = f"edit {j}: old_string matches {count} places (need uniqueness)"
                    break
                current = current.replace(old, new, 1)
                applied += 1

            if err:
                results.append({"path": full, "ok": False, "applied": applied, "error": err})
                any_failure = True
                break

            try:
                _atomic_write(full, current)
            except OSError as exc:
                results.append({"path": full, "ok": False, "error": f"write failed: {exc}"})
                any_failure = True
                break

            diff = _unified_diff(original, current, path)
            results.append({
                "path": full, "ok": True, "applied": applied,
                "diff": diff[:4000] if diff else "",
            })

        ok_count = sum(1 for r in results if r.get("ok"))
        summary = (
            f"Applied edits to {ok_count}/{len(files)} files."
            + ("" if not any_failure else " Stopped on first failure.")
        )
        rendered = summary + "\n\n" + "\n\n".join(
            (f"--- {r.get('path')} ---\n"
             + (r.get("diff") or f"applied={r.get('applied', 0)}")
             if r.get("ok") else
             f"--- {r.get('path')} (FAILED) ---\n{r.get('error')}")
            for r in results
        )
        return ToolResult(
            output=results,
            content=rendered,
            is_error=any_failure,
        )


def _atomic_write(path: str, content: str) -> None:
    import tempfile
    parent = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=parent, prefix=".multi_edit_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            fp.write(content)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
        raise
