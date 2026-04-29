# Issue Fixer Agent Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a multi-agent coding agent (`100_issue_fixer_agent.py`) that takes a GitHub issue number, autonomously analyzes the codebase, implements a fix with tests, and creates a PR.

**Architecture:** Pipeline-wrapped swarm — `issue_analyst >> coding_swarm >> pr_creator`. The swarm contains Tech Lead (Opus), Coder (Sonnet), DG Code Reviewer (skill agent), and QA Lead (Sonnet). All agents share a file-backed contextbook for durable team memory. Stateful workers with issue-number-based idempotency.

**Tech Stack:** Agentspan Python SDK (`Agent`, `Strategy.SWARM`, `skill()`, `agent_tool()`, `@tool`, `OnTextMention`, `TextMentionTermination`, `CliConfig`), Python 3.10+, subprocess, pathlib, ripgrep.

**Spec:** `docs/superpowers/specs/2026-04-23-issue-fixer-agent-design.md`

---

## File Structure

```
sdk/python/examples/
├── 100_issue_fixer_agent.py       # Main: constants, agents, pipeline, entry point (~250 lines)
├── _issue_fixer_tools.py          # All 21 @tool functions (~500 lines)
└── _issue_fixer_instructions.py   # All 6 agent instruction strings (~300 lines)
```

**Why 3 files:**
- `_issue_fixer_tools.py` — 21 tools is substantial; isolating them makes each tool independently readable and testable. Leading underscore because Python module names can't start with digits.
- `_issue_fixer_instructions.py` — 6 multi-paragraph prompt strings would clutter the main file. Isolated for easy iteration on prompts without touching agent wiring.
- `100_issue_fixer_agent.py` — clean orchestration: imports tools + instructions, wires agents, defines pipeline, entry point.

Follows the existing `kitchen_sink.py` / `kitchen_sink_helpers.py` pattern.

---

## Chunk 1: Tools Module

### Task 1: File operation tools

**Files:**
- Create: `sdk/python/examples/100_issue_fixer_tools.py`

- [ ] **Step 1: Create tools module with constants and imports**

```python
# sdk/python/examples/100_issue_fixer_tools.py
"""Reusable @tool functions for the Issue Fixer Agent.

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

# Limits
_MAX_FILE_BYTES = 500_000      # 500 KB
_MAX_OUTPUT_LINES = 200        # truncate long outputs
_MAX_COMMAND_OUTPUT = 16_000   # chars for command output
_DEFAULT_TIMEOUT = 120         # seconds for shell commands

# Module detection mapping: directory prefix -> module name
_MODULE_MAP = {
    "sdk/python": "sdk/python",
    "sdk/typescript": "sdk/typescript",
    "cli": "cli",
    "server": "server",
    "ui": "ui",
}
```

- [ ] **Step 2: Implement `read_file`**

```python
@tool
def read_file(path: str, start_line: int = 0, end_line: int = 0) -> str:
    """Read a file's contents with optional line range. Returns lines with line numbers.
    If start_line and end_line are both 0, reads the entire file."""
    target = Path(path)
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
```

- [ ] **Step 3: Implement `write_file`**

```python
@tool
def write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent directories as needed. Overwrites existing files."""
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote {len(content):,} bytes to {path!r}."
    except Exception as exc:
        return f"Error writing {path!r}: {exc}"
```

- [ ] **Step 4: Implement `edit_file`**

```python
@tool
def edit_file(path: str, old_string: str, new_string: str) -> str:
    """Replace exact text in a file. Fails if old_string is not found or matches more than once."""
    target = Path(path)
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
```

- [ ] **Step 5: Implement `apply_patch`**

```python
@tool
def apply_patch(patch: str, working_dir: str = ".") -> str:
    """Apply a unified diff patch. Returns success/failure details."""
    try:
        proc = subprocess.run(
            ["git", "apply", "--check", "-"],
            input=patch, capture_output=True, text=True,
            cwd=working_dir, timeout=30,
        )
        if proc.returncode != 0:
            return f"Error: patch would not apply cleanly:\n{proc.stderr.strip()}"
        proc = subprocess.run(
            ["git", "apply", "-"],
            input=patch, capture_output=True, text=True,
            cwd=working_dir, timeout=30,
        )
        if proc.returncode == 0:
            return "Patch applied successfully."
        return f"Error applying patch:\n{proc.stderr.strip()}"
    except Exception as exc:
        return f"Error: {exc}"
```

- [ ] **Step 6: Implement `list_directory`**

```python
@tool
def list_directory(path: str = ".", max_depth: int = 2) -> str:
    """List directory contents in tree format up to max_depth levels deep."""
    target = Path(path)
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
        # Skip hidden dirs and common noise
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
```

- [ ] **Step 7: Implement `file_outline`**

```python
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
    Works across Python, Go, Java, TypeScript, and React."""
    target = Path(path)
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
```

- [ ] **Step 8: Verify file operations compile**

Run: `cd sdk/python && python -c "from examples.issue_fixer_tools_100 import *; print('OK')" 2>&1 || python -c "import ast; ast.parse(open('examples/100_issue_fixer_tools.py').read()); print('Syntax OK')"`

Expected: No import or syntax errors. (May get import errors for `agentspan.agents` if server isn't running — syntax check is the minimum gate.)

- [ ] **Step 9: Commit**

```bash
git add sdk/python/examples/100_issue_fixer_tools.py
git commit -m "feat(examples): add file operation tools for issue fixer agent

Implements read_file, write_file, edit_file, apply_patch, list_directory,
and file_outline with polyglot support (Python, Go, Java, TypeScript, React)."
```

---

### Task 2: Search & navigation tools

**Files:**
- Modify: `sdk/python/examples/100_issue_fixer_tools.py`

- [ ] **Step 1: Implement `glob_find`**

```python
@tool
def glob_find(pattern: str, path: str = ".") -> str:
    """Find files matching a glob pattern (e.g. '**/*.py'). Returns sorted file paths."""
    base = Path(path)
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
```

- [ ] **Step 2: Implement `grep_search`**

```python
@tool
def grep_search(pattern: str, path: str = ".", glob_filter: str = "", max_results: int = 50) -> str:
    """Search file contents with regex pattern. Returns matching lines as file:line: content.
    Uses ripgrep (rg) for speed, falls back to Python regex if rg is not available."""
    rg = shutil.which("rg")
    if rg:
        cmd = [rg, "--no-heading", "--line-number", "--max-count", str(max_results), "--color", "never"]
        if glob_filter:
            cmd.extend(["--glob", glob_filter])
        cmd.extend([pattern, path])
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
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
    for filepath in sorted(Path(path).rglob(glob_filter or "*")):
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
```

- [ ] **Step 3: Implement `search_symbols`**

```python
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
    Returns file:line: definition_line."""
    if kind and kind not in _SYMBOL_DEF_PATTERNS:
        return f"Error: unknown kind {kind!r}. Use: class, function, type, interface, struct, or empty for all."
    patterns = {kind: _SYMBOL_DEF_PATTERNS[kind]} if kind else _SYMBOL_DEF_PATTERNS
    rg = shutil.which("rg")
    results = []
    for k, pat_template in patterns.items():
        pat = pat_template.format(name=re.escape(name))
        if rg:
            cmd = [rg, "--no-heading", "--line-number", "--color", "never", pat, path]
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if proc.returncode == 0:
                    for line in proc.stdout.strip().splitlines():
                        results.append(f"[{k}] {line}")
            except Exception:
                continue
        else:
            compiled = re.compile(pat)
            for filepath in sorted(Path(path).rglob("*")):
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
```

- [ ] **Step 4: Implement `find_references`**

```python
@tool
def find_references(symbol: str, path: str = ".") -> str:
    """Find all usages of a symbol (excludes definitions). Returns file:line: context.
    Useful for blast radius analysis — 'if I change this, what breaks?'"""
    rg = shutil.which("rg")
    if not rg:
        return "Error: ripgrep (rg) is required for find_references. Install it: brew install ripgrep"
    # Find all mentions
    cmd = [rg, "--no-heading", "--line-number", "--color", "never", "--word-regexp", symbol, path]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            return f"No references found for {symbol!r} in {path!r}."
        all_lines = proc.stdout.strip().splitlines()
    except Exception as exc:
        return f"Error: {exc}"

    # Filter out definitions (lines that look like def/class/func/type/interface declarations)
    def_pattern = re.compile(
        r"^\s*(?:export\s+)?(?:abstract\s+)?(?:public\s+)?(?:private\s+)?(?:protected\s+)?"
        r"(?:static\s+)?(?:async\s+)?(?:def|function|func|class|type|interface|struct|enum|const)\s+"
        + re.escape(symbol) + r"\b"
    )
    references = []
    for line in all_lines:
        # line format: file:lineno:content
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
```

- [ ] **Step 5: Commit**

```bash
git add sdk/python/examples/100_issue_fixer_tools.py
git commit -m "feat(examples): add search & navigation tools for issue fixer

Implements glob_find, grep_search (rg with Python fallback),
search_symbols (polyglot definition finder), and find_references
(usage/blast radius analysis)."
```

---

### Task 3: Git tools

**Files:**
- Modify: `sdk/python/examples/100_issue_fixer_tools.py`

- [ ] **Step 1: Implement `git_diff`**

```python
@tool
def git_diff(base: str = "main", path: str = "") -> str:
    """Show diff of current changes vs a base branch or commit.
    Optionally scoped to a specific file or directory."""
    cmd = ["git", "diff", base]
    if path:
        cmd.extend(["--", path])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = proc.stdout.strip()
        if not output:
            return f"No diff between current state and {base!r}" + (f" for {path!r}" if path else "") + "."
        if len(output) > _MAX_COMMAND_OUTPUT:
            output = output[:_MAX_COMMAND_OUTPUT] + f"\n... (truncated, {len(output):,} chars total)"
        return output
    except Exception as exc:
        return f"Error: {exc}"
```

- [ ] **Step 2: Implement `git_log`**

```python
@tool
def git_log(path: str = "", max_count: int = 20) -> str:
    """Show recent commit history. Optionally scoped to a file/directory."""
    cmd = ["git", "log", f"--max-count={max_count}", "--format=%h %ad %an: %s", "--date=short"]
    if path:
        cmd.extend(["--", path])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return proc.stdout.strip() or "No commits found."
    except Exception as exc:
        return f"Error: {exc}"
```

- [ ] **Step 3: Implement `git_blame`**

```python
@tool
def git_blame(path: str, start_line: int = 0, end_line: int = 0) -> str:
    """Show who last modified each line of a file. Optionally scoped to a line range."""
    cmd = ["git", "blame", "--date=short"]
    if start_line and end_line:
        cmd.extend([f"-L{start_line},{end_line}"])
    cmd.append(path)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            return f"Error: {proc.stderr.strip()}"
        return proc.stdout.strip() or f"No blame data for {path!r}."
    except Exception as exc:
        return f"Error: {exc}"
```

- [ ] **Step 4: Commit**

```bash
git add sdk/python/examples/100_issue_fixer_tools.py
git commit -m "feat(examples): add git tools for issue fixer (diff, log, blame)"
```

---

### Task 4: Build & test tools

**Files:**
- Modify: `sdk/python/examples/100_issue_fixer_tools.py`

- [ ] **Step 1: Add module detection helper**

```python
def _detect_module(path: str) -> str:
    """Detect which monorepo module a path belongs to."""
    for prefix, module in _MODULE_MAP.items():
        if path.startswith(prefix):
            return module
    return ""
```

- [ ] **Step 2: Implement `lint_and_format`**

```python
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
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=_DEFAULT_TIMEOUT)
        output = (proc.stdout + proc.stderr).strip()
        if len(output) > _MAX_COMMAND_OUTPUT:
            output = output[:_MAX_COMMAND_OUTPUT] + "\n... (truncated)"
        status = "OK" if proc.returncode == 0 else f"ISSUES (exit {proc.returncode})"
        return f"[{resolved}] lint_and_format: {status}\n{output}"
    except Exception as exc:
        return f"Error: {exc}"
```

- [ ] **Step 3: Implement `build_check`**

```python
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
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=_DEFAULT_TIMEOUT)
        output = (proc.stdout + proc.stderr).strip()
        if len(output) > _MAX_COMMAND_OUTPUT:
            output = output[:_MAX_COMMAND_OUTPUT] + "\n... (truncated)"
        status = "PASS" if proc.returncode == 0 else f"FAIL (exit {proc.returncode})"
        return f"[{module}] build_check: {status}\n{output}"
    except Exception as exc:
        return f"Error: {exc}"
```

- [ ] **Step 4: Implement `run_unit_tests`**

```python
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
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=600)
        output = (proc.stdout + proc.stderr).strip()
        if len(output) > _MAX_COMMAND_OUTPUT:
            output = output[:_MAX_COMMAND_OUTPUT] + "\n... (truncated)"
        status = "PASS" if proc.returncode == 0 else f"FAIL (exit {proc.returncode})"
        return f"[{module}] unit_tests: {status}\n{output}"
    except subprocess.TimeoutExpired:
        return f"Error: tests timed out after 600s."
    except Exception as exc:
        return f"Error: {exc}"
```

- [ ] **Step 5: Implement `run_e2e_tests`**

```python
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
```

- [ ] **Step 6: Commit**

```bash
git add sdk/python/examples/100_issue_fixer_tools.py
git commit -m "feat(examples): add build & test tools for issue fixer

Implements lint_and_format, build_check, run_unit_tests, run_e2e_tests
with polyglot module detection and auto-command selection."
```

---

### Task 5: Contextbook tools and run_command

**Files:**
- Modify: `sdk/python/examples/100_issue_fixer_tools.py`

- [ ] **Step 1: Implement contextbook tools**

```python
# Contextbook directory — created alongside the repo clone
_CONTEXTBOOK_DIR = Path(".contextbook")
_VALID_SECTIONS = {
    "issue_context", "module_map", "implementation_plan", "test_plan",
    "change_log", "review_findings", "test_results", "decisions", "status",
}


@tool(stateful=True)
def contextbook_write(section: str, content: str, append: bool = False) -> str:
    """Write to a named section of the team contextbook.
    Sections: issue_context, module_map, implementation_plan, test_plan,
    change_log, review_findings, test_results, decisions, status.
    append=True adds to existing content; append=False replaces the section."""
    if section not in _VALID_SECTIONS:
        return f"Error: invalid section {section!r}. Valid: {', '.join(sorted(_VALID_SECTIONS))}"
    _CONTEXTBOOK_DIR.mkdir(exist_ok=True)
    filepath = _CONTEXTBOOK_DIR / f"{section}.md"
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
    if not _CONTEXTBOOK_DIR.exists():
        return "Contextbook is empty. No sections written yet."
    if not section:
        # Table of contents
        toc = []
        for name in sorted(_VALID_SECTIONS):
            filepath = _CONTEXTBOOK_DIR / f"{name}.md"
            if filepath.exists():
                first_line = filepath.read_text(encoding="utf-8").split("\n")[0][:100]
                size = filepath.stat().st_size
                toc.append(f"  [{name}] ({size:,} chars) — {first_line}")
            else:
                toc.append(f"  [{name}] (empty)")
        return "Contextbook sections:\n" + "\n".join(toc)
    if section not in _VALID_SECTIONS:
        return f"Error: invalid section {section!r}. Valid: {', '.join(sorted(_VALID_SECTIONS))}"
    filepath = _CONTEXTBOOK_DIR / f"{section}.md"
    if not filepath.exists():
        return f"Section '{section}' has not been written yet."
    return filepath.read_text(encoding="utf-8")


@tool(stateful=True)
def contextbook_summary() -> str:
    """Returns a condensed summary of ALL contextbook sections.
    Designed to be called after context compaction or crash recovery for quick re-orientation."""
    if not _CONTEXTBOOK_DIR.exists():
        return "Contextbook is empty. No sections written yet."
    summary_parts = []
    for name in sorted(_VALID_SECTIONS):
        filepath = _CONTEXTBOOK_DIR / f"{name}.md"
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8")
            # Take first 500 chars as summary
            preview = content[:500]
            if len(content) > 500:
                preview += f"\n... ({len(content):,} chars total)"
            summary_parts.append(f"=== {name.upper()} ===\n{preview}")
    if not summary_parts:
        return "Contextbook is empty. No sections written yet."
    return "\n\n".join(summary_parts)
```

- [ ] **Step 2: Implement `run_command`**

```python
@tool
def run_command(command: str, working_dir: str = "", timeout: int = 300) -> str:
    """Execute a shell command and return stdout+stderr with exit code.
    working_dir defaults to current directory if empty."""
    cwd = working_dir or None
    try:
        proc = subprocess.run(
            command, shell=True, cwd=cwd,
            capture_output=True, text=True,
            timeout=min(timeout, 600),  # cap at 10 min
        )
        output = (proc.stdout + proc.stderr).strip()
        if len(output) > _MAX_COMMAND_OUTPUT:
            output = output[:_MAX_COMMAND_OUTPUT] + f"\n... (truncated, {len(output):,} chars total)"
        return f"[exit {proc.returncode}]\n{output}" if output else f"[exit {proc.returncode}] (no output)"
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s."
    except Exception as exc:
        return f"Error: {exc}"
```

- [ ] **Step 3: Verify complete tools module compiles**

Run: `cd sdk/python && python -c "import ast; ast.parse(open('examples/100_issue_fixer_tools.py').read()); print('21 tools — syntax OK')"`

Expected: `21 tools — syntax OK`

- [ ] **Step 4: Commit**

```bash
git add sdk/python/examples/100_issue_fixer_tools.py
git commit -m "feat(examples): add contextbook and run_command tools for issue fixer

Implements contextbook_write/read/summary (file-backed durable team memory)
and run_command (general shell execution). Tools module complete: 21 tools."
```

---

## Chunk 2: Instructions & Agent Assembly

### Task 6: Agent instruction strings

**Files:**
- Create: `sdk/python/examples/100_issue_fixer_instructions.py`

- [ ] **Step 1: Write Issue Analyst instructions**

Create `sdk/python/examples/100_issue_fixer_instructions.py` with:

```python
"""Agent instruction strings for the Issue Fixer Agent.

Each constant is a multi-line prompt string used as the `instructions` parameter
for one of the 6 agents in the pipeline. Separated from agent wiring for clarity.
"""

# Placeholder for REPO — replaced at import time by the main module
# Instructions use {repo} and {branch_prefix} format strings.

ISSUE_ANALYST_INSTRUCTIONS = """\
You fetch a GitHub issue and prepare the repo for fixing.

FIRST: Call contextbook_read() to check if work has already started.

Step 1 — Fetch the issue:
  Run: gh issue view <N> --repo {repo} --json number,title,body,author,labels,comments
  Read the full output carefully.

Step 2 — Clone and create branch:
  Run: TMPDIR=$(mktemp -d) && gh repo clone {repo} "$TMPDIR" && cd "$TMPDIR" && git checkout -b {branch_prefix}<N> && git push -u origin {branch_prefix}<N> && pwd

Step 3 — Identify the affected module:
  Scan the issue body for keywords: "server", "sdk", "python", "typescript", "cli", "ui".
  Run: ls to see top-level directories.
  Determine which module(s) need changes: server/, sdk/python/, sdk/typescript/, cli/, ui/.
  If unclear, set MODULE: unknown.

Step 4 — Write to contextbook:
  contextbook_write("issue_context", "<full issue JSON output>")
  contextbook_write("module_map", "<identified modules and rationale>")

Step 5 — Output ONLY these lines (no tool calls after this):
  REPO: {repo}
  BRANCH: {branch_prefix}<N>
  ISSUE: #<N> <title>
  AUTHOR: <who opened the issue>
  MODULE: <primary module>
  DETAILS: <one-paragraph summary>

RULES:
- Do NOT create files, commits, or pull requests.
- After step 5, STOP using tools entirely.
"""
```

- [ ] **Step 2: Write Tech Lead instructions**

```python
TECH_LEAD_INSTRUCTIONS = """\
You are the Tech Lead. You analyze the codebase and create a detailed implementation plan.

FIRST: Call contextbook_read() to see current project state.

STEP 1 — Understand the issue:
  Read contextbook sections: issue_context, module_map.
  Understand the requirements, acceptance criteria, and affected modules.

STEP 2 — Deep-dive into the codebase:
  Use read_file, file_outline, search_symbols, find_references, grep_search
  to understand the code architecture in the affected module(s).
  Trace call chains. Understand how the broken component fits into the system.
  Use git_log and git_blame to understand recent changes and code ownership.

STEP 3 — Review e2e test patterns:
  Read sdk/python/e2e/conftest.py to understand test infrastructure.
  Read 2-3 existing test_suite*.py files to understand assertion patterns.
  Note: tests must be real e2e (no mocks), algorithmic assertions (no LLM parsing).

STEP 4 — Write the implementation plan:
  contextbook_write("implementation_plan", plan) with:
  - Root cause analysis
  - Step-by-step fix: specific files, functions, what to change and why
  - Risks and edge cases
  - Dependencies between changes

STEP 5 — Write the test plan skeleton:
  contextbook_write("test_plan", plan) with:
  - Which existing e2e suites are relevant
  - What new test cases are needed
  - Acceptance criteria per test (deterministic, no mocks)

STEP 6 — Update status and hand off:
  contextbook_write("status", "Plan complete. Ready for implementation.")
  Say HANDOFF_TO_CODER
"""
```

- [ ] **Step 3: Write Coder instructions**

```python
CODER_INSTRUCTIONS = """\
You are the Coder. You implement fixes and write tests per the plans.

FIRST: Call contextbook_read() to see current project state.
Read implementation_plan and/or test_plan depending on your current task.

MODE: IMPLEMENTATION (when handed off from Tech Lead or after DG review feedback)
  1. Read implementation_plan from contextbook.
  2. Implement the fix step by step.
  3. After each file change, run lint_and_format for the affected module.
  4. After all changes, run build_check for the affected module.
  5. Append each change to contextbook: contextbook_write("change_log", "...", append=True)
  6. Commit changes: git add <files> && git commit -m "fix: <description>"
  7. Say HANDOFF_TO_DG

MODE: WRITING TESTS (when handed off from QA Lead with test_plan)
  1. Read test_plan from contextbook.
  2. Write tests following the e2e patterns in sdk/python/e2e/.
  3. RULES for tests:
     - No mocks. All tests must run against a live server.
     - No LLM output parsing for assertions. Use algorithmic/deterministic checks.
     - Use deterministic tools with known outputs.
     - Follow existing conftest.py fixtures (runtime, model, verify_server).
  4. Run run_unit_tests to verify tests compile and basic structure is correct.
  5. Append test files to change_log.
  6. Say HANDOFF_TO_QA

MODE: FIX FEEDBACK (when handed off from DG or QA with review_findings)
  1. Read review_findings from contextbook.
  2. Fix each issue identified.
  3. Re-run lint_and_format and build_check.
  4. Update change_log.
  5. Hand off back to whoever sent you (HANDOFF_TO_DG or HANDOFF_TO_QA).

IMPORTANT: If you've been through {max_review_cycles} review cycles without resolution,
say HANDOFF_TO_TECH_LEAD — the plan may need rethinking.
"""
```

- [ ] **Step 4: Write DG Reviewer instructions**

```python
DG_REVIEWER_INSTRUCTIONS = """\
You are the Code Review Coordinator. You orchestrate adversarial code reviews using the DG skill.

FIRST: Call contextbook_read() to see current project state.

STEP 1 — Gather context:
  Read contextbook: implementation_plan, change_log.
  Run git_diff to see all code changes.

STEP 2 — Prepare review input:
  Collect the full diff and relevant context (what the plan was, what files changed).

STEP 3 — Run adversarial review:
  Call the dg_reviewer tool with the diff and context.
  The DG skill will run an internal Dinesh vs Gilfoyle debate and return findings.

STEP 4 — Evaluate and record findings:
  Write findings to contextbook: contextbook_write("review_findings", findings)

STEP 5 — Decision:
  If CRITICAL issues found (security, correctness, design flaws):
    Say HANDOFF_TO_CODER with specific issues to fix.
  If only minor/style issues or approved:
    Say HANDOFF_TO_QA

Track review cycles. If this is the {max_review_cycles}th review and issues persist,
say HANDOFF_TO_TECH_LEAD — the approach may be fundamentally wrong.
"""
```

- [ ] **Step 5: Write QA Lead instructions**

```python
QA_LEAD_INSTRUCTIONS = """\
You are the QA Lead. You plan tests, review test quality, and gate the PR with full e2e.

FIRST: Call contextbook_read() to see current project state.

MODE: TEST PLANNING (after DG approves code)
  1. Read contextbook: implementation_plan, change_log, review_findings.
  2. Study existing e2e test patterns:
     - Read sdk/python/e2e/conftest.py for fixtures and helpers.
     - Read 1-2 test_suite*.py files similar to what you need.
  3. Write detailed test_plan to contextbook:
     - Which existing suites must still pass
     - New test cases with specific assertions
     - Each test must be: real e2e (no mocks), deterministic, algorithmic
  4. Say HANDOFF_TO_CODER to write the tests.

MODE: TEST REVIEW (after Coder writes tests)
  1. Read the new test files.
  2. Validate EACH test against these rules:
     a. NO MOCKS — tests must hit a real server, not fakes.
     b. NO LLM OUTPUT PARSING — don't assert on LLM text content.
     c. ALGORITHMIC ASSERTIONS — use status codes, task counts, output keys.
     d. COUNTERFACTUAL — each test must be able to fail. Consider: if the bug
        were still present, would this test actually catch it?
  3. If quality issues found:
     Write review_findings to contextbook, say HANDOFF_TO_CODER.
  4. If tests look good:
     Run run_e2e_tests (full suite, sdk="both").
  5. If e2e PASSES:
     contextbook_write("test_results", "ALL PASSED: <summary>")
     contextbook_write("status", "All tests pass. Ready for PR.")
     Say SWARM_COMPLETE
  6. If e2e FAILS:
     contextbook_write("test_results", "<failure details>")
     Say HANDOFF_TO_CODER with the specific failures.

Track e2e attempts. After {max_e2e_retries} failed e2e runs, stop and report the situation.
Do NOT endlessly retry.
"""
```

- [ ] **Step 6: Write PR Creator instructions**

```python
PR_CREATOR_INSTRUCTIONS = """\
You create a pull request summarizing the fix.

FIRST: Call contextbook_read() to see the full context.

STEP 1 — Read context:
  Read contextbook: issue_context, implementation_plan, change_log, test_results.

STEP 2 — Stage and commit:
  Run: git add -A && git status
  If there are uncommitted changes, commit with a descriptive message.

STEP 3 — Push branch:
  Run: git push origin HEAD

STEP 4 — Create PR:
  Run: gh pr create --repo {repo} --base main --head <BRANCH> \\
    --title "Fix #<N>: <short description>" \\
    --body "<PR body with: summary of fix, what was changed, testing done, Fixes #N>"

STEP 5 — Output the PR URL and stop.

RULES:
- Include "Fixes #<N>" in the PR body so GitHub auto-closes the issue.
- After outputting the PR URL, STOP. Do not call any more tools.
"""
```

- [ ] **Step 7: Verify instructions module compiles**

Run: `cd sdk/python && python -c "import ast; ast.parse(open('examples/100_issue_fixer_instructions.py').read()); print('6 instructions — syntax OK')"`

- [ ] **Step 8: Commit**

```bash
git add sdk/python/examples/100_issue_fixer_instructions.py
git commit -m "feat(examples): add agent instructions for issue fixer

Six detailed prompt strings: Issue Analyst, Tech Lead, Coder,
DG Reviewer, QA Lead, PR Creator. Parameterized with {repo},
{branch_prefix}, {max_review_cycles}, {max_e2e_retries}."
```

---

### Task 7: Main agent file — constants, agents, pipeline, entry point

**Files:**
- Create: `sdk/python/examples/100_issue_fixer_agent.py`

- [ ] **Step 1: Write the main module with constants and imports**

```python
#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Issue Fixer Agent — autonomous GitHub issue to PR pipeline.

A multi-agent coding agent that takes a GitHub issue number, analyzes the
codebase, implements a fix with tests, and creates a pull request.

Architecture: Pipeline-wrapped swarm
    Issue Analyst >> [SWARM: Tech Lead <-> Coder <-> DG <-> QA Lead] >> PR Creator

Usage:
    python 100_issue_fixer_agent.py <issue_number>
    python 100_issue_fixer_agent.py 42

Requirements:
    - Agentspan server running
    - GITHUB_TOKEN: agentspan credentials set GITHUB_TOKEN <your-token>
    - gh CLI installed and authenticated
    - DG skill: git clone https://github.com/v1r3n/dinesh-gilfoyle ~/.claude/skills/dg
    - Full build toolchain (Go, Java 21, Python 3.10+, Node.js, pnpm, uv)
"""

import sys

from agentspan.agents import Agent, AgentRuntime, Strategy, skill, agent_tool
from agentspan.agents.cli_config import CliConfig
from agentspan.agents.handoff import OnTextMention
from agentspan.agents.termination import TextMentionTermination

from _issue_fixer_tools import (
    read_file, write_file, edit_file, apply_patch, list_directory, file_outline,
    glob_find, grep_search, search_symbols, find_references,
    git_diff, git_log, git_blame,
    lint_and_format, build_check, run_unit_tests, run_e2e_tests,
    contextbook_write, contextbook_read, contextbook_summary,
    run_command,
)

# ── Project-Specific Configuration ────────────────────────────
REPO = "agentspan-ai/agentspan"
REPO_URL = f"https://github.com/{REPO}"
BRANCH_PREFIX = "fix/issue-"

# ── Models ────────────────────────────────────────────────────
OPUS = "anthropic/claude-opus-4-6"
SONNET = "anthropic/claude-sonnet-4-6"

# ── Credentials ──────────────────────────────────────────────
GITHUB_CREDENTIAL = "GITHUB_TOKEN"

# ── Skill Paths ──────────────────────────────────────────────
DG_SKILL_PATH = "~/.claude/skills/dg"

# ── Server ───────────────────────────────────────────────────
SERVER_URL = "http://localhost:6767"

# ── Timeouts & Limits ────────────────────────────────────────
SWARM_MAX_TURNS = 500
SWARM_TIMEOUT = 14400          # 4 hours
E2E_TOOL_TIMEOUT = 5400        # 90 min — full e2e suite with margin
MAX_REVIEW_CYCLES = 3
MAX_E2E_RETRIES = 3
```

- [ ] **Step 2: Import and format instructions**

```python
from _issue_fixer_instructions import (
    ISSUE_ANALYST_INSTRUCTIONS,
    TECH_LEAD_INSTRUCTIONS,
    CODER_INSTRUCTIONS,
    DG_REVIEWER_INSTRUCTIONS,
    QA_LEAD_INSTRUCTIONS,
    PR_CREATOR_INSTRUCTIONS,
)

# Format instruction templates with project constants
_fmt = {
    "repo": REPO,
    "branch_prefix": BRANCH_PREFIX,
    "max_review_cycles": MAX_REVIEW_CYCLES,
    "max_e2e_retries": MAX_E2E_RETRIES,
}
```

- [ ] **Step 3: Define stop conditions**

```python
def _issue_analyzed(context: dict, **kwargs) -> bool:
    """Stop Issue Analyst when structured output is produced."""
    result = context.get("result", "")
    return all(tag in result for tag in ("REPO:", "BRANCH:", "ISSUE:", "MODULE:"))


def _pr_created(context: dict, **kwargs) -> bool:
    """Stop PR Creator when a PR URL is output."""
    result = context.get("result", "")
    return "github.com" in result and "/pull/" in result
```

- [ ] **Step 4: Define all 6 agents**

```python
# ── Stage 1: Issue Analyst ────────────────────────────────────

issue_analyst = Agent(
    name="issue_analyst",
    model=SONNET,
    stateful=True,
    max_turns=20,
    max_tokens=8192,
    credentials=[GITHUB_CREDENTIAL],
    cli_config=CliConfig(
        allowed_commands=["gh", "git", "mktemp", "ls", "find"],
        allow_shell=True,
        timeout=60,
    ),
    tools=[contextbook_write, contextbook_read],
    stop_when=_issue_analyzed,
    instructions=ISSUE_ANALYST_INSTRUCTIONS.format(**_fmt),
)

# ── Stage 2: Swarm agents ────────────────────────────────────

tech_lead = Agent(
    name="tech_lead",
    model=OPUS,
    stateful=True,
    max_turns=30,
    max_tokens=60000,
    tools=[
        read_file, grep_search, glob_find, list_directory,
        file_outline, search_symbols, find_references,
        git_log, git_blame, run_command,
        contextbook_write, contextbook_read, contextbook_summary,
    ],
    instructions=TECH_LEAD_INSTRUCTIONS.format(**_fmt),
)

coder = Agent(
    name="coder",
    model=SONNET,
    stateful=True,
    max_turns=100,
    max_tokens=60000,
    credentials=[GITHUB_CREDENTIAL],
    cli_config=CliConfig(
        allowed_commands=["git"],
        allow_shell=True,
        timeout=120,
    ),
    tools=[
        read_file, write_file, edit_file, apply_patch,
        grep_search, glob_find, list_directory,
        file_outline, search_symbols, find_references,
        git_diff, git_log, run_command,
        lint_and_format, build_check, run_unit_tests,
        contextbook_write, contextbook_read, contextbook_summary,
    ],
    instructions=CODER_INSTRUCTIONS.format(**_fmt),
)

# DG skill + coordinator wrapper
dg_skill = skill(
    DG_SKILL_PATH,
    model=SONNET,
    agent_models={"gilfoyle": OPUS, "dinesh": SONNET},
)

dg_reviewer = Agent(
    name="dg_reviewer",
    model=SONNET,
    stateful=True,
    max_turns=15,
    max_tokens=60000,
    tools=[
        agent_tool(dg_skill, description="Run adversarial Dinesh vs Gilfoyle code review"),
        read_file, grep_search, git_diff, file_outline,
        contextbook_write, contextbook_read, contextbook_summary,
    ],
    instructions=DG_REVIEWER_INSTRUCTIONS.format(**_fmt),
)

qa_lead = Agent(
    name="qa_lead",
    model=SONNET,
    stateful=True,
    max_turns=40,
    max_tokens=60000,
    tools=[
        read_file, grep_search, glob_find, list_directory,
        file_outline, git_diff, run_command,
        run_unit_tests, run_e2e_tests,
        contextbook_write, contextbook_read, contextbook_summary,
    ],
    instructions=QA_LEAD_INSTRUCTIONS.format(**_fmt),
)
```

- [ ] **Step 5: Assemble swarm and pipeline**

```python
# ── Swarm assembly ────────────────────────────────────────────

coding_swarm = Agent(
    name="coding_swarm",
    model=SONNET,
    stateful=True,
    strategy=Strategy.SWARM,
    agents=[tech_lead, coder, dg_reviewer, qa_lead],
    handoffs=[
        OnTextMention(text="HANDOFF_TO_CODER", target="coder"),
        OnTextMention(text="HANDOFF_TO_DG", target="dg_reviewer"),
        OnTextMention(text="HANDOFF_TO_QA", target="qa_lead"),
        OnTextMention(text="HANDOFF_TO_TECH_LEAD", target="tech_lead"),
    ],
    termination=TextMentionTermination("SWARM_COMPLETE"),
    max_turns=SWARM_MAX_TURNS,
    max_tokens=60000,
    timeout_seconds=SWARM_TIMEOUT,
    instructions="Start with tech_lead. Iterate until QA Lead confirms ALL_TESTS_PASS.",
)

# ── Stage 3: PR Creator ──────────────────────────────────────

pr_creator = Agent(
    name="pr_creator",
    model=SONNET,
    stateful=True,
    max_turns=10,
    max_tokens=8192,
    credentials=[GITHUB_CREDENTIAL],
    cli_config=CliConfig(
        allowed_commands=["gh", "git"],
        allow_shell=True,
        timeout=60,
    ),
    tools=[git_diff, git_log, contextbook_read],
    stop_when=_pr_created,
    instructions=PR_CREATOR_INSTRUCTIONS.format(**_fmt),
)

# ── Full pipeline ─────────────────────────────────────────────

pipeline = issue_analyst >> coding_swarm >> pr_creator
```

- [ ] **Step 6: Write entry point**

```python
def main():
    if len(sys.argv) < 2:
        print("Usage: python 100_issue_fixer_agent.py <issue_number>")
        sys.exit(1)

    issue_number = int(sys.argv[1])
    idempotency_key = f"issue-{issue_number}"

    with AgentRuntime() as rt:
        handle = rt.start(
            pipeline,
            f"Fix issue #{issue_number} from {REPO}",
            idempotency_key=idempotency_key,
        )
        print(f"Execution started: {handle.execution_id}")
        print(f"Idempotency key: {idempotency_key}")
        print(f"Monitor at: {SERVER_URL}/execution/{handle.execution_id}")

        rt.serve(pipeline)


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Verify syntax of all 3 files**

Run: `cd sdk/python/examples && python -c "import ast; [ast.parse(open(f).read()) for f in ('_issue_fixer_tools.py', '_issue_fixer_instructions.py', '100_issue_fixer_agent.py')]; print('All 3 files — syntax OK')"`

- [ ] **Step 8: Commit**

```bash
git add sdk/python/examples/100_issue_fixer_agent.py sdk/python/examples/_issue_fixer_tools.py sdk/python/examples/_issue_fixer_instructions.py
git commit -m "feat(examples): add issue fixer agent — autonomous issue-to-PR pipeline

Multi-agent coding agent: pipeline-wrapped swarm with Tech Lead (Opus),
Coder (Sonnet), DG Code Reviewer (skill agent), QA Lead (Sonnet).
21 custom tools, file-backed contextbook, stateful workers, idempotency.

Usage: python 100_issue_fixer_agent.py <issue_number>"
```

---

## Chunk 3: Verification

### Task 8: Smoke test — plan compilation

**Files:**
- No new files — uses existing `runtime.plan()` API

- [ ] **Step 1: Verify plan compiles**

Run: `cd sdk/python/examples && python -c "
from agentspan.agents import AgentRuntime
# Can't fully test without server, but verify the agent definitions load
import ast
for f in ('_issue_fixer_tools.py', '_issue_fixer_instructions.py', '100_issue_fixer_agent.py'):
    ast.parse(open(f).read())
print('All files parse successfully')
print('Agent definitions are syntactically valid')
print('Pipeline construction will be verified when server is available')
"`

Expected: `All files parse successfully`

- [ ] **Step 2: Verify with running server (if available)**

Run: `cd sdk/python/examples && python -c "
import os
os.environ.setdefault('AGENTSPAN_AUTO_START_SERVER', 'false')
try:
    from agentspan.agents import AgentRuntime
    # Import the pipeline (will try to load DG skill)
    # If DG skill isn't cloned, this will fail — that's expected
    print('SDK imports work')
except Exception as e:
    print(f'Note: {e} — expected if server/skill not available')
"`

- [ ] **Step 3: Final commit with any fixes**

If any issues found during verification, fix and commit:

```bash
git add -A
git commit -m "fix(examples): address verification issues in issue fixer agent"
```

---

## Summary

| Chunk | Tasks | Files | Description |
|---|---|---|---|
| 1 | Tasks 1-5 | `sdk/python/examples/_issue_fixer_tools.py` | 21 @tool functions (file, search, git, build, contextbook) |
| 2 | Tasks 6-7 | `sdk/python/examples/_issue_fixer_instructions.py`, `sdk/python/examples/100_issue_fixer_agent.py` | 6 instruction strings, agent definitions, pipeline, entry point |
| 3 | Task 8 | (none) | Syntax verification and plan compilation smoke test |

Total: ~1,050 lines across 3 files, 8 tasks, ~30 steps.
