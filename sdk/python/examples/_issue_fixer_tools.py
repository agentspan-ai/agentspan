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

# ── Working directory ──────────────────────────────────────────

_WORKING_DIR: str = ""


def set_working_dir(path: str) -> None:
    """Set the shared working directory for all tools.

    Must be called before any agent runs. Typically a temp folder where
    the target repo will be cloned into by the Issue Analyst.
    """
    global _WORKING_DIR
    _WORKING_DIR = str(path)
    os.makedirs(_WORKING_DIR, exist_ok=True)


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

_MAX_FILE_BYTES = 100_000      # 100 KB
_MAX_OUTPUT_LINES = 200        # truncate long outputs
_MAX_COMMAND_OUTPUT = 16_000   # chars for command output
_DEFAULT_TIMEOUT = 120         # seconds for shell commands
E2E_TOOL_TIMEOUT = 5400        # 90 min — full e2e suite with margin

# Module detection mapping: directory prefix -> module name
_MODULE_MAP = {
    "sdk/python": "sdk/python",
    "sdk/typescript": "sdk/typescript",
    "cli": "cli",
    "server": "server",
    "ui": "ui",
}

_last_tool_calls: dict = {}
_MAX_CONSECUTIVE = 2

def _check_loop(tool_name: str, args_key: str) -> str:
    prev = _last_tool_calls.get(tool_name)
    if prev and prev[0] == args_key:
        count = prev[1] + 1
        _last_tool_calls[tool_name] = (args_key, count)
        if count > _MAX_CONSECUTIVE:
            return (
                f"LOOP DETECTED: {tool_name} called {count} times with the same arguments. "
                f"You already have this result. STOP calling this tool and proceed with your task."
            )
    else:
        _last_tool_calls[tool_name] = (args_key, 1)
    return ""


# ── File Operations ──────────────────────────────────────────


@tool
def read_file(path: str, start_line: int = 0, end_line: int = 0) -> str:
    """Read a file's contents with optional line range. Returns lines with line numbers.
    If start_line and end_line are both 0, reads the entire file.
    Paths are relative to the repo working directory."""
    loop_err = _check_loop("read_file", f"{path}:{start_line}:{end_line}")
    if loop_err:
        return loop_err
    target = _resolve(path)
    if not target.exists():
        return f"Error: {path!r} does not exist."
    if target.is_dir():
        return f"Error: {path!r} is a directory. Use list_directory instead."
    size = target.stat().st_size
    if size > _MAX_FILE_BYTES:
        return f"Error: {path!r} is {size:,} bytes (limit {_MAX_FILE_BYTES:,}). Use grep_search to find specific content."
    try:
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        if start_line or end_line:
            start = max(0, start_line - 1)
            end = end_line if end_line else len(lines)
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


@tool
def grep_search(pattern: str, path: str = ".", glob_filter: str = "", max_results: int = 50) -> str:
    """Search file contents with regex pattern. Returns matching lines as file:line: content.
    Uses ripgrep (rg) for speed, falls back to Python regex if rg is not available.
    Paths are relative to the repo working directory."""
    loop_err = _check_loop("grep_search", f"{pattern}:{path}:{glob_filter}")
    if loop_err:
        return loop_err
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
def git_diff(base: str = "main", path: str = "") -> str:
    """Show diff of current changes vs a base branch or commit.
    Optionally scoped to a specific file or directory."""
    cmd = ["git", "diff", base]
    if path:
        cmd.extend(["--", path])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=_cwd())
        output = proc.stdout.strip()
        if not output:
            return f"No diff between current state and {base!r}" + (f" for {path!r}" if path else "") + "."
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


def _detect_module(path: str) -> str:
    """Detect which monorepo module a path belongs to."""
    for prefix, module in _MODULE_MAP.items():
        if path.startswith(prefix):
            return module
    return ""


_LINT_COMMANDS = {
    "sdk/python":      "cd sdk/python && uv run ruff format . && uv run ruff check --fix .",
    "sdk/typescript":  "cd sdk/typescript && npx eslint --fix . && npx prettier --write .",
    "cli":             "cd cli && gofmt -w . && go vet ./...",
    "server":          "cd server && gradle spotlessApply 2>/dev/null || echo 'spotless not configured'",
    "ui":              "cd ui && npx eslint --fix . && npx prettier --write .",
}


@tool
def lint_and_format(module: str = "", path: str = "") -> str:
    """Run the appropriate linter and formatter for a module.
    Auto-detects module from path if module is empty."""
    resolved = module or _detect_module(path)
    if not resolved:
        return "Error: cannot detect module. Provide module (sdk/python, sdk/typescript, cli, server, ui) or a path within one."
    cmd = _LINT_COMMANDS.get(resolved)
    if not cmd:
        return f"Error: unknown module {resolved!r}. Known: {', '.join(_LINT_COMMANDS)}."
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=_DEFAULT_TIMEOUT, cwd=_cwd())
        output = (proc.stdout + proc.stderr).strip()
        if len(output) > _MAX_COMMAND_OUTPUT:
            output = output[:_MAX_COMMAND_OUTPUT] + "\n... (truncated)"
        status = "OK" if proc.returncode == 0 else f"ISSUES (exit {proc.returncode})"
        return f"[{resolved}] lint_and_format: {status}\n{output}"
    except Exception as exc:
        return f"Error: {exc}"


_BUILD_COMMANDS = {
    "sdk/python":      "cd sdk/python && uv run ruff check .",
    "sdk/typescript":  "cd sdk/typescript && npx tsc --noEmit",
    "cli":             "cd cli && go build ./...",
    "server":          "cd server && gradle compileJava -x test",
    "ui":              "cd ui && pnpm run build",
}


@tool
def build_check(module: str = "") -> str:
    """Compile/type-check a module without running tests.
    module: sdk/python, sdk/typescript, cli, server, or ui."""
    if not module:
        return "Error: module is required. Use: sdk/python, sdk/typescript, cli, server, ui."
    cmd = _BUILD_COMMANDS.get(module)
    if not cmd:
        return f"Error: unknown module {module!r}. Known: {', '.join(_BUILD_COMMANDS)}."
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=_DEFAULT_TIMEOUT, cwd=_cwd())
        output = (proc.stdout + proc.stderr).strip()
        if len(output) > _MAX_COMMAND_OUTPUT:
            output = output[:_MAX_COMMAND_OUTPUT] + "\n... (truncated)"
        status = "PASS" if proc.returncode == 0 else f"FAIL (exit {proc.returncode})"
        return f"[{module}] build_check: {status}\n{output}"
    except Exception as exc:
        return f"Error: {exc}"


_UNIT_TEST_COMMANDS = {
    "sdk/python":      "cd sdk/python && uv run pytest tests/ -x -q",
    "sdk/typescript":  "cd sdk/typescript && npm test",
    "cli":             "cd cli && go test ./... -race -count=1",
    "server":          "cd server && gradle test",
    "ui":              "cd ui && pnpm test",
}


@tool
def run_unit_tests(module: str, command: str = "") -> str:
    """Run unit tests for a specific module. If command is provided, uses it instead of the default."""
    cmd = command or _UNIT_TEST_COMMANDS.get(module)
    if not cmd:
        return f"Error: unknown module {module!r} and no command provided. Known: {', '.join(_UNIT_TEST_COMMANDS)}."
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=600, cwd=_cwd())
        output = (proc.stdout + proc.stderr).strip()
        if len(output) > _MAX_COMMAND_OUTPUT:
            output = output[:_MAX_COMMAND_OUTPUT] + "\n... (truncated)"
        status = "PASS" if proc.returncode == 0 else f"FAIL (exit {proc.returncode})"
        return f"[{module}] unit_tests: {status}\n{output}"
    except subprocess.TimeoutExpired:
        return "Error: tests timed out after 600s."
    except Exception as exc:
        return f"Error: {exc}"


@tool
def run_e2e_tests(suite: str = "", sdk: str = "both") -> str:
    """Run the full e2e test suite via e2e/orchestrator.sh (~45 min for full suite).
    suite: optional suite name filter (e.g. 'suite9').
    sdk: 'python', 'typescript', or 'both' (default)."""
    cmd = ["./e2e/orchestrator.sh", "--no-build", "--no-start", "--sdk", sdk]
    if suite:
        cmd.extend(["--suite", suite])
    try:
        proc = subprocess.run(
            " ".join(cmd), shell=True,
            capture_output=True, text=True,
            timeout=E2E_TOOL_TIMEOUT,
            cwd=_cwd(),
        )
        output = (proc.stdout + proc.stderr).strip()
        if len(output) > _MAX_COMMAND_OUTPUT * 2:
            output = output[:_MAX_COMMAND_OUTPUT * 2] + "\n... (truncated)"
        status = "ALL PASSED" if proc.returncode == 0 else f"FAILURES (exit {proc.returncode})"
        return f"e2e_tests (sdk={sdk}, suite={suite or 'all'}): {status}\n{output}"
    except subprocess.TimeoutExpired:
        return "Error: e2e tests timed out after 90 minutes."
    except Exception as exc:
        return f"Error: {exc}"


# ── Contextbook Tools ────────────────────────────────────────


_VALID_SECTIONS = {
    "issue_context", "module_map", "implementation_plan", "test_plan", "change_context",
    "change_log", "review_findings", "test_results", "decisions", "status",
}


def _contextbook_dir() -> Path:
    """Return the contextbook directory, inside the working directory."""
    base = Path(_WORKING_DIR) if _WORKING_DIR else Path.cwd()
    return base / ".contextbook"


@tool(stateful=True)
def contextbook_write(section: str, content: str, append: bool = False) -> str:
    """Write to a named section of the team contextbook.
    Sections: issue_context, module_map, implementation_plan, test_plan,
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
    (all section names + first line summary). If section is specified, returns full content."""
    loop_err = _check_loop("contextbook_read", section)
    if loop_err:
        return loop_err
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
    return filepath.read_text(encoding="utf-8")


@tool(stateful=True)
def contextbook_summary() -> str:
    """Returns a condensed summary of ALL contextbook sections.
    Designed to be called after context compaction or crash recovery for quick re-orientation."""
    loop_err = _check_loop("contextbook_summary", "")
    if loop_err:
        return loop_err
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
    loop_err = _check_loop("run_command", command)
    if loop_err:
        return loop_err
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


# ── Deterministic PR/Issue Tools ─────────────────────────────


@tool
def fetch_pr_context(repo: str, pr_number: int) -> str:
    """Fetch PR details, diff, comments, reviews, and the linked issue in one call.

    Clones the repo, checks out the PR branch, and writes everything to the
    contextbook (issue_context, review_findings, module_map, status).
    Returns a structured summary. No LLM needed — pure CLI orchestration.
    """
    import json as _json
    results = []

    def _run(cmd):
        proc = subprocess.run(cmd, shell=True, cwd=_cwd(), capture_output=True, text=True, timeout=120)
        return proc.stdout.strip(), proc.stderr.strip(), proc.returncode

    # 1. Fetch PR details (use minimal fields to avoid scope issues)
    pr_json_out, pr_err, rc = _run(
        f"gh pr view {pr_number} --repo {repo} "
        f"--json number,title,body,state,headRefName"
    )
    if rc != 0:
        return f"Error fetching PR #{pr_number}: {pr_err}"

    try:
        pr_data = _json.loads(pr_json_out)
    except:
        pr_data = {"raw": pr_json_out}
    results.append(f"PR #{pr_number}: {pr_data.get('title', '?')}")

    # Fetch comments via REST API (no extra scopes needed beyond 'repo')
    # Issue comments API covers both issue and PR conversation comments
    comments_out, _, _ = _run(
        f"gh api repos/{repo}/issues/{pr_number}/comments "
        f"--jq '.[] | \"[\" + .user.login + \"]: \" + .body'"
    )
    # Inline review comments (file-level feedback)
    review_comments_out, _, _ = _run(
        f"gh api repos/{repo}/pulls/{pr_number}/comments "
        f"--jq '.[] | .path + \":\" + (.line|tostring) + \" [\" + .user.login + \"]: \" + .body'"
    )
    # Review body text (approve/request changes summary)
    reviews_out, _, _ = _run(
        f"gh api repos/{repo}/pulls/{pr_number}/reviews "
        f"--jq '.[] | select(.body != \"\") | \"[\" + .user.login + \"] (\" + .state + \"): \" + .body'"
    )

    # 2. Fetch PR diff (truncated to avoid payload issues)
    diff_out, _, _ = _run(f"gh pr diff {pr_number} --repo {repo}")
    if len(diff_out) > 8000:
        diff_out = diff_out[:8000] + "\n...[diff truncated]"
    results.append(f"Diff: {len(diff_out)} chars")

    # 3. Clone and checkout
    _run(f"gh repo clone {repo} .")
    _run("echo '.contextbook/' >> .gitignore")
    branch = pr_data.get("headRefName", f"fix/issue-{pr_number}")
    _run(f"git checkout {branch}")
    results.append(f"Branch: {branch}")

    # 4. Extract issue number from PR body
    body = pr_data.get("body", "")
    issue_num = None
    import re
    match = re.search(r"[Ff]ixes?\s*#(\d+)", body)
    if match:
        issue_num = int(match.group(1))

    # 5. Fetch issue if found (use API to get full details + comments)
    issue_json = ""
    if issue_num:
        issue_out, _, rc = _run(
            f"gh issue view {issue_num} --repo {repo} "
            f"--json number,title,body,labels,state"
        )
        if rc == 0:
            issue_json = issue_out
            results.append(f"Issue #{issue_num} fetched")
        # Also get issue comments
        issue_comments_out, _, _ = _run(
            f"gh api repos/{repo}/issues/{issue_num}/comments "
            f"--jq '.[] | \"[\" + .user.login + \"]: \" + .body'"
        )
        if issue_comments_out.strip():
            issue_json += "\n\n## Issue Comments\n" + issue_comments_out[:3000]

    # 6. Extract review comments into structured feedback
    feedback_items = []
    if comments_out.strip():
        feedback_items.append("## PR Comments\n" + comments_out[:2000])
    if reviews_out.strip():
        feedback_items.append("## Review Feedback\n" + reviews_out[:2000])
    if review_comments_out.strip():
        feedback_items.append("## Inline Review Comments\n" + review_comments_out[:2000])
    feedback_text = "\n\n".join(feedback_items) if feedback_items else "No review comments found."

    # 7. Write to contextbook
    cb = _contextbook_dir()
    cb.mkdir(parents=True, exist_ok=True)

    if issue_json:
        (cb / "issue_context.md").write_text(issue_json, encoding="utf-8")

    review_doc = f"# PR #{pr_number} Review Feedback\n\n"
    review_doc += f"## PR Title\n{pr_data.get('title', '?')}\n\n"
    review_doc += f"## PR Body\n{body[:2000]}\n\n"
    review_doc += f"{feedback_text}\n\n"
    review_doc += f"## Diff\n```diff\n{diff_out}\n```\n"
    (cb / "review_findings.md").write_text(review_doc, encoding="utf-8")

    (cb / "status.md").write_text(
        f"PR feedback collected for PR #{pr_number}. Ready for implementation.",
        encoding="utf-8"
    )

    # Return the FULL context so the next pipeline stage has everything.
    # The return value becomes the downstream agent's input prompt.
    output_parts = [
        f"# PR #{pr_number}: {pr_data.get('title', '?')}",
        f"Branch: {branch}",
    ]

    # Issue details
    if issue_num and issue_json:
        try:
            issue_data = _json.loads(issue_json.split("\n\n##")[0])  # JSON part only
            output_parts.append(f"\n## Issue #{issue_num}: {issue_data.get('title', '?')}")
            issue_body = issue_data.get("body", "")
            if issue_body:
                output_parts.append(issue_body[:3000])
        except:
            output_parts.append(f"\n## Issue #{issue_num}")
            output_parts.append(issue_json[:3000])

    # PR comments / review feedback
    if feedback_text and feedback_text != "No review comments found.":
        output_parts.append(f"\n{feedback_text}")
    else:
        output_parts.append("\nNo review comments found.")

    # Diff
    output_parts.append(f"\n## Diff\n```diff\n{diff_out}\n```")

    output_parts.append(f"\nContextbook populated: issue_context, review_findings, status")

    return "\n".join(output_parts)


@tool
def fetch_issue_context(repo: str, issue_number: int, branch_prefix: str = "fix/issue-") -> str:
    """Fetch a GitHub issue, clone the repo, create a branch, and write contextbook.

    Does everything the Issue Analyst LLM agent does, but deterministically in one call.
    Returns structured output (REPO, BRANCH, ISSUE, MODULE, DETAILS).
    """
    import json as _json
    results = []

    def _run(cmd):
        proc = subprocess.run(cmd, shell=True, cwd=_cwd(), capture_output=True, text=True, timeout=120)
        return proc.stdout.strip(), proc.stderr.strip(), proc.returncode

    # 1. Fetch issue
    issue_out, err, rc = _run(
        f"gh issue view {issue_number} --repo {repo} "
        f"--json number,title,body,labels,state"
    )
    if rc != 0:
        return f"Error fetching issue #{issue_number}: {err}"

    try:
        issue_data = _json.loads(issue_out)
    except:
        issue_data = {"title": "?", "body": issue_out}

    title = issue_data.get("title", "?")
    author = "unknown"  # author field requires read:user scope
    body = issue_data.get("body", "")

    # 2. Clone and branch
    _run(f"gh repo clone {repo} .")
    _run("echo '.contextbook/' >> .gitignore && git add .gitignore && git commit -m 'chore: ignore contextbook'")
    branch = f"{branch_prefix}{issue_number}"
    _run(f"git checkout -b {branch}")
    _run(f"git push -u origin {branch}")

    # 3. Detect module from issue body keywords
    module = "unknown"
    for keyword, mod in [("server", "server"), ("sdk/python", "sdk/python"), ("python sdk", "sdk/python"),
                          ("typescript", "sdk/typescript"), ("ts sdk", "sdk/typescript"),
                          ("cli", "cli"), ("ui", "ui")]:
        if keyword.lower() in body.lower():
            module = mod
            break

    # 4. Write contextbook
    cb = _contextbook_dir()
    cb.mkdir(parents=True, exist_ok=True)
    (cb / "issue_context.md").write_text(issue_out, encoding="utf-8")
    (cb / "module_map.md").write_text(f"{module}: detected from issue body keywords", encoding="utf-8")

    # 5. Return FULL context — this becomes the downstream agent's input
    labels = [l.get("name", "") for l in issue_data.get("labels", [])]
    return (
        f"REPO: {repo}\n"
        f"BRANCH: {branch}\n"
        f"ISSUE: #{issue_number} {title}\n"
        f"MODULE: {module}\n"
        f"LABELS: {', '.join(labels) if labels else 'none'}\n"
        f"\n## Issue Body\n{body}\n"
        f"\nContextbook populated: issue_context, module_map"
    )


@tool
def create_pr(repo: str, issue_number: int, qa_evidence_dir: str = "qa-tests") -> str:
    """Commit remaining changes, push the branch, and create a pull request.

    Reads contextbook for issue context, change log, and change context.
    Builds the PR body with human-readable sections + machine-readable JSON.
    Returns the PR URL.
    """
    import json as _json
    results = []

    def _run(cmd):
        proc = subprocess.run(cmd, shell=True, cwd=_cwd(), capture_output=True, text=True, timeout=120)
        return proc.stdout.strip(), proc.stderr.strip(), proc.returncode

    cb = _contextbook_dir()

    # Read contextbook sections
    issue_ctx = ""
    if (cb / "issue_context.md").exists():
        issue_ctx = (cb / "issue_context.md").read_text(encoding="utf-8")
    change_log = ""
    if (cb / "change_log.md").exists():
        change_log = (cb / "change_log.md").read_text(encoding="utf-8")
    change_context = ""
    if (cb / "change_context.md").exists():
        change_context = (cb / "change_context.md").read_text(encoding="utf-8")
    test_results = ""
    if (cb / "test_results.md").exists():
        test_results = (cb / "test_results.md").read_text(encoding="utf-8")

    # Parse issue title from context
    title = f"Fix #{issue_number}"
    try:
        data = _json.loads(issue_ctx)
        title = f"Fix #{issue_number}: {data.get('title', '')}"
    except:
        pass

    # Stage, commit, push
    _run("git add -A -- ':!.contextbook'")
    status_out, _, _ = _run("git status --short")
    if status_out.strip():
        _run("git commit -m 'fix: final changes'")
        results.append("Committed remaining changes")

    branch_out, _, _ = _run("git branch --show-current")
    push_out, push_err, rc = _run("git push origin HEAD")
    if rc != 0:
        _run(f"git push --set-upstream origin {branch_out}")
    results.append(f"Pushed branch: {branch_out}")

    # Build PR body
    summary = change_log[:500] if change_log else "See commits for details."
    testing = test_results[:300] if test_results else "See QA evidence folder."

    body = (
        f"Fixes #{issue_number}\n\n"
        f"## Summary\n{summary}\n\n"
        f"## Testing\n{testing}\n\n"
        f"## QA Evidence\nSee `{qa_evidence_dir}/issue-{issue_number}/` for detailed test results.\n\n"
    )
    if change_context:
        body += (
            f"<details>\n<summary>Change Context (machine-readable)</summary>\n\n"
            f"```json\n{change_context[:3000]}\n```\n\n</details>\n"
        )

    # Create PR
    # Escape body for shell
    body_escaped = body.replace("'", "'\\''")
    pr_out, pr_err, rc = _run(
        f"gh pr create --repo {repo} --base main --head {branch_out} "
        f"--title '{title[:70]}' --body '{body_escaped}'"
    )

    if rc == 0 and "github.com" in pr_out:
        results.append(f"PR created: {pr_out}")
        return "\n".join(results) + f"\n\nPR_URL: {pr_out}"
    else:
        results.append(f"PR creation failed: {pr_err or pr_out}")
        return "\n".join(results)


@tool
def update_pr(repo: str, pr_number: int) -> str:
    """Push changes to the existing PR branch and add a comment summarizing what was addressed.

    Reads contextbook for change log, change context, and review findings.
    Pushes to the same branch and adds a PR comment with a feedback resolution table.
    """
    import json as _json
    results = []

    def _run(cmd):
        proc = subprocess.run(cmd, shell=True, cwd=_cwd(), capture_output=True, text=True, timeout=120)
        return proc.stdout.strip(), proc.stderr.strip(), proc.returncode

    cb = _contextbook_dir()

    # Read contextbook
    change_log = ""
    if (cb / "change_log.md").exists():
        change_log = (cb / "change_log.md").read_text(encoding="utf-8")
    change_context = ""
    if (cb / "change_context.md").exists():
        change_context = (cb / "change_context.md").read_text(encoding="utf-8")
    review_findings = ""
    if (cb / "review_findings.md").exists():
        review_findings = (cb / "review_findings.md").read_text(encoding="utf-8")

    # Stage, commit, push
    _run("git add -A -- ':!.contextbook'")
    status_out, _, _ = _run("git status --short")
    if status_out.strip():
        _run("git commit -m 'fix: address PR feedback'")
        results.append("Committed changes")

    _, _, rc = _run("git push origin HEAD")
    if rc != 0:
        branch_out, _, _ = _run("git branch --show-current")
        _run(f"git push --set-upstream origin {branch_out}")
    results.append("Pushed to branch")

    # Build PR comment
    comment = "## Feedback Addressed\n\n"
    if change_log:
        comment += f"### Changes Made\n{change_log[:1000]}\n\n"
    if change_context:
        comment += (
            f"<details>\n<summary>Change Context</summary>\n\n"
            f"```json\n{change_context[:2000]}\n```\n\n</details>\n"
        )

    # Post comment
    comment_escaped = comment.replace("'", "'\\''")
    _, err, rc = _run(
        f"gh pr comment {pr_number} --repo {repo} --body '{comment_escaped}'"
    )
    if rc == 0:
        results.append(f"Posted comment on PR #{pr_number}")
    else:
        results.append(f"Comment failed: {err}")

    # Get PR URL
    pr_out, _, _ = _run(f"gh pr view {pr_number} --repo {repo} --json url --jq .url")
    if pr_out:
        results.append(f"PR URL: {pr_out}")

    return "\n".join(results)
