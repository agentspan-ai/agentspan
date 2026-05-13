# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""``read_symbol`` — extract a single function/class body from a file.

Cuts the model's context cost dramatically vs. ``read_file`` on long
sources. Regex-based detection (matches ``file_outline``'s patterns).

Output is line-numbered with ~6 lines of leading context (decorators,
docstring opener) and capped at ``MAX_CHARS`` so a giant class doesn't
blow the budget.
"""

from __future__ import annotations

import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..contract import Tool, ToolResult, ToolUseContext
from .file_outline import _LANG_PATTERNS, _detect


MAX_CHARS = 15_000
LEADING_CONTEXT_LINES = 6


class ReadSymbol(Tool[Dict[str, Any], str]):
    @property
    def name(self) -> str:
        return "read_symbol"

    @property
    def description(self) -> str:
        return (
            "Read a specific function, class, method, type, or interface "
            "from a file by its declared name. Cheaper than read_file when "
            "you only need one symbol from a long source. Use file_outline "
            "first to discover symbol names. Returns line-numbered text."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "name": {"type": "string", "description": "Symbol name."},
            },
            "required": ["path", "name"],
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
        path = input["path"]
        sym = input["name"]
        if not os.path.isabs(path):
            path = os.path.normpath(os.path.join(context.cwd, path))

        sandbox = context.store.get("sandbox")
        if sandbox is not None:
            check = sandbox.check_path_read(path)
            if not check.allowed:
                return ToolResult.error(f"sandbox: {check.reason}")

        if not os.path.exists(path) or os.path.isdir(path):
            return ToolResult.error(f"file not found: {path}")

        patterns = _detect(path)
        if patterns is None:
            return ToolResult.error(
                f"read_symbol does not support extension {os.path.splitext(path)[1]}"
            )

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fp:
                lines = fp.readlines()
        except OSError as exc:
            return ToolResult.error(f"read failed: {exc}")

        rng = _find_symbol_range(lines, sym, path, patterns)
        if rng is None:
            return ToolResult.error(
                f"symbol {sym!r} not found in {path}. "
                "Try file_outline to list available symbols."
            )

        start, end = rng
        ctx_start = max(0, start - LEADING_CONTEXT_LINES)
        body_lines = lines[ctx_start:end]
        rendered = "".join(
            f"{ctx_start + i + 1:6d}\t{line}" for i, line in enumerate(body_lines)
        )
        truncated = False
        if len(rendered) > MAX_CHARS:
            rendered = rendered[:MAX_CHARS]
            truncated = True
            rendered += (
                f"\n... TRUNCATED ({end - start} body lines). "
                f"Use read_file with offset/limit for the full range."
            )
        return ToolResult.ok(
            content=rendered,
            output={"path": path, "name": sym, "start_line": start + 1, "end_line": end,
                    "truncated": truncated},
        )


def _find_symbol_range(
    lines: List[str],
    name: str,
    path: str,
    patterns: List[Tuple[re.Pattern, str]],
) -> Optional[Tuple[int, int]]:
    """Locate ``name``'s declaration and the line where its body ends.

    Returns (start_idx, end_idx_exclusive) zero-indexed. Python uses
    indentation; brace-paired languages count braces; Go uses braces too.
    """
    start_idx: Optional[int] = None
    for i, line in enumerate(lines):
        for regex, _label in patterns:
            m = regex.match(line)
            if not m:
                continue
            captured = m.group(m.lastindex or 1)
            if captured == name:
                start_idx = i
                break
        if start_idx is not None:
            break

    if start_idx is None:
        return None

    ext = os.path.splitext(path)[1].lower()
    if ext == ".py":
        def_indent = len(lines[start_idx]) - len(lines[start_idx].lstrip())
        end_idx = start_idx + 1
        while end_idx < len(lines):
            line = lines[end_idx]
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                indent = len(line) - len(line.lstrip())
                if indent <= def_indent:
                    break
            end_idx += 1
        while end_idx > start_idx + 1 and not lines[end_idx - 1].strip():
            end_idx -= 1
        return (start_idx, end_idx)

    # Brace-balanced languages.
    brace = 0
    seen_open = False
    end_idx = start_idx
    for i in range(start_idx, len(lines)):
        for ch in lines[i]:
            if ch == "{":
                brace += 1
                seen_open = True
            elif ch == "}":
                brace -= 1
        if seen_open and brace <= 0:
            end_idx = i + 1
            break
    else:
        end_idx = min(start_idx + 50, len(lines))
    return (start_idx, end_idx)
