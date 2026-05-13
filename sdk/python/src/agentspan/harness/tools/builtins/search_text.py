# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""``search_text`` — ripgrep-like text search over the workspace."""

from __future__ import annotations

import asyncio
import os
import shutil
from typing import Any, Callable, Dict, Optional

from ..contract import Tool, ToolResult, ToolUseContext


_MAX_RESULTS = 200


class SearchText(Tool[Dict[str, Any], str]):
    @property
    def name(self) -> str:
        return "search_text"

    @property
    def description(self) -> str:
        return (
            "Search file contents for a pattern. Uses ripgrep when available, "
            "falls back to a Python implementation. Returns matching lines "
            "with file:line numbers."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex (or fixed string with literal=true).",
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search; defaults to cwd.",
                },
                "literal": {
                    "type": "boolean",
                    "description": "Treat pattern as a literal string. Default false.",
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "Default false (smart-case behavior).",
                },
                "include": {
                    "type": "string",
                    "description": "Optional file glob filter, e.g. '*.py'.",
                },
            },
            "required": ["pattern"],
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
        pattern = input["pattern"]
        path = input.get("path", context.cwd)
        if not os.path.isabs(path):
            path = os.path.normpath(os.path.join(context.cwd, path))
        literal = bool(input.get("literal", False))
        case_sensitive = bool(input.get("case_sensitive", False))
        include = input.get("include")

        sandbox = context.store.get("sandbox")
        if sandbox is not None:
            check = sandbox.check_path_read(path)
            if not check.allowed:
                return ToolResult.error(f"sandbox: {check.reason}")
        if not os.path.exists(path):
            return ToolResult.error(f"path not found: {path}")

        if shutil.which("rg"):
            content = await self._rg(pattern, path, literal, case_sensitive, include)
        else:
            content = self._fallback(pattern, path, literal, case_sensitive, include)

        return ToolResult.ok(content=content, output=content)

    async def _rg(
        self,
        pattern: str,
        path: str,
        literal: bool,
        case_sensitive: bool,
        include: Optional[str],
    ) -> str:
        cmd = [
            "rg",
            "--no-heading",
            "--with-filename",
            "--line-number",
            "--max-count",
            str(_MAX_RESULTS),
        ]
        if literal:
            cmd.append("-F")
        if not case_sensitive:
            cmd.append("-i")
        if include:
            cmd.extend(["-g", include])
        cmd.extend(["--", pattern, path])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        text = stdout.decode("utf-8", errors="replace")
        lines = text.splitlines()
        if len(lines) >= _MAX_RESULTS:
            lines = lines[:_MAX_RESULTS]
            lines.append(f"[truncated at {_MAX_RESULTS} matches]")
        return "\n".join(lines) if lines else "[no matches]"

    def _fallback(
        self,
        pattern: str,
        path: str,
        literal: bool,
        case_sensitive: bool,
        include: Optional[str],
    ) -> str:
        import fnmatch
        import re

        if literal:
            regex = re.compile(re.escape(pattern), 0 if case_sensitive else re.IGNORECASE)
        else:
            regex = re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)

        results = []
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fn in filenames:
                if include and not fnmatch.fnmatch(fn, include):
                    continue
                full = os.path.join(dirpath, fn)
                try:
                    with open(full, "r", encoding="utf-8", errors="replace") as fp:
                        for i, line in enumerate(fp, start=1):
                            if regex.search(line):
                                rel = os.path.relpath(full, path)
                                results.append(f"{rel}:{i}:{line.rstrip()}")
                                if len(results) >= _MAX_RESULTS:
                                    results.append(f"[truncated at {_MAX_RESULTS} matches]")
                                    return "\n".join(results)
                except OSError:
                    continue
        return "\n".join(results) if results else "[no matches]"
