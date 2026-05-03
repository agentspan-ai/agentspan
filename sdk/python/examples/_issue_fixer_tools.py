# sdk/python/examples/_issue_fixer_tools.py
"""Reusable @tool functions for the Issue Fixer Agent.

All tools operate relative to a shared working directory set via
``set_working_dir(path)`` before any agent runs. This is typically a
temp folder where the target repo is cloned.

Provides tools organized into 5 categories:
- File operations (read_file bounded, read_symbol, write, edit, patch, list, outline)
- Search & navigation (glob, grep, symbols, references)
- Git (diff, log, blame)
- Build & test (lint, build, unit tests, e2e)
- Contextbook (write, read, summary)

Design: search-first discovery, bounded reads, per-tool output budgets.
Agents use search tools to find what they need, then read_symbol or
read_file(path, start, end) for targeted code reading. No full-file dumps.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from agentspan.agents import tool
from agentspan.agents.tool import ToolContext

# ── Agent-boundary isolation ──────────────────────────────────
#
# Tools are shared across agents in the same worker process.
# Dedup caches (file hashes, grep results) must be reset when a
# new agent starts — otherwise agent B gets "unchanged" for content
# that agent A read but agent B never saw.
#
# We detect agent boundaries by tracking execution_id from ToolContext.
# Each agent runs as a separate Conductor workflow with its own ID.
# When the execution_id changes → new agent → clear all caches.
# This is systematic — no developer discipline required.

_last_execution_id: str = ""


def _ensure_agent_boundary(context: ToolContext | None) -> None:
    """Clear all dedup caches when the calling agent changes.

    Detects agent boundaries via ToolContext.execution_id, which maps
    to the Conductor workflow_instance_id. Each agent in a pipeline
    runs as a separate sub-workflow with its own ID.
    """
    global _last_execution_id
    if context is None:
        return
    eid = context.execution_id
    if not eid:
        return
    if eid != _last_execution_id:
        _last_execution_id = eid
        _file_read_hashes.clear()
        _grep_cache.clear()
        _symbol_read_hashes.clear()
        _read_file_cache.clear()


# ── Working directory ──────────────────────────────────────────

_WORKING_DIR: str = ""


def set_working_dir(path: str) -> None:
    """Set the shared working directory for all tools.

    Must be called before any agent runs. Typically a temp folder where
    the target repo will be cloned into by the Issue Analyst.
    """
    global _WORKING_DIR, _last_execution_id
    _WORKING_DIR = str(path)
    os.makedirs(_WORKING_DIR, exist_ok=True)
    _last_execution_id = ""
    _file_read_hashes.clear()
    _grep_cache.clear()
    _symbol_read_hashes.clear()
    _read_file_cache.clear()


def get_working_dir() -> str:
    """Return the current working directory."""
    return _WORKING_DIR


def _resolve(path: str) -> Path:
    """Resolve a path relative to the working directory.

    Absolute paths are returned as-is. Relative paths are resolved
    against _WORKING_DIR. If _WORKING_DIR is unset, resolves against CWD.
    """
    p = Path(path)
    if p.is_absolute():
        return p
    base = Path(_WORKING_DIR) if _WORKING_DIR else Path.cwd()
    return base / p


def _cwd() -> str:
    """Return the working directory for subprocess calls."""
    return _WORKING_DIR or None


# ── Limits ─────────────────────────────────────────────────────

_MAX_FILE_BYTES = 500_000  # 500 KB
_MAX_OUTPUT_LINES = 200  # truncate long outputs
_MAX_COMMAND_OUTPUT = 16_000  # chars for command output
_DEFAULT_TIMEOUT = 120  # seconds for shell commands
E2E_TOOL_TIMEOUT = 5400  # 90 min — full e2e suite with margin

# Per-tool output budgets (harness design: every tool has maxResultSizeChars)
_MAX_READ_FILE_CHARS = 60_000  # read_file bounded range output
_MAX_READ_SYMBOL_CHARS = 15_000  # read_symbol output
_MAX_GREP_CHARS = 20_000  # grep_search output
_MAX_SEARCH_SYMBOLS_CHARS = 20_000  # search_symbols output
_MAX_OUTLINE_CHARS = 10_000  # file_outline output
_MAX_LIST_DIR_CHARS = 10_000  # list_directory output

# Dedup: track file reads to block redundant re-reads
_file_read_hashes: dict[str, int] = {}  # resolved path -> content hash
_symbol_read_hashes: dict[str, int] = {}  # "resolved_path:symbol" -> content hash
_read_file_cache: dict[str, tuple[int, int]] = {}  # resolved path -> (size_bytes, line_count)

# Auto-discovered at runtime by _discover_repo_conventions()
_BASE_BRANCH: str = "main"
_REPO_COMMANDS: dict[str, str] = {}  # keys: lint, build, test


# ── File Operations ──────────────────────────────────────────


@tool
def read_file(path: str, context: ToolContext = None) -> str:
    """Read a file. Always returns the FULL file content with line numbers.
    For targeted code reading, use read_symbol() instead.
    Paths are relative to the repo working directory."""
    _ensure_agent_boundary(context)
    target = _resolve(path)
    if not target.exists():
        return f"Error: {path!r} does not exist."
    if target.is_dir():
        return f"Error: {path!r} is a directory. Use list_directory instead."
    size = target.stat().st_size
    if size > _MAX_FILE_BYTES:
        return f"Error: {path!r} is {size:,} bytes (limit {_MAX_FILE_BYTES:,}). Use grep_search to find specific content."
    abs_path = str(target.resolve())
    if abs_path in _read_file_cache:
        cached_size, cached_lines = _read_file_cache[abs_path]
        return (
            f"Already returned on a previous call ({cached_size:,} bytes, {cached_lines:,} lines). "
            f"Content is in your conversation history — use it directly. "
            f"Do NOT call read_file on this path again."
        )
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        _read_file_cache[abs_path] = (size, len(lines))
        numbered = [f"{i + 1:6d}\t{line}" for i, line in enumerate(lines)]
        result = "\n".join(numbered)
        if len(result) > _MAX_READ_FILE_CHARS:
            result = result[:_MAX_READ_FILE_CHARS]
            result += f"\n... TRUNCATED at {_MAX_READ_FILE_CHARS:,} chars. Use read_symbol() for targeted reading."
        return result
    except Exception as exc:
        return f"Error reading {path!r}: {exc}"


@tool
def write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent directories as needed. Overwrites existing files.
    Paths are relative to the repo working directory."""
    target = _resolve(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        _grep_cache.clear()  # file changed — invalidate grep cache
        _file_read_hashes.pop(str(target.resolve()), None)
        _read_file_cache.pop(str(target.resolve()), None)
        return f"Wrote {len(content):,} bytes to {path!r}."
    except Exception as exc:
        return f"Error writing {path!r}: {exc}"


@tool
def edit_file(path: str, old_string: str, new_string: str) -> str:
    """Replace exact text in a file. Fails if old_string is not found or matches more than once.
    Paths are relative to the repo working directory."""
    target = _resolve(path)
    if not target.exists():
        return f"Error: {path!r} does not exist."
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        count = content.count(old_string)
        if count == 0:
            return f"Error: old_string not found in {path!r}."
        if count > 1:
            return f"Error: old_string found {count} times in {path!r}. Provide more context to make it unique."
        new_content = content.replace(old_string, new_string, 1)
        target.write_text(new_content, encoding="utf-8")
        _grep_cache.clear()  # file changed — invalidate grep cache
        _file_read_hashes.pop(str(target.resolve()), None)
        _read_file_cache.pop(str(target.resolve()), None)
        return (
            f"Edited {path!r}: replaced 1 occurrence ({len(old_string)} → {len(new_string)} chars)."
        )
    except Exception as exc:
        return f"Error editing {path!r}: {exc}"


@tool
def apply_patch(patch: str) -> str:
    """Apply a unified diff patch to the repo. Returns success/failure details."""
    try:
        proc = subprocess.run(
            ["git", "apply", "--check", "-"],
            input=patch,
            capture_output=True,
            text=True,
            cwd=_cwd(),
            timeout=30,
        )
        if proc.returncode != 0:
            return f"Error: patch would not apply cleanly:\n{proc.stderr.strip()}"
        proc = subprocess.run(
            ["git", "apply", "-"],
            input=patch,
            capture_output=True,
            text=True,
            cwd=_cwd(),
            timeout=30,
        )
        if proc.returncode == 0:
            _read_file_cache.clear()
            _grep_cache.clear()
            return "Patch applied successfully."
        return f"Error applying patch:\n{proc.stderr.strip()}"
    except Exception as exc:
        return f"Error: {exc}"


@tool
def list_directory(path: str = ".", max_depth: int = 2) -> str:
    """List directory contents in tree format up to max_depth levels deep.
    Paths are relative to the repo working directory."""
    target = _resolve(path)
    if not target.exists():
        return f"Error: {path!r} does not exist."
    if not target.is_dir():
        return f"Error: {path!r} is not a directory."

    lines = [str(target) + "/"]

    def _walk(dir_path: Path, prefix: str, depth: int):
        if depth > max_depth:
            return
        try:
            entries = sorted(dir_path.iterdir(), key=lambda p: (p.is_file(), p.name))
        except PermissionError:
            return
        entries = [
            e
            for e in entries
            if not e.name.startswith(".")
            and e.name not in ("node_modules", "__pycache__", ".git", "dist", "build")
        ]
        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            if entry.is_dir():
                lines.append(f"{prefix}{connector}{entry.name}/")
                extension = "    " if is_last else "│   "
                _walk(entry, prefix + extension, depth + 1)
            else:
                size = entry.stat().st_size
                lines.append(f"{prefix}{connector}{entry.name}  ({size:,}b)")

    _walk(target, "", 1)
    if len(lines) > _MAX_OUTPUT_LINES:
        lines = lines[:_MAX_OUTPUT_LINES]
        lines.append(f"... (truncated at {_MAX_OUTPUT_LINES} entries)")
    result = "\n".join(lines)
    if len(result) > _MAX_LIST_DIR_CHARS:
        result = result[:_MAX_LIST_DIR_CHARS] + "\n... TRUNCATED. Use a deeper path or glob_find."
    return result


# Language-specific regex patterns for definition extraction
_OUTLINE_PATTERNS = {
    ".py": [
        (r"^\s*(class\s+\w+)", "class"),
        (r"^\s*((?:async\s+)?def\s+\w+\s*\([^)]*\))", "function"),
    ],
    ".go": [
        (r"^(func\s+(?:\([^)]+\)\s+)?\w+\s*\([^)]*\))", "function"),
        (r"^(type\s+\w+\s+struct\s*\{)", "struct"),
        (r"^(type\s+\w+\s+interface\s*\{)", "interface"),
    ],
    ".java": [
        (r"^\s*(?:public|private|protected)?\s*(class\s+\w+)", "class"),
        (r"^\s*(?:public|private|protected)?\s*(interface\s+\w+)", "interface"),
        (
            r"^\s*(?:public|private|protected|static|\s)*\s+(\w+\s+\w+\s*\([^)]*\))\s*(?:\{|throws)",
            "method",
        ),
    ],
    ".ts": [
        (r"^\s*(?:export\s+)?(?:abstract\s+)?(class\s+\w+)", "class"),
        (r"^\s*(?:export\s+)?(interface\s+\w+)", "interface"),
        (r"^\s*(?:export\s+)?(type\s+\w+)", "type"),
        (r"^\s*(?:export\s+)?(?:async\s+)?(function\s+\w+\s*\([^)]*\))", "function"),
        (r"^\s*(?:export\s+)?const\s+(\w+)\s*=\s*(?:\([^)]*\)|[^=])*=>", "arrow"),
    ],
    ".tsx": None,  # same as .ts, handled below
    ".jsx": None,  # same as .ts
}


def _file_outline_impl(target: Path) -> str:
    """Extract file outline (classes, functions, methods) — shared implementation."""
    ext = target.suffix
    patterns = _OUTLINE_PATTERNS.get(ext)
    if patterns is None and ext in (".tsx", ".jsx"):
        patterns = _OUTLINE_PATTERNS[".ts"]
    if not patterns:
        return ""
    try:
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        results = []
        for lineno, line in enumerate(lines, 1):
            for pattern, kind in patterns:
                m = re.match(pattern, line)
                if m:
                    results.append(f"{lineno:6d} | {kind:10s} | {m.group(1).strip()}")
                    break
        return "\n".join(results) if results else ""
    except Exception:
        return ""


@tool
def file_outline(path: str) -> str:
    """Show the structure of a file: classes, functions, methods, interfaces.
    Works across Python, Go, Java, TypeScript, and React.
    Paths are relative to the repo working directory."""
    target = _resolve(path)
    if not target.exists():
        return f"Error: {path!r} does not exist."
    result = _file_outline_impl(target)
    if not result:
        ext = target.suffix
        supported = ".py, .go, .java, .ts, .tsx, .jsx"
        if ext not in _OUTLINE_PATTERNS and ext not in (".tsx", ".jsx"):
            return f"Error: unsupported file type {ext!r}. Supported: {supported}"
        return f"No definitions found in {path!r}."
    if len(result) > _MAX_OUTLINE_CHARS:
        result = result[:_MAX_OUTLINE_CHARS] + "\n... TRUNCATED. Use grep_search for specific symbols."
    return result


def _find_symbol_range(lines: list[str], name: str, ext: str) -> tuple[int, int] | None:
    """Find the line range of a symbol (function/class/method) in a file.

    Returns (start_line, end_line) as 1-indexed inclusive, or None if not found.
    Uses indentation-based boundary detection for Python, brace-counting for others.
    """
    patterns = _OUTLINE_PATTERNS.get(ext)
    if patterns is None and ext in (".tsx", ".jsx"):
        patterns = _OUTLINE_PATTERNS[".ts"]
    if not patterns:
        return None

    # Find the definition line
    start_idx = None
    for i, line in enumerate(lines):
        for pattern, _ in patterns:
            m = re.match(pattern, line)
            if m and name in m.group(1):
                start_idx = i
                break
        if start_idx is not None:
            break

    if start_idx is None:
        return None

    # Find the end of the symbol body
    if ext == ".py":
        # Python: indentation-based — find next line at same or lesser indent
        def_indent = len(lines[start_idx]) - len(lines[start_idx].lstrip())
        end_idx = start_idx + 1
        while end_idx < len(lines):
            line = lines[end_idx]
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("\"\"\""):
                line_indent = len(line) - len(line.lstrip())
                if line_indent <= def_indent:
                    break
            end_idx += 1
        # Back up past trailing blank lines
        while end_idx > start_idx + 1 and not lines[end_idx - 1].strip():
            end_idx -= 1
    else:
        # Brace-counting for Go, Java, TS
        brace_count = 0
        found_open = False
        end_idx = start_idx
        for i in range(start_idx, len(lines)):
            for ch in lines[i]:
                if ch == "{":
                    brace_count += 1
                    found_open = True
                elif ch == "}":
                    brace_count -= 1
            if found_open and brace_count <= 0:
                end_idx = i + 1
                break
        else:
            end_idx = min(start_idx + 50, len(lines))  # fallback

    return (start_idx + 1, end_idx)  # 1-indexed


@tool
def read_symbol(path: str, name: str, context: ToolContext = None) -> str:
    """Read a specific function, class, or method from a file by name.
    Returns the complete symbol body with line numbers.
    Use file_outline(path) or search_symbols(name) to discover symbol names first.
    Paths are relative to the repo working directory."""
    _ensure_agent_boundary(context)
    target = _resolve(path)
    if not target.exists():
        return f"Error: {path!r} does not exist."
    if target.is_dir():
        return f"Error: {path!r} is a directory."
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        # Dedup: skip if content unchanged since last read of this symbol
        cache_key = f"{target.resolve()}:{name}"
        content_hash = hash(content)
        if _symbol_read_hashes.get(cache_key) == content_hash:
            return f"Symbol '{name}' in '{path}' unchanged since last read. Use content from your context window."
        lines = content.splitlines()
        rng = _find_symbol_range(lines, name, target.suffix)
        if rng is None:
            # Fallback: grep for the name and return context around first match
            for i, line in enumerate(lines):
                if name in line:
                    start = max(0, i - 5)
                    end = min(len(lines), i + 50)
                    numbered = [f"{j + 1:6d}\t{lines[j]}" for j in range(start, end)]
                    result = f"Symbol '{name}' not found as a definition. Showing context around first mention:\n"
                    result += "\n".join(numbered)
                    return result
            return f"Error: '{name}' not found in {path!r}. Use file_outline('{path}') to see available symbols."

        start, end = rng
        # Add a few lines of context above (imports, decorators, comments)
        ctx_start = max(0, start - 6)
        symbol_lines = lines[ctx_start:end]
        offset = ctx_start
        numbered = [f"{i + offset + 1:6d}\t{line}" for i, line in enumerate(symbol_lines)]
        result = "\n".join(numbered)
        # Enforce output budget
        if len(result) > _MAX_READ_SYMBOL_CHARS:
            result = result[:_MAX_READ_SYMBOL_CHARS]
            result += f"\n... TRUNCATED. Symbol is large ({end - start + 1} lines). Use read_file('{path}', {start}, {end}) for the full range."
        _symbol_read_hashes[cache_key] = content_hash
        return result
    except Exception as exc:
        return f"Error reading symbol '{name}' from {path!r}: {exc}"


# ── Search & Navigation ─────────────────────────────────────


@tool
def glob_find(pattern: str, path: str = ".") -> str:
    """Find files matching a glob pattern (e.g. '**/*.py'). Returns sorted file paths.
    Paths are relative to the repo working directory."""
    base = _resolve(path)
    if not base.exists():
        return f"Error: {path!r} does not exist."
    try:
        matches = sorted(str(m) for m in base.glob(pattern) if m.is_file())
        if not matches:
            return f"No files matching {pattern!r} under {path!r}."
        if len(matches) > _MAX_OUTPUT_LINES:
            matches = matches[:_MAX_OUTPUT_LINES]
            matches.append(f"... (truncated at {_MAX_OUTPUT_LINES} files)")
        return "\n".join(matches)
    except Exception as exc:
        return f"Error: {exc}"


# Dedup: track recent grep queries to block identical re-runs
_grep_cache: dict[tuple, str] = {}


@tool
def grep_search(
    pattern: str,
    path: str = ".",
    glob_filter: str = "",
    max_results: int = 50,
    context: ToolContext = None,
) -> str:
    """Search file contents with regex pattern. Returns matching lines as file:line: content.
    Uses ripgrep (rg) for speed, falls back to Python regex if rg is not available.
    Paths are relative to the repo working directory."""
    _ensure_agent_boundary(context)
    cache_key = (pattern, path, glob_filter)
    if cache_key in _grep_cache:
        return f"Duplicate search — same results as before. Use them from your context window.\n{_grep_cache[cache_key][:500]}"
    result = _grep_search_impl(pattern, path, glob_filter, max_results)
    if not result.startswith("Error"):
        # Enforce output budget
        if len(result) > _MAX_GREP_CHARS:
            result = result[:_MAX_GREP_CHARS] + "\n... TRUNCATED. Narrow your search pattern."
        _grep_cache[cache_key] = result
    return result


def _grep_search_impl(pattern: str, path: str, glob_filter: str, max_results: int) -> str:
    """Core grep implementation."""
    resolved_path = str(_resolve(path))
    rg = shutil.which("rg")
    if rg:
        cmd = [
            rg,
            "--no-heading",
            "--line-number",
            "--max-count",
            str(max_results),
            "--color",
            "never",
        ]
        if glob_filter:
            cmd.extend(["--glob", glob_filter])
        cmd.extend([pattern, resolved_path])
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=_cwd())
            if proc.returncode == 0:
                lines = proc.stdout.strip().splitlines()
                if len(lines) > max_results:
                    lines = lines[:max_results]
                    lines.append(f"... (truncated at {max_results} matches)")
                return "\n".join(lines) if lines else f"No matches for {pattern!r} in {path!r}."
            if proc.returncode == 1:
                return f"No matches for {pattern!r} in {path!r}."
            return f"Error: rg exited {proc.returncode}: {proc.stderr.strip()}"
        except Exception as exc:
            return f"Error: {exc}"
    # Fallback: pure Python
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        return f"Invalid regex: {exc}"
    results = []
    base = _resolve(path)
    for filepath in sorted(base.rglob(glob_filter or "*")):
        if not filepath.is_file() or filepath.stat().st_size > _MAX_FILE_BYTES:
            continue
        try:
            for lineno, line in enumerate(
                filepath.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if compiled.search(line):
                    results.append(f"{filepath}:{lineno}: {line.rstrip()}")
                    if len(results) >= max_results:
                        break
        except Exception:
            continue
        if len(results) >= max_results:
            break
    if not results:
        return f"No matches for {pattern!r} in {path!r}."
    return "\n".join(results)


# Regex patterns for symbol definitions per language
_SYMBOL_DEF_PATTERNS = {
    "class": r"^\s*(?:export\s+)?(?:abstract\s+)?(?:public\s+)?class\s+{name}",
    "function": r"^\s*(?:export\s+)?(?:async\s+)?(?:def|function|func)\s+{name}\b",
    "type": r"^\s*(?:export\s+)?type\s+{name}\b",
    "interface": r"^\s*(?:export\s+)?interface\s+{name}\b",
    "struct": r"^type\s+{name}\s+struct\b",
}


@tool
def search_symbols(name: str, kind: str = "", path: str = ".") -> str:
    """Find definitions of classes, functions, types, interfaces, or structs.
    kind: 'class', 'function', 'type', 'interface', 'struct', or '' for all.
    Paths are relative to the repo working directory."""
    resolved_path = str(_resolve(path))
    if kind and kind not in _SYMBOL_DEF_PATTERNS:
        return f"Error: unknown kind {kind!r}. Use: class, function, type, interface, struct, or empty for all."
    patterns = {kind: _SYMBOL_DEF_PATTERNS[kind]} if kind else _SYMBOL_DEF_PATTERNS
    rg = shutil.which("rg")
    results = []
    for k, pat_template in patterns.items():
        pat = pat_template.format(name=re.escape(name))
        if rg:
            cmd = [rg, "--no-heading", "--line-number", "--color", "never", pat, resolved_path]
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=_cwd())
                if proc.returncode == 0:
                    for line in proc.stdout.strip().splitlines():
                        results.append(f"[{k}] {line}")
            except Exception:
                continue
        else:
            compiled = re.compile(pat)
            for filepath in sorted(Path(resolved_path).rglob("*")):
                if not filepath.is_file() or filepath.stat().st_size > _MAX_FILE_BYTES:
                    continue
                try:
                    for lineno, line in enumerate(
                        filepath.read_text(encoding="utf-8", errors="replace").splitlines(), 1
                    ):
                        if compiled.match(line):
                            results.append(f"[{k}] {filepath}:{lineno}: {line.rstrip()}")
                except Exception:
                    continue
    if not results:
        return f"No definitions found for {name!r} in {path!r}."
    result = "\n".join(results)
    if len(result) > _MAX_SEARCH_SYMBOLS_CHARS:
        result = result[:_MAX_SEARCH_SYMBOLS_CHARS] + "\n... TRUNCATED. Narrow your search."
    return result


@tool
def find_references(symbol: str, path: str = ".") -> str:
    """Find all usages of a symbol (excludes definitions). Returns file:line: context.
    Useful for blast radius analysis — 'if I change this, what breaks?'
    Paths are relative to the repo working directory."""
    resolved_path = str(_resolve(path))
    rg = shutil.which("rg")
    if not rg:
        return (
            "Error: ripgrep (rg) is required for find_references. Install it: brew install ripgrep"
        )
    cmd = [
        rg,
        "--no-heading",
        "--line-number",
        "--color",
        "never",
        "--word-regexp",
        symbol,
        resolved_path,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=_cwd())
        if proc.returncode != 0:
            return f"No references found for {symbol!r} in {path!r}."
        all_lines = proc.stdout.strip().splitlines()
    except Exception as exc:
        return f"Error: {exc}"

    def_pattern = re.compile(
        r"^\s*(?:export\s+)?(?:abstract\s+)?(?:public\s+)?(?:private\s+)?(?:protected\s+)?"
        r"(?:static\s+)?(?:async\s+)?(?:def|function|func|class|type|interface|struct|enum|const)\s+"
        + re.escape(symbol)
        + r"\b"
    )
    references = []
    for line in all_lines:
        parts = line.split(":", 2)
        if len(parts) >= 3:
            content = parts[2].strip()
            if not def_pattern.match(content):
                references.append(line)
    if not references:
        return f"No references (usages) found for {symbol!r} in {path!r}. It may only appear in definitions."
    if len(references) > _MAX_OUTPUT_LINES:
        references = references[:_MAX_OUTPUT_LINES]
        references.append(f"... (truncated at {_MAX_OUTPUT_LINES} references)")
    return "\n".join(references)


# ── Git Tools ────────────────────────────────────────────────


@tool
def git_diff(base: str = "", path: str = "") -> str:
    """Show diff of current changes vs a base branch or commit.
    Optionally scoped to a specific file or directory."""
    actual_base = base or _BASE_BRANCH
    cmd = ["git", "diff", actual_base]
    if path:
        cmd.extend(["--", path])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=_cwd())
        output = proc.stdout.strip()
        if not output:
            return (
                f"No diff between current state and {actual_base!r}"
                + (f" for {path!r}" if path else "")
                + "."
            )
        if len(output) > _MAX_COMMAND_OUTPUT:
            output = (
                output[:_MAX_COMMAND_OUTPUT] + f"\n... (truncated, {len(output):,} chars total)"
            )
        return output
    except Exception as exc:
        return f"Error: {exc}"


@tool
def git_log(path: str = "", max_count: int = 20) -> str:
    """Show recent commit history. Optionally scoped to a file/directory."""
    cmd = ["git", "log", f"--max-count={max_count}", "--format=%h %ad %an: %s", "--date=short"]
    if path:
        cmd.extend(["--", path])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=_cwd())
        return proc.stdout.strip() or "No commits found."
    except Exception as exc:
        return f"Error: {exc}"


@tool
def git_blame(path: str, start_line: int = 0, end_line: int = 0) -> str:
    """Show who last modified each line of a file. Optionally scoped to a line range."""
    cmd = ["git", "blame", "--date=short"]
    if start_line and end_line:
        cmd.extend([f"-L{start_line},{end_line}"])
    cmd.append(path)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=_cwd())
        if proc.returncode != 0:
            return f"Error: {proc.stderr.strip()}"
        return proc.stdout.strip() or f"No blame data for {path!r}."
    except Exception as exc:
        return f"Error: {exc}"


# ── Build & Test Tools ───────────────────────────────────────


@tool
def lint_and_format() -> str:
    """Run the project's linter and formatter. Commands are auto-detected from repo build files.
    If no commands were detected, use run_command with the appropriate command from repo_conventions."""
    cmd = _REPO_COMMANDS.get("lint")
    if not cmd:
        return "No lint command auto-detected. Read repo_conventions from contextbook and use run_command with the appropriate lint/format command."
    try:
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=_DEFAULT_TIMEOUT, cwd=_cwd()
        )
        output = (proc.stdout + proc.stderr).strip()
        if len(output) > _MAX_COMMAND_OUTPUT:
            output = output[:_MAX_COMMAND_OUTPUT] + "\n... (truncated)"
        status = "OK" if proc.returncode == 0 else f"ISSUES (exit {proc.returncode})"
        return f"lint_and_format: {status}\n{output}"
    except Exception as exc:
        return f"Error: {exc}"


@tool
def build_check() -> str:
    """Compile/type-check the project. Commands are auto-detected from repo build files.
    If no commands were detected, use run_command with the appropriate command from repo_conventions."""
    cmd = _REPO_COMMANDS.get("build")
    if not cmd:
        return "No build command auto-detected. Read repo_conventions from contextbook and use run_command with the appropriate build/compile command."
    try:
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=_DEFAULT_TIMEOUT, cwd=_cwd()
        )
        output = (proc.stdout + proc.stderr).strip()
        if len(output) > _MAX_COMMAND_OUTPUT:
            output = output[:_MAX_COMMAND_OUTPUT] + "\n... (truncated)"
        status = "PASS" if proc.returncode == 0 else f"FAIL (exit {proc.returncode})"
        return f"build_check: {status}\n{output}"
    except Exception as exc:
        return f"Error: {exc}"


@tool
def run_unit_tests(command: str = "") -> str:
    """Run unit tests. Uses auto-detected command or a custom one.
    If command is provided, uses it instead of the auto-detected one."""
    cmd = command or _REPO_COMMANDS.get("test")
    if not cmd:
        return "No test command auto-detected and none provided. Read repo_conventions from contextbook and use run_command, or pass a command argument."
    try:
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=600, cwd=_cwd()
        )
        output = (proc.stdout + proc.stderr).strip()
        if len(output) > _MAX_COMMAND_OUTPUT:
            output = output[:_MAX_COMMAND_OUTPUT] + "\n... (truncated)"
        status = "PASS" if proc.returncode == 0 else f"FAIL (exit {proc.returncode})"
        return f"unit_tests: {status}\n{output}"
    except subprocess.TimeoutExpired:
        return "Error: tests timed out after 600s."
    except Exception as exc:
        return f"Error: {exc}"


@tool
def run_e2e_tests(command: str = "") -> str:
    """Run end-to-end tests. Provide the command to run.
    Discover the e2e test runner from the repo's CI config or convention files."""
    if not command:
        return "No e2e command provided. Check repo_conventions for the e2e test runner command, then call run_e2e_tests(command='...')."
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=E2E_TOOL_TIMEOUT,
            cwd=_cwd(),
        )
        output = (proc.stdout + proc.stderr).strip()
        if len(output) > _MAX_COMMAND_OUTPUT * 2:
            output = output[: _MAX_COMMAND_OUTPUT * 2] + "\n... (truncated)"
        status = "ALL PASSED" if proc.returncode == 0 else f"FAILURES (exit {proc.returncode})"
        return f"e2e_tests: {status}\n{output}"
    except subprocess.TimeoutExpired:
        return f"Error: e2e tests timed out after {E2E_TOOL_TIMEOUT}s."
    except Exception as exc:
        return f"Error: {exc}"


# ── Contextbook Tools ────────────────────────────────────────


_VALID_SECTIONS = {
    "issue_pr",
    "repo_conventions",
    "architecture_design_test",
    "coder_plan",
    "implementation",
    "implementation_report",
    "qa_testing",
}


def _contextbook_dir() -> Path:
    """Return the contextbook directory, inside the working directory."""
    base = Path(_WORKING_DIR) if _WORKING_DIR else Path.cwd()
    return base / ".contextbook"


@tool(stateful=True)
def contextbook_write(section: str, content: str, append: bool = False) -> str:
    """Write to a named section of the team contextbook.
    Sections: issue_pr, repo_conventions, architecture_design_test, implementation, qa_testing.
    append=True adds to existing content; append=False replaces the section."""
    if section not in _VALID_SECTIONS:
        return f"Error: invalid section {section!r}. Valid: {', '.join(sorted(_VALID_SECTIONS))}"
    cb = _contextbook_dir()
    cb.mkdir(parents=True, exist_ok=True)
    filepath = cb / f"{section}.md"
    try:
        if append and filepath.exists():
            existing = filepath.read_text(encoding="utf-8")
            content = existing.rstrip() + "\n\n" + content
        filepath.write_text(content, encoding="utf-8")
        mode = "appended to" if append else "wrote"
        return f"Contextbook: {mode} '{section}' ({len(content):,} chars)."
    except Exception as exc:
        return f"Error writing contextbook section {section!r}: {exc}"


def _make_contextbook_writer(tool_name: str, fixed_section: str, max_calls: int = 2):
    """Create a contextbook_write tool locked to a specific section."""

    def _fn(content: str, append: bool = False) -> str:
        return contextbook_write(fixed_section, content, append)

    _fn.__name__ = tool_name
    _fn.__qualname__ = tool_name
    _fn.__doc__ = (
        f"Write to the '{fixed_section}' contextbook section.\n"
        f"append=True adds to existing content; append=False replaces."
    )
    # Apply @tool decorator with explicit name AFTER setting __name__
    return tool(name=tool_name, stateful=True, max_calls=max_calls)(_fn)


# Per-agent contextbook writers — section name is baked in, LLM can't pick wrong one
write_architecture = _make_contextbook_writer("write_architecture", "architecture_design_test", max_calls=2)
write_coder_plan = _make_contextbook_writer("write_coder_plan", "coder_plan", max_calls=2)
write_implementation_report = _make_contextbook_writer("write_implementation_report", "implementation_report", max_calls=1)
write_qa_testing = _make_contextbook_writer("write_qa_testing", "qa_testing", max_calls=2)


@tool(stateful=True)
def contextbook_read(section: str = "") -> str:
    """Read from the contextbook. If section is empty, returns table of contents
    (all section names + first line summary). If section is specified, returns full content.
    Returns a short message if the same section was already read and hasn't changed."""
    cb = _contextbook_dir()
    if not cb.exists():
        return "Contextbook is empty. No sections written yet."
    if not section:
        toc = []
        for name in sorted(_VALID_SECTIONS):
            filepath = cb / f"{name}.md"
            if filepath.exists():
                first_line = filepath.read_text(encoding="utf-8").split("\n")[0][:100]
                size = filepath.stat().st_size
                toc.append(f"  [{name}] ({size:,} chars) — {first_line}")
            else:
                toc.append(f"  [{name}] (empty)")
        return "Contextbook sections:\n" + "\n".join(toc)
    if section not in _VALID_SECTIONS:
        return f"Error: invalid section {section!r}. Valid: {', '.join(sorted(_VALID_SECTIONS))}"
    filepath = cb / f"{section}.md"
    if not filepath.exists():
        return f"Section '{section}' has not been written yet."
    content = filepath.read_text(encoding="utf-8")
    return content


@tool(stateful=True)
def contextbook_summary() -> str:
    """Returns a condensed summary of ALL contextbook sections.
    Designed to be called after context compaction or crash recovery for quick re-orientation."""
    cb = _contextbook_dir()
    if not cb.exists():
        return "Contextbook is empty. No sections written yet."
    summary_parts = []
    for name in sorted(_VALID_SECTIONS):
        filepath = cb / f"{name}.md"
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8")
            preview = content[:500]
            if len(content) > 500:
                preview += f"\n... ({len(content):,} chars total)"
            summary_parts.append(f"=== {name.upper()} ===\n{preview}")
    if not summary_parts:
        return "Contextbook is empty. No sections written yet."
    return "\n\n".join(summary_parts)


# ── General Command ──────────────────────────────────────────


@tool
def run_command(command: str, timeout: int = 300) -> str:
    """Execute a shell command in the repo working directory and return stdout+stderr with exit code."""
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=_cwd(),
            capture_output=True,
            text=True,
            timeout=min(timeout, 600),
        )
        output = (proc.stdout + proc.stderr).strip()
        if len(output) > _MAX_COMMAND_OUTPUT:
            output = (
                output[:_MAX_COMMAND_OUTPUT] + f"\n... (truncated, {len(output):,} chars total)"
            )
        return (
            f"[exit {proc.returncode}]\n{output}"
            if output
            else f"[exit {proc.returncode}] (no output)"
        )
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s."
    except Exception as exc:
        return f"Error: {exc}"


# ── Web Fetch ────────────────────────────────────────────────


@tool
def web_fetch(url: str) -> str:
    """Fetch content from a URL and return it as text. Useful for reading external
    documentation, referenced links in issues, RFCs, API docs, etc.
    HTML is converted to plain text. Returns first 16,000 chars."""
    import html.parser
    import urllib.request

    class _HTMLToText(html.parser.HTMLParser):
        def __init__(self):
            super().__init__()
            self._texts = []
            self._skip = False

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style", "noscript"):
                self._skip = True

        def handle_endtag(self, tag):
            if tag in ("script", "style", "noscript"):
                self._skip = False
            if tag in ("p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr"):
                self._texts.append("\n")

        def handle_data(self, data):
            if not self._skip:
                self._texts.append(data)

        def get_text(self):
            return "".join(self._texts)

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AgentSpan-IssueFixer/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read(500_000).decode("utf-8", errors="replace")

            if "html" in content_type.lower():
                parser = _HTMLToText()
                parser.feed(raw)
                text = parser.get_text()
            else:
                text = raw

            # Clean up whitespace
            lines = [line.strip() for line in text.splitlines()]
            text = "\n".join(line for line in lines if line)

            if len(text) > _MAX_COMMAND_OUTPUT:
                text = text[:_MAX_COMMAND_OUTPUT] + f"\n... (truncated, {len(text):,} chars total)"
            return text if text.strip() else f"No readable content at {url}"
    except Exception as exc:
        return f"Error fetching {url}: {exc}"


# ── Composite Tools (deterministic, reduce LLM turns) ───────


@tool
def get_coder_context() -> str:
    """Read ALL contextbook sections in one call.
    Returns only sections that have been written (skips empty ones).
    Call this ONCE at the start of your work. Do not call it again."""
    cb = _contextbook_dir()
    parts = []
    for section in ("issue_pr", "architecture_design_test", "implementation", "qa_testing"):
        filepath = cb / f"{section}.md"
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8")
            parts.append(f"=== {section.upper()} ===\n{content}")
    if not parts:
        return "(no contextbook sections written yet)"
    return "\n\n".join(parts)


# ── Repo Convention Discovery ───────────────────────────────


_CONVENTION_FILES = [
    "CLAUDE.md",
    "AGENTS.md",
    "AGENT.md",
    "GEMINI.md",
    ".cursorrules",
    ".cursor/rules",
    "CONTRIBUTING.md",
    "DEVELOPMENT.md",
    "HACKING.md",
]

_BUILD_FILES = [
    "pyproject.toml",
    "setup.py",
    "package.json",
    "tsconfig.json",
    "go.mod",
    "Cargo.toml",
    "build.gradle",
    "pom.xml",
    "Makefile",
    "Justfile",
    "Taskfile.yml",
]

_MAX_CONVENTION_CHARS = 5000
_MAX_BUILD_FILE_CHARS = 3000


def _detect_build_commands(base: Path) -> None:
    """Detect lint/build/test commands from build system files. Populates _REPO_COMMANDS."""
    global _REPO_COMMANDS
    _REPO_COMMANDS = {}

    pyproject = base / "pyproject.toml"
    package_json = base / "package.json"
    go_mod = base / "go.mod"
    cargo_toml = base / "Cargo.toml"
    makefile = base / "Makefile"
    gradlew = base / "gradlew"

    if pyproject.exists():
        content = pyproject.read_text(encoding="utf-8", errors="replace")
        if (base / "uv.lock").exists() or "[tool.uv]" in content:
            _REPO_COMMANDS["lint"] = "uv run ruff format . && uv run ruff check --fix ."
            _REPO_COMMANDS["build"] = "uv run ruff check ."
            _REPO_COMMANDS["test"] = "uv run pytest tests/ -x -q"
        elif "[tool.poetry]" in content:
            _REPO_COMMANDS["lint"] = "poetry run ruff format . && poetry run ruff check --fix ."
            _REPO_COMMANDS["build"] = "poetry run ruff check ."
            _REPO_COMMANDS["test"] = "poetry run pytest tests/ -x -q"
        else:
            _REPO_COMMANDS["lint"] = "ruff format . && ruff check --fix . 2>/dev/null || true"
            _REPO_COMMANDS["build"] = "python -m py_compile *.py 2>/dev/null || true"
            _REPO_COMMANDS["test"] = "pytest tests/ -x -q 2>/dev/null || python -m pytest -x -q"
    elif package_json.exists():
        try:
            pkg = json.loads(package_json.read_text(encoding="utf-8", errors="replace"))
            scripts = pkg.get("scripts", {})
            if "lint" in scripts:
                _REPO_COMMANDS["lint"] = "npm run lint"
            if "build" in scripts:
                _REPO_COMMANDS["build"] = "npm run build"
            if "test" in scripts:
                _REPO_COMMANDS["test"] = "npm test"
        except Exception:
            pass
    elif go_mod.exists():
        _REPO_COMMANDS["lint"] = "gofmt -w . && go vet ./..."
        _REPO_COMMANDS["build"] = "go build ./..."
        _REPO_COMMANDS["test"] = "go test ./... -race -count=1"
    elif cargo_toml.exists():
        _REPO_COMMANDS["lint"] = "cargo fmt"
        _REPO_COMMANDS["build"] = "cargo build"
        _REPO_COMMANDS["test"] = "cargo test"
    elif gradlew.exists():
        _REPO_COMMANDS["lint"] = "./gradlew spotlessApply 2>/dev/null || echo 'no formatter'"
        _REPO_COMMANDS["build"] = "./gradlew compileJava -x test"
        _REPO_COMMANDS["test"] = "./gradlew test"

    # Makefile overrides: if Makefile has lint/build/test targets, prefer them
    if makefile.exists():
        try:
            mk = makefile.read_text(encoding="utf-8", errors="replace")
            if re.search(r"^lint\s*:", mk, re.MULTILINE):
                _REPO_COMMANDS["lint"] = "make lint"
            if re.search(r"^build\s*:", mk, re.MULTILINE):
                _REPO_COMMANDS["build"] = "make build"
            if re.search(r"^test\s*:", mk, re.MULTILINE):
                _REPO_COMMANDS["test"] = "make test"
        except Exception:
            pass


def _discover_repo_conventions() -> str:
    """Read well-known convention files and detect build commands.

    Called after cloning. Populates _REPO_COMMANDS and _BASE_BRANCH.
    Returns a text summary for the repo_conventions contextbook section.
    """
    global _BASE_BRANCH
    parts = []
    base = Path(_WORKING_DIR)

    # 1. Detect default branch
    try:
        proc = subprocess.run(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=_cwd(),
        )
        if proc.returncode == 0:
            _BASE_BRANCH = proc.stdout.strip().split("/")[-1]
        else:
            proc2 = subprocess.run(
                ["git", "remote", "show", "origin"],
                capture_output=True,
                text=True,
                timeout=15,
                cwd=_cwd(),
            )
            m = re.search(r"HEAD branch:\s*(\S+)", proc2.stdout)
            if m:
                _BASE_BRANCH = m.group(1)
    except Exception:
        pass  # keep default "main"

    parts.append(f"Default branch: {_BASE_BRANCH}")

    # 2. Read convention files
    for filename in _CONVENTION_FILES:
        filepath = base / filename
        if filepath.exists() and filepath.is_file():
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
                if len(content) > _MAX_CONVENTION_CHARS:
                    content = content[:_MAX_CONVENTION_CHARS] + "\n... (truncated)"
                parts.append(f"--- {filename} ---\n{content}")
            except Exception:
                pass

    # 3. Read build files
    for filename in _BUILD_FILES:
        filepath = base / filename
        if filepath.exists() and filepath.is_file():
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
                if len(content) > _MAX_BUILD_FILE_CHARS:
                    content = content[:_MAX_BUILD_FILE_CHARS] + "\n... (truncated)"
                parts.append(f"--- {filename} ---\n{content}")
            except Exception:
                pass

    # 4. Read first 2 CI workflow files
    ci_dir = base / ".github" / "workflows"
    if ci_dir.exists():
        workflows = sorted(ci_dir.glob("*.yml"))[:2]
        for wf in workflows:
            try:
                content = wf.read_text(encoding="utf-8", errors="replace")
                if len(content) > _MAX_BUILD_FILE_CHARS:
                    content = content[:_MAX_BUILD_FILE_CHARS] + "\n... (truncated)"
                parts.append(f"--- .github/workflows/{wf.name} ---\n{content}")
            except Exception:
                pass

    # 5. Detect build commands
    _detect_build_commands(base)
    if any(_REPO_COMMANDS.values()):
        cmd_summary = "\n".join(f"  {k}: {v}" for k, v in _REPO_COMMANDS.items() if v)
        parts.append(f"--- Detected Commands ---\n{cmd_summary}")

    return "\n\n".join(parts)


@tool(max_calls=1)
def setup_repo(
    repo: str, issue_number: int, pr_number: int = 0, branch_prefix: str = "fix/issue-"
) -> str:
    """Clone repo, fetch issue (and PR if given), create branch, write issue_pr to contextbook.

    Handles both modes:
    - New issue (pr_number=0): clones, creates branch, writes issue details
    - PR feedback (pr_number>0): clones, checks out PR branch, writes issue+PR+comments

    Returns structured text with issue details, PR comments (if any), and repo info."""
    import json as _json

    # Normalize repo to owner/name format (strip URLs, .git suffix)
    repo = re.sub(r"^https?://", "", repo)
    repo = re.sub(r"^github\.com/", "", repo)
    repo = re.sub(r"\.git$", "", repo)
    repo = repo.strip("/")

    errors = []

    def _run(cmd: str, timeout: int = 60) -> str:
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=_cwd(),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            out = (proc.stdout + proc.stderr).strip()
            if proc.returncode != 0:
                errors.append(f"[{proc.returncode}] {cmd}: {out[:500]}")
            return out
        except Exception as e:
            errors.append(f"{cmd}: {e}")
            return ""

    # 1. Fetch issue (with ALL comments, no pagination limit)
    issue_json_raw = _run(
        f"gh issue view {issue_number} --repo {repo} "
        f"--json number,title,body,author,labels,comments,assignees,"
        f"milestone,state,createdAt,updatedAt,closedAt,reactionGroups",
        timeout=120,
    )
    issue_data = {}
    try:
        issue_data = _json.loads(issue_json_raw)
    except _json.JSONDecodeError:
        pass

    # 2. Clone repo (or fetch if already cloned — supports restarts)
    if (Path(_cwd()) / ".git").exists():
        _run("git fetch origin", timeout=120)
    else:
        _run(f"gh repo clone {repo} .", timeout=120)

    # 3. Gitignore contextbook
    _run(
        "echo '.contextbook/' >> .gitignore && git add .gitignore "
        "&& git commit -m 'chore: ignore contextbook'"
    )

    # 4. Branch handling
    if pr_number:
        # PR mode: fetch PR details and checkout existing branch
        pr_json_raw = _run(
            f"gh pr view {pr_number} --repo {repo} "
            f"--json number,title,body,state,headRefName,baseRefName,"
            f"comments,reviews,reviewRequests,author,labels"
        )
        pr_data = {}
        try:
            pr_data = _json.loads(pr_json_raw)
        except _json.JSONDecodeError:
            pass
        branch = pr_data.get("headRefName", f"fix/issue-{issue_number}")
        _run(f"git checkout {branch}")
    else:
        # New issue: create branch
        branch = f"{branch_prefix}{issue_number}"
        checkout_out = _run(f"git checkout -b {branch}")
        if "already exists" in checkout_out:
            _run(f"git checkout {branch}")
        push_out = _run(f"git push -u origin {branch}")
        if "error" in push_out.lower() or "rejected" in push_out.lower():
            _run(f"git push --force-with-lease -u origin {branch}")
        pr_data = {}

    # 5. Discover repo conventions
    conventions = _discover_repo_conventions()

    # 6. Build issue_pr contextbook content
    cb = _contextbook_dir()
    cb.mkdir(parents=True, exist_ok=True)

    issue_pr_parts = [
        f"# Issue #{issue_number}: {issue_data.get('title', 'unknown')}",
        f"Author: {issue_data.get('author', {}).get('login', 'unknown')}",
        f"Labels: {', '.join(lb.get('name', '') for lb in issue_data.get('labels', [])) or 'none'}",
        f"Repo: {repo}",
        f"Branch: {branch}",
        "",
        "## Issue Body",
        issue_data.get("body", "(empty)"),
    ]

    # Issue comments
    issue_comments = issue_data.get("comments", [])
    if issue_comments:
        issue_pr_parts.append("\n## Issue Comments")
        for c in issue_comments:
            author = c.get("author", {}).get("login", "unknown")
            body = c.get("body", "")
            issue_pr_parts.append(f"\n**@{author}:**\n{body}")

    # PR details and comments
    if pr_number and pr_data:
        issue_pr_parts.append(f"\n## PR #{pr_number}: {pr_data.get('title', '')}")
        issue_pr_parts.append(f"State: {pr_data.get('state', '')}")
        pr_body = pr_data.get("body", "")
        if pr_body:
            issue_pr_parts.append(f"\n### PR Body\n{pr_body}")

        pr_comments = pr_data.get("comments", [])
        if pr_comments:
            issue_pr_parts.append("\n### PR Comments")
            for c in pr_comments:
                author = c.get("author", {}).get("login", "unknown")
                body = c.get("body", "")
                issue_pr_parts.append(f"\n**@{author}:**\n{body}")

        reviews = pr_data.get("reviews", [])
        if reviews:
            issue_pr_parts.append("\n### Reviews")
            for r in reviews:
                author = r.get("author", {}).get("login", "unknown")
                state = r.get("state", "")
                body = r.get("body", "")
                issue_pr_parts.append(f"\n**@{author}** ({state}):\n{body}")

        # Fetch ALL inline/review comments (includes review threads and replies)
        inline_raw = _run(
            f"gh api repos/{repo}/pulls/{pr_number}/comments "
            f"--paginate "
            f"--jq '[.[] | {{path:.path,line:.line,original_line:.original_line,diff_hunk:.diff_hunk,body:.body,author:.user.login,in_reply_to_id:.in_reply_to_id,created_at:.created_at}}]'",
            timeout=120,
        )
        try:
            inline_comments = _json.loads(inline_raw) if inline_raw.strip() else []
        except _json.JSONDecodeError:
            inline_comments = []
        if inline_comments:
            issue_pr_parts.append("\n### Inline Review Comments")
            for ic in inline_comments:
                line_ref = ic.get("line") or ic.get("original_line") or "?"
                reply_note = " (reply)" if ic.get("in_reply_to_id") else ""
                issue_pr_parts.append(
                    f"\n**@{ic.get('author', '?')}**{reply_note} at `{ic.get('path', '?')}:{line_ref}`:\n{ic.get('body', '')}"
                )

        # Fetch issue timeline comments (linked issues, cross-references)
        issue_comments_raw = _run(
            f"gh api repos/{repo}/issues/{issue_number}/comments "
            f"--paginate "
            f"--jq '[.[] | {{body:.body,author:.user.login,created_at:.created_at}}]'",
            timeout=120,
        )
        try:
            api_issue_comments = _json.loads(issue_comments_raw) if issue_comments_raw.strip() else []
        except _json.JSONDecodeError:
            api_issue_comments = []
        # Merge with gh-cli comments (API returns all, gh-cli may paginate differently)
        existing_bodies = {c.get("body", "")[:100] for c in issue_comments}
        extra_comments = [c for c in api_issue_comments if c.get("body", "")[:100] not in existing_bodies]
        if extra_comments:
            issue_pr_parts.append("\n### Additional Issue Comments")
            for c in extra_comments:
                issue_pr_parts.append(
                    f"\n**@{c.get('author', '?')}:**\n{c.get('body', '')}"
                )

    issue_pr_content = "\n".join(issue_pr_parts)
    (cb / "issue_pr.md").write_text(issue_pr_content, encoding="utf-8")
    (cb / "repo_conventions.md").write_text(conventions, encoding="utf-8")

    # 7. Build return value — include full issue_pr content so the LLM
    # has all comments without needing to call contextbook_read.
    result_parts = [
        f"REPO: {repo}",
        f"BRANCH: {branch}",
        f"ISSUE: #{issue_number} {issue_data.get('title', 'unknown')}",
        f"AUTHOR: {issue_data.get('author', {}).get('login', 'unknown')}",
    ]
    if pr_number:
        result_parts.append(f"PR: #{pr_number}")
    result_parts.append(f"\nContextbook: wrote 'issue_pr' ({len(issue_pr_content):,} chars)")
    result_parts.append(f"Contextbook: wrote 'repo_conventions' ({len(conventions):,} chars)")

    if errors:
        result_parts.append("\nWARNINGS:\n" + "\n".join(errors))

    result_parts.append(f"\n---\n\n{issue_pr_content}")

    return "\n".join(result_parts)


# ── Batch Tools (force parallel operations in a single call) ──


@tool
def edit_files(edits_json: str) -> str:
    """Apply multiple edits in one call. Pass a JSON array of edits.
    Each edit: {"path": "file.py", "old_string": "...", "new_string": "..."}
    Example: edit_files('[{"path":"a.py","old_string":"foo","new_string":"bar"},{"path":"b.py","old_string":"x","new_string":"y"}]')
    Much faster than calling edit_file multiple times."""
    try:
        edits = json.loads(edits_json)
    except json.JSONDecodeError as exc:
        return f"Error: invalid JSON — {exc}"
    if not isinstance(edits, list):
        return "Error: expected a JSON array of edits."
    results = []
    any_success = False
    for i, edit in enumerate(edits):
        path = edit.get("path", "")
        old_string = edit.get("old_string", "")
        new_string = edit.get("new_string", "")
        if not path or not old_string:
            results.append(f"[{i + 1}] Error: missing 'path' or 'old_string'.")
            continue
        target = _resolve(path)
        if not target.exists():
            results.append(f"[{i + 1}] Error: {path!r} does not exist.")
            continue
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
            count = content.count(old_string)
            if count == 0:
                results.append(f"[{i + 1}] Error: old_string not found in {path!r}.")
                continue
            if count > 1:
                results.append(f"[{i + 1}] Error: old_string found {count} times in {path!r}.")
                continue
            new_content = content.replace(old_string, new_string, 1)
            target.write_text(new_content, encoding="utf-8")
            _file_read_hashes.pop(str(target.resolve()), None)
            _read_file_cache.pop(str(target.resolve()), None)
            results.append(
                f"[{i + 1}] OK: {path!r} edited ({len(old_string)} → {len(new_string)} chars)."
            )
            any_success = True
        except Exception as exc:
            results.append(f"[{i + 1}] Error editing {path!r}: {exc}")
    if any_success:
        _grep_cache.clear()
    return "\n".join(results)
