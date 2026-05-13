# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""``list_files`` — enumerate files by glob or directory."""

from __future__ import annotations

import fnmatch
import os
from typing import Any, Callable, Dict, List, Optional

from ..contract import Tool, ToolResult, ToolUseContext


class ListFiles(Tool[Dict[str, Any], List[str]]):
    @property
    def name(self) -> str:
        return "list_files"

    @property
    def description(self) -> str:
        return (
            "List files in a directory or matching a glob pattern. "
            "Recursive by default. Hidden files excluded unless include_hidden=true."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path; defaults to cwd.",
                },
                "pattern": {
                    "type": "string",
                    "description": "Optional glob pattern, e.g. '**/*.py'.",
                },
                "include_hidden": {
                    "type": "boolean",
                    "description": "Include dotfiles. Default false.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Cap result count. Default 1000.",
                },
            },
            "required": [],
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
    ) -> ToolResult[List[str]]:
        root = input.get("path", context.cwd)
        if not os.path.isabs(root):
            root = os.path.normpath(os.path.join(context.cwd, root))
        pattern = input.get("pattern")
        include_hidden = bool(input.get("include_hidden", False))
        max_results = int(input.get("max_results", 1000))

        sandbox = context.store.get("sandbox")
        if sandbox is not None:
            check = sandbox.check_path_read(root)
            if not check.allowed:
                return ToolResult.error(f"sandbox: {check.reason}")

        if not os.path.isdir(root):
            return ToolResult.error(f"not a directory: {root}")

        results: List[str] = []
        for dirpath, dirnames, filenames in os.walk(root):
            # Skip hidden subdirectories unless requested.
            if not include_hidden:
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fn in filenames:
                if not include_hidden and fn.startswith("."):
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, root)
                if pattern and not fnmatch.fnmatch(rel, pattern):
                    continue
                results.append(rel)
                if len(results) >= max_results:
                    break
            if len(results) >= max_results:
                break

        results.sort()
        truncated_msg = (
            f"\n[truncated at {max_results}]" if len(results) >= max_results else ""
        )
        content = "\n".join(results) + truncated_msg if results else "[no matches]"
        return ToolResult.ok(content=content, output=results)
