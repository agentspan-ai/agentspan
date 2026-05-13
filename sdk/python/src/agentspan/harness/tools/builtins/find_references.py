# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""``find_references`` — find all references to a symbol across files.

Word-boundary search. Not type-aware (would need an LSP). Good enough
for "where is this function called?" questions on real codebases.
Delegates to ripgrep when available; falls back to a Python walker.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
from typing import Any, Callable, Dict, List, Optional

from ..contract import Tool, ToolResult, ToolUseContext


class FindReferences(Tool[Dict[str, Any], List[Dict[str, Any]]]):
    @property
    def name(self) -> str:
        return "find_references"

    @property
    def description(self) -> str:
        return (
            "Find every reference to a symbol (function/class/variable name) "
            "across the workspace. Word-boundary match — won't match prefixes. "
            "Returns matches with file path, line number, and the matching line. "
            "Bounded to 200 matches; refine the symbol or use ``path`` to scope."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Symbol name to find."},
                "path": {
                    "type": "string",
                    "description": "Optional sub-path to scope the search. Defaults to cwd.",
                },
                "extensions": {
                    "type": "array",
                    "description": "Optional list of file extensions (e.g. ['.py']).",
                    "items": {"type": "string"},
                },
            },
            "required": ["symbol"],
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
    ) -> ToolResult[List[Dict[str, Any]]]:
        symbol = input["symbol"]
        if not symbol or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", symbol):
            return ToolResult.error(
                "symbol must be a single identifier (letters/digits/underscore)"
            )
        scope = input.get("path") or context.cwd
        if not os.path.isabs(scope):
            scope = os.path.normpath(os.path.join(context.cwd, scope))

        sandbox = context.store.get("sandbox")
        if sandbox is not None:
            check = sandbox.check_path_read(scope)
            if not check.allowed:
                return ToolResult.error(f"sandbox: {check.reason}")

        exts = input.get("extensions") or []
        if isinstance(exts, list):
            exts = [str(e).lower() for e in exts]
        else:
            exts = []

        rg = shutil.which("rg")
        results: List[Dict[str, Any]] = []
        if rg:
            args = [rg, "--word-regexp", "--line-number", "--no-heading", "--color=never"]
            for e in exts:
                args.extend(["-g", f"*{e}"])
            args.extend(["--", symbol, scope])
            try:
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()
            except OSError as exc:
                return ToolResult.error(f"rg failed: {exc}")
            for line in stdout.decode("utf-8", errors="replace").splitlines():
                # path:line:content
                parts = line.split(":", 2)
                if len(parts) < 3:
                    continue
                results.append({
                    "path": parts[0], "line": int(parts[1]) if parts[1].isdigit() else 0,
                    "match": parts[2],
                })
                if len(results) >= 200:
                    break
        else:
            pattern = re.compile(rf"\b{re.escape(symbol)}\b")
            for root, _dirs, files in os.walk(scope):
                # Skip common noise dirs.
                _dirs[:] = [d for d in _dirs if d not in (".git", "node_modules", "__pycache__", ".venv", "build", "target", "dist")]
                for f in files:
                    if exts and os.path.splitext(f)[1].lower() not in exts:
                        continue
                    full = os.path.join(root, f)
                    try:
                        with open(full, "r", encoding="utf-8", errors="replace") as fp:
                            for i, line in enumerate(fp, start=1):
                                if pattern.search(line):
                                    results.append({"path": full, "line": i, "match": line.rstrip()})
                                    if len(results) >= 200:
                                        break
                    except (OSError, UnicodeDecodeError):
                        continue
                    if len(results) >= 200:
                        break
                if len(results) >= 200:
                    break

        rendered = "\n".join(f"{r['path']}:{r['line']}: {r['match']}" for r in results)
        truncated = len(results) >= 200
        msg = f"{len(results)} references to {symbol!r}" + (
            " (capped at 200)" if truncated else ""
        )
        return ToolResult.ok(
            content=f"{msg}\n{rendered}" if rendered else msg,
            output=results,
        )
