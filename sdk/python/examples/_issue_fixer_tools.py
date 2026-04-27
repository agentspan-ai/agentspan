# sdk/python/examples/_issue_fixer_tools.py
"""Reusable @tool functions for the Issue Fixer Agent.

All tools operate relative to a shared working directory set via
``set_working_dir(path)`` before any agent runs. This is typically a
temp folder where the target repo is cloned.

Provides 21 tools organized into 5 categories:
- File operations (read, write, edit, patch, list, outline)
- Search & navigation (glob, grep, symbols, references)
- Git (diff, log, blame)
- Build & test (lint, build, unit tests, e2e)
- Contextbook (write, read, summary)
"""

import glob as _glob
import json
import os
import re
import subprocess
import shutil
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

_MAX_FILE_BYTES = 500_000      # 500 KB
_MAX_OUTPUT_LINES = 200        # truncate long outputs
_MAX_COMMAND_OUTPUT = 16_000   # chars for command output
_MAX_READ_FILES_CHARS = 50_000 # total output cap for read_files (~15K tokens)
_DEFAULT_TIMEOUT = 120         # seconds for shell commands
E2E_TOOL_TIMEOUT = 5400        # 90 min — full e2e suite with margin

# Dedup: track file reads to block redundant re-reads
_file_read_hashes: dict[str, int] = {}  # resolved path -> content hash

# Auto-discovered at runtime by _discover_repo_conventions()
_BASE_BRANCH: str = "main"
_REPO_COMMANDS: dict[str, str] = {}  # keys: lint, build, test


# ── File Operations ──────────────────────────────────────────


_MIN_READ_LINES = 200  # minimum lines for ranged reads — prevents wasteful tiny chunks


@tool
def read_file(path: str, start_line: int = 0, end_line: int = 0, context: ToolContext = None) -> str:
    """Read a file's contents. Returns lines with line numbers.
    If start_line/end_line are 0, reads the entire file (preferred).
    Only use line ranges for very large files (1000+ lines). Minimum range: 200 lines.
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
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        # Dedup: full-file reads (no line range) are cached by content hash
        if not start_line and not end_line:
            content_hash = hash(content)
            cache_key = str(target.resolve())
            if _file_read_hashes.get(cache_key) == content_hash:
                return f"File '{path}' unchanged since last read ({len(content):,} chars, {len(content.splitlines())} lines). Use content from your context window."
            _file_read_hashes[cache_key] = content_hash
        lines = content.splitlines()
        if start_line or end_line:
            start = max(0, start_line - 1)
            end = end_line if end_line else len(lines)
            # Enforce minimum range — tiny reads waste turns
            if 0 < (end - start) < _MIN_READ_LINES:
                end = min(start + _MIN_READ_LINES, len(lines))
            lines = lines[start:end]
            offset = start
        else:
            offset = 0
        numbered = [f"{i + offset + 1:6d}\t{line}" for i, line in enumerate(lines)]
        return "\n".join(numbered)
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
        return f"Edited {path!r}: replaced 1 occurrence ({len(old_string)} → {len(new_string)} chars)."
    except Exception as exc:
        return f"Error editing {path!r}: {exc}"


@tool
def apply_patch(patch: str) -> str:
    """Apply a unified diff patch to the repo. Returns success/failure details."""
    try:
        proc = subprocess.run(
            ["git", "apply", "--check", "-"],
            input=patch, capture_output=True, text=True,
            cwd=_cwd(), timeout=30,
        )
        if proc.returncode != 0:
            return f"Error: patch would not apply cleanly:\n{proc.stderr.strip()}"
        proc = subprocess.run(
            ["git", "apply", "-"],
            input=patch, capture_output=True, text=True,
            cwd=_cwd(), timeout=30,
        )
        if proc.returncode == 0:
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
        entries = [e for e in entries if not e.name.startswith(".") and e.name not in ("node_modules", "__pycache__", ".git", "dist", "build")]
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
    return "\n".join(lines)


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
        (r"^\s*(?:public|private|protected|static|\s)*\s+(\w+\s+\w+\s*\([^)]*\))\s*(?:\{|throws)", "method"),
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


@tool
def file_outline(path: str) -> str:
    """Show the structure of a file: classes, functions, methods, interfaces.
    Works across Python, Go, Java, TypeScript, and React.
    Paths are relative to the repo working directory."""
    target = _resolve(path)
    if not target.exists():
        return f"Error: {path!r} does not exist."
    ext = target.suffix
    patterns = _OUTLINE_PATTERNS.get(ext)
    if patterns is None and ext in (".tsx", ".jsx"):
        patterns = _OUTLINE_PATTERNS[".ts"]
    if not patterns:
        return f"Error: unsupported file type {ext!r}. Supported: .py, .go, .java, .ts, .tsx, .jsx"
    try:
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        results = []
        for lineno, line in enumerate(lines, 1):
            for pattern, kind in patterns:
                m = re.match(pattern, line)
                if m:
                    results.append(f"{lineno:6d} | {kind:10s} | {m.group(1).strip()}")
                    break
        if not results:
            return f"No definitions found in {path!r}."
        return "\n".join(results)
    except Exception as exc:
        return f"Error: {exc}"


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
def grep_search(pattern: str, path: str = ".", glob_filter: str = "", max_results: int = 50, context: ToolContext = None) -> str:
    """Search file contents with regex pattern. Returns matching lines as file:line: content.
    Uses ripgrep (rg) for speed, falls back to Python regex if rg is not available.
    Paths are relative to the repo working directory."""
    _ensure_agent_boundary(context)
    cache_key = (pattern, path, glob_filter)
    if cache_key in _grep_cache:
        return f"Duplicate search — same results as before. Use them from your context window.\n{_grep_cache[cache_key][:500]}"
    result = _grep_search_impl(pattern, path, glob_filter, max_results)
    if not result.startswith("Error"):
        _grep_cache[cache_key] = result
    return result


def _grep_search_impl(pattern: str, path: str, glob_filter: str, max_results: int) -> str:
    """Core grep implementation."""
    resolved_path = str(_resolve(path))
    rg = shutil.which("rg")
    if rg:
        cmd = [rg, "--no-heading", "--line-number", "--max-count", str(max_results), "--color", "never"]
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
            for lineno, line in enumerate(filepath.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
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
    "class":     r"^\s*(?:export\s+)?(?:abstract\s+)?(?:public\s+)?class\s+{name}",
    "function":  r"^\s*(?:export\s+)?(?:async\s+)?(?:def|function|func)\s+{name}\b",
    "type":      r"^\s*(?:export\s+)?type\s+{name}\b",
    "interface": r"^\s*(?:export\s+)?interface\s+{name}\b",
    "struct":    r"^type\s+{name}\s+struct\b",
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
                    for lineno, line in enumerate(filepath.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                        if compiled.match(line):
                            results.append(f"[{k}] {filepath}:{lineno}: {line.rstrip()}")
                except Exception:
                    continue
    if not results:
        return f"No definitions found for {name!r} in {path!r}."
    return "\n".join(results)


@tool
def find_references(symbol: str, path: str = ".") -> str:
    """Find all usages of a symbol (excludes definitions). Returns file:line: context.
    Useful for blast radius analysis — 'if I change this, what breaks?'
    Paths are relative to the repo working directory."""
    resolved_path = str(_resolve(path))
    rg = shutil.which("rg")
    if not rg:
        return "Error: ripgrep (rg) is required for find_references. Install it: brew install ripgrep"
    cmd = [rg, "--no-heading", "--line-number", "--color", "never", "--word-regexp", symbol, resolved_path]
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
        + re.escape(symbol) + r"\b"
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
            return f"No diff between current state and {actual_base!r}" + (f" for {path!r}" if path else "") + "."
        if len(output) > _MAX_COMMAND_OUTPUT:
            output = output[:_MAX_COMMAND_OUTPUT] + f"\n... (truncated, {len(output):,} chars total)"
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
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=_DEFAULT_TIMEOUT, cwd=_cwd())
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
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=_DEFAULT_TIMEOUT, cwd=_cwd())
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
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=600, cwd=_cwd())
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
            command, shell=True,
            capture_output=True, text=True,
            timeout=E2E_TOOL_TIMEOUT,
            cwd=_cwd(),
        )
        output = (proc.stdout + proc.stderr).strip()
        if len(output) > _MAX_COMMAND_OUTPUT * 2:
            output = output[:_MAX_COMMAND_OUTPUT * 2] + "\n... (truncated)"
        status = "ALL PASSED" if proc.returncode == 0 else f"FAILURES (exit {proc.returncode})"
        return f"e2e_tests: {status}\n{output}"
    except subprocess.TimeoutExpired:
        return f"Error: e2e tests timed out after {E2E_TOOL_TIMEOUT}s."
    except Exception as exc:
        return f"Error: {exc}"


# ── Contextbook Tools ────────────────────────────────────────


_VALID_SECTIONS = {
    "issue_context", "repo_conventions", "implementation_plan", "test_plan", "change_context",
    "change_log", "review_findings", "test_results", "decisions", "status",
}


def _contextbook_dir() -> Path:
    """Return the contextbook directory, inside the working directory."""
    base = Path(_WORKING_DIR) if _WORKING_DIR else Path.cwd()
    return base / ".contextbook"


@tool(stateful=True)
def contextbook_write(section: str, content: str, append: bool = False) -> str:
    """Write to a named section of the team contextbook.
    Sections: issue_context, repo_conventions, implementation_plan, test_plan,
    change_log, review_findings, test_results, decisions, status.
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
            command, shell=True, cwd=_cwd(),
            capture_output=True, text=True,
            timeout=min(timeout, 600),
        )
        output = (proc.stdout + proc.stderr).strip()
        if len(output) > _MAX_COMMAND_OUTPUT:
            output = output[:_MAX_COMMAND_OUTPUT] + f"\n... (truncated, {len(output):,} chars total)"
        return f"[exit {proc.returncode}]\n{output}" if output else f"[exit {proc.returncode}] (no output)"
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
    import urllib.request
    import html.parser

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
    """Read ALL contextbook sections the coder needs in one call:
    implementation_plan, review_findings, change_log, test_plan, and change_context.
    Call this ONCE at the start of your work. Do not call it again."""
    cb = _contextbook_dir()
    parts = []
    for section in ("implementation_plan", "review_findings", "change_log", "test_plan", "change_context"):
        filepath = cb / f"{section}.md"
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8")
            parts.append(f"=== {section.upper()} ===\n{content}")
        else:
            parts.append(f"=== {section.upper()} ===\n(not yet written)")
    return "\n\n".join(parts)


@tool
def gather_review_context() -> str:
    """Gather all context needed for code review in one call:
    implementation_plan, change_log, and git diff vs main."""
    parts = []
    cb = _contextbook_dir()
    for section in ("implementation_plan", "change_log"):
        filepath = cb / f"{section}.md"
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8")
            parts.append(f"=== {section.upper()} ===\n{content}")
        else:
            parts.append(f"=== {section.upper()} ===\n(not yet written)")
    try:
        proc = subprocess.run(
            ["git", "diff", _BASE_BRANCH], capture_output=True, text=True,
            timeout=30, cwd=_cwd(),
        )
        diff = proc.stdout.strip()
        if len(diff) > _MAX_COMMAND_OUTPUT:
            diff = diff[:_MAX_COMMAND_OUTPUT] + f"\n... (truncated, {len(diff):,} chars)"
        parts.append(f"=== GIT DIFF (vs {_BASE_BRANCH}) ===\n{diff or '(no changes)'}")
    except Exception as e:
        parts.append(f"=== GIT DIFF (vs {_BASE_BRANCH}) ===\nError: {e}")
    return "\n\n".join(parts)


# ── Repo Convention Discovery ───────────────────────────────


_CONVENTION_FILES = [
    "CLAUDE.md", "AGENTS.md", "AGENT.md", "GEMINI.md",
    ".cursorrules", ".cursor/rules",
    "CONTRIBUTING.md", "DEVELOPMENT.md", "HACKING.md",
]

_BUILD_FILES = [
    "pyproject.toml", "setup.py", "package.json", "tsconfig.json",
    "go.mod", "Cargo.toml", "build.gradle", "pom.xml",
    "Makefile", "Justfile", "Taskfile.yml",
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
            capture_output=True, text=True, timeout=10, cwd=_cwd(),
        )
        if proc.returncode == 0:
            _BASE_BRANCH = proc.stdout.strip().split("/")[-1]
        else:
            proc2 = subprocess.run(
                ["git", "remote", "show", "origin"],
                capture_output=True, text=True, timeout=15, cwd=_cwd(),
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


@tool
def setup_issue_repo(repo: str, issue_number: int, branch_prefix: str = "fix/issue-") -> str:
    """Fetch a GitHub issue, clone the repo, create a branch, and write issue_context to contextbook.

    Does ALL mechanical setup in one deterministic call:
    1. Fetches issue JSON via gh CLI
    2. Clones the repo into the working directory
    3. Adds .contextbook/ to .gitignore
    4. Creates and pushes the fix branch
    5. Writes issue_context to contextbook
    6. Lists top-level directory

    Returns: issue JSON + directory listing for module identification."""
    import json as _json

    errors = []

    def _run(cmd: str, timeout: int = 60) -> str:
        try:
            proc = subprocess.run(
                cmd, shell=True, cwd=_cwd(),
                capture_output=True, text=True, timeout=timeout,
            )
            out = (proc.stdout + proc.stderr).strip()
            if proc.returncode != 0:
                errors.append(f"[{proc.returncode}] {cmd}: {out[:500]}")
            return out
        except Exception as e:
            errors.append(f"{cmd}: {e}")
            return ""

    # 1. Fetch issue
    issue_json_raw = _run(
        f'gh issue view {issue_number} --repo {repo} '
        f'--json number,title,body,author,labels,comments,assignees,'
        f'milestone,state,createdAt,updatedAt,closedAt,reactionGroups'
    )
    issue_data = {}
    try:
        issue_data = _json.loads(issue_json_raw)
    except _json.JSONDecodeError:
        pass

    # 2. Clone repo
    _run(f'gh repo clone {repo} .', timeout=120)

    # 3. Gitignore contextbook
    _run("echo '.contextbook/' >> .gitignore && git add .gitignore "
         "&& git commit -m 'chore: ignore contextbook'")

    # 4. Create branch (handle existing branch gracefully)
    branch = f"{branch_prefix}{issue_number}"
    checkout_out = _run(f'git checkout -b {branch}')
    if "already exists" in checkout_out:
        _run(f'git checkout {branch}')

    # 5. Push (handle existing remote branch)
    push_out = _run(f'git push -u origin {branch}')
    if "error" in push_out.lower() or "rejected" in push_out.lower():
        _run(f'git push --force-with-lease -u origin {branch}')

    # 6. Write issue_context to contextbook
    cb = _contextbook_dir()
    cb.mkdir(parents=True, exist_ok=True)
    if issue_data:
        (cb / "issue_context.md").write_text(
            _json.dumps(issue_data, indent=2, default=str), encoding="utf-8"
        )

    # 7. Discover repo conventions (reads CLAUDE.md, AGENTS.md, build files, etc.)
    conventions = _discover_repo_conventions()
    (cb / "repo_conventions.md").write_text(conventions, encoding="utf-8")

    # 8. List top-level directory
    dir_listing = _run("ls -1")

    # Build result
    title = issue_data.get("title", "unknown")
    author = issue_data.get("author", {}).get("login", "unknown")
    body = issue_data.get("body", "")
    labels = [l.get("name", "") for l in issue_data.get("labels", [])]

    result_parts = [
        f"=== ISSUE #{issue_number} ===",
        f"Title: {title}",
        f"Author: {author}",
        f"Labels: {', '.join(labels) or 'none'}",
        f"Branch: {branch}",
        f"Repo: {repo}",
        f"",
        f"=== ISSUE BODY ===",
        body[:5000] if body else "(empty)",
        f"",
        f"=== REPO CONVENTIONS (summary) ===",
        f"Default branch: {_BASE_BRANCH}",
        f"Detected commands: {', '.join(f'{k}={v}' for k,v in _REPO_COMMANDS.items()) or 'none (agents will discover from convention files)'}",
        f"",
        f"=== DIRECTORY LISTING ===",
        dir_listing,
    ]

    if errors:
        result_parts.append(f"\n=== WARNINGS ===\n" + "\n".join(errors))

    return "\n".join(result_parts)


@tool
def fetch_pr_context(repo: str, pr_number: int) -> str:
    """Fetch PR context in one call: PR details, comments, reviews, linked issue,
    and clone + checkout the branch.

    Returns structured JSON with all data needed to analyze PR feedback.
    The repo is cloned into the working directory and the PR branch is checked out.
    Does NOT fetch the diff — the coder agent reads files directly."""
    import json as _json

    errors = []
    results = {}

    def _run(cmd: str, timeout: int = 60) -> str:
        try:
            proc = subprocess.run(
                cmd, shell=True, cwd=_cwd(),
                capture_output=True, text=True, timeout=timeout,
            )
            out = (proc.stdout + proc.stderr).strip()
            if proc.returncode != 0:
                errors.append(f"[{proc.returncode}] {cmd}: {out[:500]}")
            return out
        except Exception as e:
            errors.append(f"{cmd}: {e}")
            return ""

    # 1. PR details
    pr_json_raw = _run(
        f'gh pr view {pr_number} --repo {repo} '
        f'--json number,title,body,state,headRefName,baseRefName,'
        f'comments,reviews,reviewRequests,author,labels'
    )
    pr_data = {}
    try:
        pr_data = _json.loads(pr_json_raw)
        results["pr"] = pr_data
    except _json.JSONDecodeError:
        results["pr_raw"] = pr_json_raw[:8000]

    # 2. Linked issue
    issue_number = None
    body = pr_data.get("body", "") or ""
    m = re.search(r'(?:Fixes|Closes|Resolves)\s+#(\d+)', body, re.IGNORECASE)
    if m:
        issue_number = int(m.group(1))
    else:
        m = re.search(r'#(\d+)', body)
        if m:
            issue_number = int(m.group(1))
    results["issue_number"] = issue_number

    if issue_number:
        issue_json_raw = _run(
            f'gh issue view {issue_number} --repo {repo} '
            f'--json number,title,body,author,labels,comments,assignees,'
            f'milestone,state,createdAt,updatedAt,closedAt,reactionGroups'
        )
        try:
            results["issue"] = _json.loads(issue_json_raw)
        except _json.JSONDecodeError:
            results["issue_raw"] = issue_json_raw[:8000]

    # 4. Clone and checkout
    branch = pr_data.get("headRefName", f"pr-{pr_number}")
    results["branch"] = branch
    _run(f'gh repo clone {repo} .', timeout=120)
    _run("echo '.contextbook/' >> .gitignore")
    _run(f'git checkout {branch}')

    # 5. Write issue_context to contextbook (deterministic, no LLM needed)
    cb = _contextbook_dir()
    cb.mkdir(parents=True, exist_ok=True)
    if issue_number and "issue" in results:
        (cb / "issue_context.md").write_text(
            _json.dumps(results["issue"], indent=2, default=str), encoding="utf-8"
        )

    # 5b. Discover repo conventions
    conventions = _discover_repo_conventions()
    (cb / "repo_conventions.md").write_text(conventions, encoding="utf-8")

    # 6. Structured comments
    comments = []
    for c in pr_data.get("comments", []):
        comments.append({
            "type": "pr_comment",
            "author": c.get("author", {}).get("login", "unknown"),
            "body": c.get("body", ""),
            "createdAt": c.get("createdAt", ""),
        })
    for r in pr_data.get("reviews", []):
        comments.append({
            "type": "review",
            "author": r.get("author", {}).get("login", "unknown"),
            "state": r.get("state", ""),
            "body": r.get("body", ""),
            "createdAt": r.get("submittedAt", ""),
        })
    results["all_comments"] = comments

    # 7. Inline review comments
    inline_raw = _run(
        f'gh api repos/{repo}/pulls/{pr_number}/comments '
        f'--jq \'[.[] | {{path:.path,line:.line,body:.body,author:.user.login,createdAt:.created_at}}]\''
    )
    try:
        results["inline_comments"] = _json.loads(inline_raw) if inline_raw.strip() else []
    except _json.JSONDecodeError:
        results["inline_comments"] = []

    results["errors"] = errors
    results["working_dir"] = _WORKING_DIR
    return _json.dumps(results, indent=2, default=str)


# ── Batch Tools (force parallel operations in a single call) ──


@tool
def read_files(paths: str) -> str:
    """Read multiple files in one call. Pass comma-separated paths.
    Example: read_files("src/main.py, src/utils.py, tests/test_main.py")
    Total output capped at ~50K chars. Large files are truncated with a note
    to use read_file(path, start_line, end_line) for specific sections."""
    parts = []
    total_chars = 0
    for raw_path in paths.split(","):
        path = raw_path.strip()
        if not path:
            continue
        target = _resolve(path)
        if not target.exists():
            parts.append(f"=== {path} ===\nError: {path!r} does not exist.")
            continue
        if target.is_dir():
            parts.append(f"=== {path} ===\nError: {path!r} is a directory.")
            continue
        size = target.stat().st_size
        if size > _MAX_FILE_BYTES:
            parts.append(f"=== {path} ===\nError: {path!r} is {size:,} bytes (limit {_MAX_FILE_BYTES:,}).")
            continue
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            numbered = [f"{i + 1:6d}\t{line}" for i, line in enumerate(lines)]
            file_output = "\n".join(numbered)
            remaining = _MAX_READ_FILES_CHARS - total_chars
            if remaining <= 0:
                parts.append(f"=== {path} ===\nSKIPPED — output budget exhausted. Use read_file('{path}') separately.")
                continue
            if len(file_output) > remaining:
                # Truncate and suggest targeted read
                file_output = file_output[:remaining]
                file_output += f"\n... TRUNCATED ({len(lines)} lines total, {len(content):,} chars). Use read_file('{path}', start_line, end_line) for specific sections."
            total_chars += len(file_output)
            parts.append(f"=== {path} ===\n{file_output}")
        except Exception as exc:
            parts.append(f"=== {path} ===\nError: {exc}")
    if not parts:
        return "Error: no valid paths provided."
    return "\n\n".join(parts)


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
            results.append(f"[{i+1}] Error: missing 'path' or 'old_string'.")
            continue
        target = _resolve(path)
        if not target.exists():
            results.append(f"[{i+1}] Error: {path!r} does not exist.")
            continue
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
            count = content.count(old_string)
            if count == 0:
                results.append(f"[{i+1}] Error: old_string not found in {path!r}.")
                continue
            if count > 1:
                results.append(f"[{i+1}] Error: old_string found {count} times in {path!r}.")
                continue
            new_content = content.replace(old_string, new_string, 1)
            target.write_text(new_content, encoding="utf-8")
            results.append(f"[{i+1}] OK: {path!r} edited ({len(old_string)} → {len(new_string)} chars).")
            any_success = True
        except Exception as exc:
            results.append(f"[{i+1}] Error editing {path!r}: {exc}")
    if any_success:
        _grep_cache.clear()
    return "\n".join(results)
