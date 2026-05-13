# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""``file_outline`` — language-aware outline of declarations.

Regex-based, deliberately language-agnostic. The point isn't perfect
parsing; it's letting the model see the *shape* of a file (which
classes/functions/methods exist, at what line) without paying tokens
for the bodies. For Python / TypeScript / Java / Go the regexes catch
the common cases. Anything more requires real LSP integration, which
is post-v1.
"""

from __future__ import annotations

import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..contract import Tool, ToolResult, ToolUseContext


# (language, file_extensions, list of (regex, label) pairs)
_LANG_PATTERNS: List[Tuple[str, Tuple[str, ...], List[Tuple[re.Pattern, str]]]] = [
    (
        "python", (".py",),
        [
            (re.compile(r"^\s*class\s+(\w+)"), "class"),
            (re.compile(r"^\s*(async\s+)?def\s+(\w+)"), "def"),
        ],
    ),
    (
        "javascript", (".js", ".jsx", ".mjs", ".cjs"),
        [
            (re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)"), "function"),
            (re.compile(r"^\s*(?:export\s+)?class\s+(\w+)"), "class"),
            (re.compile(r"^\s*(?:export\s+)?const\s+(\w+)\s*="), "const"),
        ],
    ),
    (
        "typescript", (".ts", ".tsx"),
        [
            (re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)"), "function"),
            (re.compile(r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+(\w+)"), "class"),
            (re.compile(r"^\s*(?:export\s+)?interface\s+(\w+)"), "interface"),
            (re.compile(r"^\s*(?:export\s+)?type\s+(\w+)"), "type"),
            (re.compile(r"^\s*(?:export\s+)?enum\s+(\w+)"), "enum"),
        ],
    ),
    (
        "java", (".java",),
        [
            (re.compile(r"^\s*(?:public|private|protected)?\s*(?:abstract\s+|final\s+|static\s+)*class\s+(\w+)"), "class"),
            (re.compile(r"^\s*(?:public|private|protected)?\s*interface\s+(\w+)"), "interface"),
            (re.compile(r"^\s*(?:public|private|protected)?\s*(?:static\s+|final\s+|abstract\s+)*[\w<>\[\]]+\s+(\w+)\s*\("), "method"),
        ],
    ),
    (
        "go", (".go",),
        [
            (re.compile(r"^func\s+(?:\([^)]+\)\s+)?(\w+)"), "func"),
            (re.compile(r"^type\s+(\w+)\s+(?:struct|interface)"), "type"),
        ],
    ),
]


def _detect(path: str) -> Optional[List[Tuple[re.Pattern, str]]]:
    ext = os.path.splitext(path)[1].lower()
    for _name, exts, patterns in _LANG_PATTERNS:
        if ext in exts:
            return patterns
    return None


class FileOutline(Tool[Dict[str, Any], List[Dict[str, Any]]]):
    @property
    def name(self) -> str:
        return "file_outline"

    @property
    def description(self) -> str:
        return (
            "Show declarations (classes, functions, methods, interfaces, types) "
            "in a file with their line numbers. Supports Python, JS/TS, Java, Go. "
            "Use this before read_file to navigate large files."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {"path": {"type": "string"}},
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
    ) -> ToolResult[List[Dict[str, Any]]]:
        path = input["path"]
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
                f"file_outline does not support this file extension: {os.path.splitext(path)[1]}"
            )

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fp:
                lines = fp.readlines()
        except OSError as exc:
            return ToolResult.error(f"read failed: {exc}")

        out: List[Dict[str, Any]] = []
        for i, line in enumerate(lines, start=1):
            for regex, label in patterns:
                m = regex.match(line)
                if m:
                    name = m.group(m.lastindex or 1)
                    if name:
                        out.append({"line": i, "kind": label, "name": name})
                    break

        rendered = "\n".join(f"L{e['line']:>5}  {e['kind']:<10} {e['name']}" for e in out)
        return ToolResult.ok(
            content=f"Outline of {path} ({len(out)} declarations):\n{rendered}",
            output=out,
        )
