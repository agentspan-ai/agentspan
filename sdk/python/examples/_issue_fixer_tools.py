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

import contextlib
import fcntl
import json
import os
import re
import shutil
import subprocess
import tempfile
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
# Inspection / edit-seen / validation state used to live in these module-level
# dicts. They were per-process and the worker pool is multiprocess (spawn mode,
# see ``runtime/worker_manager.py`` and ``runtime/_dispatch.py``). So the 10-call
# budget never accumulated past ~1-2 in any single worker process and the gate
# never fired — observed in workflow ``fb257ccd-e3e2-468e-9a4b-50b0b3284b15``
# where 408 inspections ran with 0 blocked, the coder never converged on
# editing. State now lives in ``.contextbook/.progress/<exec_id>.json`` keyed
# by execution_id, mutated under ``fcntl.flock`` so every worker process sees
# the same counter. See ``_progress_locked`` below.


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
        _read_file_count.clear()


# ── Working directory ──────────────────────────────────────────

# Workers in spawn-mode multiprocessing re-import this module fresh, so
# ``_WORKING_DIR`` (a module global) is the empty default in each worker. The
# SDK never explicitly chdirs workers, so ``Path.cwd()`` fallback resolves to
# the SDK process's launch directory — which is NOT the work_dir. Pass the
# value through the environment instead: ``set_working_dir`` writes
# ``AGENTSPAN_FIXER_WORKING_DIR`` and ``_get_working_dir`` reads it. Env vars
# are inherited by spawned worker processes, so every worker resolves the
# same path the SDK does.
_AGENTSPAN_WORKING_DIR_ENV = "AGENTSPAN_FIXER_WORKING_DIR"
_WORKING_DIR: str = os.environ.get(_AGENTSPAN_WORKING_DIR_ENV, "")


def set_working_dir(path: str) -> None:
    """Set the shared working directory for all tools.

    Must be called before any agent runs. Typically a temp folder where
    the target repo will be cloned into by the Issue Analyst. The value is
    also written to ``AGENTSPAN_FIXER_WORKING_DIR`` so worker processes that
    re-import this module pick it up automatically.
    """
    global _WORKING_DIR, _last_execution_id
    _WORKING_DIR = str(path)
    os.environ[_AGENTSPAN_WORKING_DIR_ENV] = _WORKING_DIR
    os.makedirs(_WORKING_DIR, exist_ok=True)
    _last_execution_id = ""
    _file_read_hashes.clear()
    _grep_cache.clear()
    _symbol_read_hashes.clear()
    _read_file_cache.clear()
    _read_file_count.clear()
    try:
        _REPO_COMMANDS.clear()
    except NameError:
        pass  # tool may not have been imported yet on first call
    # Clear the per-execution repo-docs cache so a switch to a new
    # working directory re-discovers AGENTS.md / CLAUDE.md fresh.
    try:
        _repo_docs_cache.clear()
    except NameError:
        pass  # tool may not have been imported yet on first call


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
_MAX_REPEAT_FILE_READS = 3  # hard stop per file per agent execution
_CODER_INSPECTION_BUDGET_BEFORE_EDIT = 100
_SUBAGENT_VALIDATION_BUDGET = 8

_RUN_COMMAND_INSPECTION_PATTERNS = [
    re.compile(r"(^|[;&|]\s*|\s)(cat|sed|head|tail|awk|grep|rg|find|ls)\b"),
    re.compile(r"\bpython3?\s+-c\b"),
    re.compile(r"\bgit\s+(?:grep|show|ls-files|blame)\b"),
    re.compile(r"\bgit\s+log\b.*(?:--patch|-p|-G|-S)\b"),
]
_RUN_COMMAND_INSPECTION_BLOCK = (
    "Blocked: run_command is only for build/test/lint/status commands. "
    "Use read_file, grep_search, glob_find, list_directory, file_outline, "
    "read_symbol, git_status, or git_diff for inspection."
)
_VALIDATION_COMMAND_INSPECTION_PATTERNS = [
    *_RUN_COMMAND_INSPECTION_PATTERNS,
    re.compile(r"\bgit\s+(?:status|diff)\b"),
]
_VALIDATION_COMMAND_INSPECTION_BLOCK = (
    "Blocked: validation tools only run build/test/lint commands. "
    "Use read_file, grep_search, glob_find, list_directory, file_outline, "
    "read_symbol, git_status, or git_diff for inspection."
)

# Dedup: track file reads to block redundant re-reads
_file_read_hashes: dict[str, int] = {}  # resolved path -> content hash
_symbol_read_hashes: dict[str, int] = {}  # "resolved_path:symbol" -> content hash
_read_file_cache: dict[str, tuple[int, int]] = {}  # resolved path -> (size_bytes, line_count)
_read_file_count: dict[str, int] = {}  # resolved path -> times read this execution

# Auto-discovered at runtime by _discover_repo_conventions()
_BASE_BRANCH: str = "main"
_REPO_COMMANDS: dict[str, str] = {}  # keys: lint, build, test


def _ensure_repo_commands() -> None:
    """Populate repo commands on demand in the current worker process."""
    if _REPO_COMMANDS:
        return
    base = Path(_WORKING_DIR) if _WORKING_DIR else Path.cwd()
    _detect_build_commands(base)


def _block_validation_inspection(command: str) -> str | None:
    """Return a recoverable tool error if a validation command is inspection."""
    for pattern in _VALIDATION_COMMAND_INSPECTION_PATTERNS:
        if pattern.search(command):
            return _VALIDATION_COMMAND_INSPECTION_BLOCK
    return None


def _context_key(context: ToolContext | None) -> str:
    if context is None:
        return ""
    return context.execution_id or ""


def _is_agent(context: ToolContext | None, *names: str) -> bool:
    return context is not None and context.agent_name in names


def _record_inspection(tool_name: str, context: ToolContext | None) -> str | None:
    """Gate coder exploration before the first successful edit.

    The gate intentionally has NO agent-name pre-check. agentspan's
    ``_dispatch._current_context`` is never populated, so ``context.agent_name``
    is always the empty string in production. An earlier guard
    ``if not _is_agent(context, "issue_fixer_coder"): return None`` short-
    circuited every call before it could touch the counter — observed in
    workflow ``fb257ccd-e3e2-468e-9a4b-50b0b3284b15`` where 416 inspections
    ran with 0 blocked. The gate is functionally coder-specific because only
    the coder agent declares these inspection tools in its ``tools=[]``; the
    fetcher uses ``write_task_brief`` only, and there is no updater. Counter
    is persisted under ``fcntl.flock`` so it accumulates correctly across
    spawn-mode worker processes.
    """
    _ensure_agent_boundary(context)
    if not _context_key(context):
        return None
    with _progress_locked(context) as progress:
        if progress is None:
            return None
        if progress.get("successful_edit_seen"):
            return None
        count = int(progress.get("inspection_count") or 0) + 1
        progress["inspection_count"] = count
        if count <= _CODER_INSPECTION_BUDGET_BEFORE_EDIT:
            return None
    # Save happens in the ctx manager exit; emit the blocked message after.
    return (
        "Blocked: coder inspection budget exceeded before the first successful edit "
        f"({_CODER_INSPECTION_BUDGET_BEFORE_EDIT} calls). "
        f"The blocked tool was {tool_name}. Use the prefilled issue_pr, "
        "repo_conventions, git_status, git_diff, and already-read context to call "
        "edit_files, edit_file, write_file, or apply_patch now. If you truly cannot "
        "edit, call write_implementation_report with a concrete blocker."
    )


def _mark_successful_edit(context: ToolContext | None) -> None:
    _ensure_agent_boundary(context)
    if not _context_key(context):
        return
    with _progress_locked(context) as progress:
        if progress is not None:
            progress["successful_edit_seen"] = True


def _record_validation(context: ToolContext | None) -> str | None:
    """Keep coder/QA from looping indefinitely on validation commands.

    No agent-name pre-check — same reasoning as ``_record_inspection``:
    ``context.agent_name`` is always ``""`` in production.
    """
    _ensure_agent_boundary(context)
    if not _context_key(context):
        return None
    with _progress_locked(context) as progress:
        if progress is None:
            return None
        count = int(progress.get("validation_count") or 0) + 1
        progress["validation_count"] = count
        if count <= _SUBAGENT_VALIDATION_BUDGET:
            return None
    return (
        "Blocked: validation budget exceeded for this sub-agent "
        f"({_SUBAGENT_VALIDATION_BUDGET} calls). Stop running commands and write the "
        "required contextbook result with the current test status and remaining risks."
    )


def _normalize_repo(repo: str) -> str:
    """Normalize and validate a GitHub repo string as ``owner/name``."""
    repo = re.sub(r"^https?://", "", repo or "")
    repo = re.sub(r"^github\.com/", "", repo)
    repo = re.sub(r"\.git$", "", repo)
    repo = repo.strip("/")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError(f"Invalid GitHub repo {repo!r}; expected owner/name")
    return repo


def _run_list(
    args: list[str], timeout: int = 60, cwd: str | None = None
) -> subprocess.CompletedProcess:
    """Run a command without a shell. Callers decide how to handle failures."""
    return subprocess.run(
        args,
        cwd=cwd if cwd is not None else _cwd(),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _combined_output(proc: subprocess.CompletedProcess) -> str:
    return (proc.stdout + proc.stderr).strip()


def _ensure_contextbook_excluded() -> None:
    """Keep contextbook artifacts out of commits without mutating .gitignore."""
    git_dir = Path(_cwd() or ".") / ".git"
    if not git_dir.exists():
        return
    info = git_dir / "info"
    info.mkdir(parents=True, exist_ok=True)
    exclude = info / "exclude"
    existing = exclude.read_text(encoding="utf-8", errors="replace") if exclude.exists() else ""
    if ".contextbook/" not in existing:
        exclude.write_text(existing.rstrip() + "\n.contextbook/\n", encoding="utf-8")


def _write_context_section(section: str, content: str) -> None:
    cb = _contextbook_dir()
    cb.mkdir(parents=True, exist_ok=True)
    (cb / f"{section}.md").write_text(content, encoding="utf-8")


def _progress_path(context: ToolContext | None) -> Path | None:
    """Return the per-execution progress file path.

    Workers in spawn-mode multiprocessing re-import this module fresh, so
    ``_WORKING_DIR`` is the empty default — they do NOT inherit the parent's
    ``set_working_dir`` setting. If we used the contextbook-relative path
    via ``_contextbook_dir()``, workers would resolve to ``Path.cwd() /
    .contextbook`` (the SDK process's launch dir), and although all workers
    share that location via CWD inheritance, the budget file would end up
    polluting whatever directory the user launched ``python`` from.

    Instead, when ``_WORKING_DIR`` is set we use the contextbook (so the
    progress file survives alongside the rest of the contextbook). When it's
    unset (worker process startup), fall back to a stable, host-wide
    ``tempfile.gettempdir() / "agentspan_progress"`` directory keyed by
    execution_id. All workers on this host that handle tasks for the same
    execution arrive at the same path either way.
    """
    key = _context_key(context)
    if not key:
        return None
    if _WORKING_DIR:
        progress_dir = _contextbook_dir() / ".progress"
    else:
        progress_dir = Path(tempfile.gettempdir()) / "agentspan_progress"
    progress_dir.mkdir(parents=True, exist_ok=True)
    safe_key = re.sub(r"[^A-Za-z0-9_.-]+", "_", key)
    return progress_dir / f"{safe_key}.json"


def _load_progress(context: ToolContext | None) -> dict:
    path = _progress_path(context)
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_progress(context: ToolContext | None, updates: dict) -> None:
    path = _progress_path(context)
    if path is None:
        return
    data = _load_progress(context)
    data.update(updates)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


@contextlib.contextmanager
def _progress_locked(context: ToolContext | None):
    """Acquire an exclusive flock on the progress file, yield the dict, write back on exit.

    Yields ``None`` when there's no execution_id (the caller no-ops). Otherwise
    yields a mutable dict the caller can update in place; the mutated state is
    persisted back to disk when the context exits normally. The flock is held
    across the read-modify-write so two workers racing the inspection counter
    never both pass the threshold check on the same boundary.
    """
    path = _progress_path(context)
    if path is None:
        yield None
        return
    # O_CREAT so the very first locker also creates the file.
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            raw = os.read(fd, 1_000_000).decode("utf-8", errors="replace")
        except OSError:
            raw = ""
        try:
            data = json.loads(raw) if raw.strip() else {}
            if not isinstance(data, dict):
                data = {}
        except json.JSONDecodeError:
            data = {}
        try:
            yield data
        finally:
            payload = json.dumps(data, indent=2, sort_keys=True).encode("utf-8")
            os.lseek(fd, 0, os.SEEK_SET)
            os.ftruncate(fd, 0)
            os.write(fd, payload)
            os.fsync(fd)
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(fd)


def _read_context_section(section: str) -> str:
    path = _contextbook_dir() / f"{section}.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _reset_contextbook() -> None:
    """Remove stale contextbook artifacts before a fresh issue/PR run."""
    cb = _contextbook_dir()
    if cb.exists():
        shutil.rmtree(cb)
    cb.mkdir(parents=True, exist_ok=True)


# ── File Operations ──────────────────────────────────────────


@tool
def read_file(path: str, context: ToolContext = None) -> str:
    """Read a file. Always returns the FULL file content with line numbers.
    For targeted code reading, use read_symbol() instead.
    Paths are relative to the repo working directory."""
    blocked = _record_inspection("read_file", context)
    if blocked:
        return blocked
    target = _resolve(path)
    if not target.exists():
        return f"Error: {path!r} does not exist."
    if target.is_dir():
        return f"Error: {path!r} is a directory. Use list_directory instead."
    size = target.stat().st_size
    if size > _MAX_FILE_BYTES:
        return f"Error: {path!r} is {size:,} bytes (limit {_MAX_FILE_BYTES:,}). Use grep_search to find specific content."
    abs_path = str(target.resolve())
    n_reads = _read_file_count.get(abs_path, 0) + 1
    _read_file_count[abs_path] = n_reads
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        _read_file_cache[abs_path] = (size, len(lines))
        numbered = [f"{i + 1:6d}\t{line}" for i, line in enumerate(lines)]
        result = "\n".join(numbered)
        if len(result) > _MAX_READ_FILE_CHARS:
            result = result[:_MAX_READ_FILE_CHARS]
            result += f"\n... TRUNCATED at {_MAX_READ_FILE_CHARS:,} chars. Use read_symbol() for targeted reading."

        # Repeat-read warning. ALWAYS return the file body — an earlier
        # version replaced content with a bare error after
        # ``_MAX_REPEAT_FILE_READS`` (3rd) reads, on the theory that the
        # agent should "use the content already returned." But the agent's
        # context window may have condensed away the prior reads, and
        # withholding the file forces another round of search/grep to
        # rediscover what it once knew. Header is the signal; data is
        # always preserved. The inspection-budget gate at
        # ``_record_inspection`` is the cross-process bound on over-reading.
        if n_reads >= 2:
            severity = (
                "STOP RE-READING"
                if n_reads > _MAX_REPEAT_FILE_READS
                else "Content is unchanged on disk"
            )
            header = (
                f"⚠️  REPEAT READ #{n_reads} of {path} ({severity}). Move to an "
                "edit, validation, or write_implementation_report with a "
                "clear blocker.\n\n"
            )
            return header + result
        return result
    except Exception as exc:
        return f"Error reading {path!r}: {exc}"


@tool
def write_file(path: str, content: str, context: ToolContext = None) -> str:
    """Write content to a file, creating parent directories as needed. Overwrites existing files.
    Paths are relative to the repo working directory."""
    target = _resolve(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            existing = target.read_text(encoding="utf-8", errors="replace")
            if existing == content:
                return f"No change: {path!r} already has the requested content."
        target.write_text(content, encoding="utf-8")
        _grep_cache.clear()  # file changed — invalidate grep cache
        _file_read_hashes.pop(str(target.resolve()), None)
        _read_file_cache.pop(str(target.resolve()), None)
        _read_file_count.pop(str(target.resolve()), None)
        _mark_successful_edit(context)
        return f"Wrote {len(content):,} bytes to {path!r}."
    except Exception as exc:
        return f"Error writing {path!r}: {exc}"


@tool
def edit_file(path: str, old_string: str, new_string: str, context: ToolContext = None) -> str:
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
        if old_string == new_string:
            return f"No change: old_string and new_string are identical for {path!r}."
        new_content = content.replace(old_string, new_string, 1)
        target.write_text(new_content, encoding="utf-8")
        _grep_cache.clear()  # file changed — invalidate grep cache
        _file_read_hashes.pop(str(target.resolve()), None)
        _read_file_cache.pop(str(target.resolve()), None)
        _read_file_count.pop(str(target.resolve()), None)
        _mark_successful_edit(context)
        return (
            f"Edited {path!r}: replaced 1 occurrence ({len(old_string)} → {len(new_string)} chars)."
        )
    except Exception as exc:
        return f"Error editing {path!r}: {exc}"


@tool
def apply_patch(patch: str, context: ToolContext = None) -> str:
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
            _read_file_count.clear()
            _grep_cache.clear()
            _mark_successful_edit(context)
            return "Patch applied successfully."
        return f"Error applying patch:\n{proc.stderr.strip()}"
    except Exception as exc:
        return f"Error: {exc}"


@tool
def list_directory(path: str = ".", max_depth: int = 2, context: ToolContext = None) -> str:
    """List directory contents in tree format up to max_depth levels deep.
    Paths are relative to the repo working directory."""
    blocked = _record_inspection("list_directory", context)
    if blocked:
        return blocked
    target = _resolve(path)
    if not target.exists():
        return f"Error: {path!r} does not exist."
    if not target.is_dir():
        return f"Error: {path!r} is not a directory."

    try:
        header = target.relative_to(Path(_cwd()))
        header_str = "./" if str(header) == "." else f"{header}/"
    except ValueError:
        header_str = f"{target}/"
    lines = [header_str]

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
def file_outline(path: str, context: ToolContext = None) -> str:
    """Show the structure of a file: classes, functions, methods, interfaces.
    Works across Python, Go, Java, TypeScript, and React.
    Paths are relative to the repo working directory."""
    blocked = _record_inspection("file_outline", context)
    if blocked:
        return blocked
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
        result = (
            result[:_MAX_OUTLINE_CHARS] + "\n... TRUNCATED. Use grep_search for specific symbols."
        )
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
            if stripped and not stripped.startswith("#") and not stripped.startswith('"""'):
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
    blocked = _record_inspection("read_symbol", context)
    if blocked:
        return blocked
    target = _resolve(path)
    if not target.exists():
        return f"Error: {path!r} does not exist."
    if target.is_dir():
        return f"Error: {path!r} is a directory."
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        # Detect repeat read of an unchanged symbol — surface a warning header
        # but ALWAYS return the symbol body. An earlier version returned just
        # "unchanged since last read. Use content from your context window"
        # with no body; if the agent re-asked (which it does after condensation
        # drops old messages) it got nothing actionable back.
        cache_key = f"{target.resolve()}:{name}"
        content_hash = hash(content)
        is_repeat = _symbol_read_hashes.get(cache_key) == content_hash
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
        if is_repeat:
            return (
                f"⚠️  REPEAT READ of symbol '{name}' in '{path}' — content "
                "unchanged. Stop re-reading and move to an edit, validation, "
                "or write_implementation_report.\n\n"
            ) + result
        return result
    except Exception as exc:
        return f"Error reading symbol '{name}' from {path!r}: {exc}"


# ── Search & Navigation ─────────────────────────────────────


_GLOB_EXCLUDE_DIRS = frozenset(
    {"build", "target", "node_modules", "dist", ".gradle", "__pycache__", ".git", ".venv", "venv"}
)


@tool
def glob_find(pattern: str, path: str = ".", context: ToolContext = None) -> str:
    """Find files matching a glob pattern (e.g. '**/*.py'). Returns sorted file paths
    relative to the repo working directory. Skips common derived directories
    (build, target, node_modules, dist, .gradle, __pycache__, .git, .venv, venv)."""
    blocked = _record_inspection("glob_find", context)
    if blocked:
        return blocked
    base = _resolve(path)
    if not base.exists():
        return f"Error: {path!r} does not exist."
    cwd = Path(_cwd())
    try:
        matches: list[str] = []
        for m in base.glob(pattern):
            if not m.is_file():
                continue
            try:
                rel = m.relative_to(cwd)
            except ValueError:
                rel = m
            if _GLOB_EXCLUDE_DIRS.intersection(rel.parts):
                continue
            matches.append(str(rel))
        matches.sort()
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
    blocked = _record_inspection("grep_search", context)
    if blocked:
        return blocked
    cache_key = (pattern, path, glob_filter)
    if cache_key in _grep_cache:
        # Return the FULL cached result. An earlier version clipped to 500
        # chars on the theory the agent should "use it from your context
        # window" — but the agent's context window may have condensed away
        # the prior call, and a 500-char stub of a 20K-char grep result
        # gives the agent essentially nothing to work with. Forces re-search
        # with slight pattern tweaks. Header warns the agent it's a repeat.
        return (
            "⚠️  REPEAT SEARCH — same pattern/path as a prior call this run. "
            "Use this result; do not re-issue the same query.\n\n" + _grep_cache[cache_key]
        )
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
def search_symbols(name: str, kind: str = "", path: str = ".", context: ToolContext = None) -> str:
    """Find definitions of classes, functions, types, interfaces, or structs.
    kind: 'class', 'function', 'type', 'interface', 'struct', or '' for all.
    Paths are relative to the repo working directory."""
    blocked = _record_inspection("search_symbols", context)
    if blocked:
        return blocked
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
def find_references(symbol: str, path: str = ".", context: ToolContext = None) -> str:
    """Find all usages of a symbol (excludes definitions). Returns file:line: context.
    Useful for blast radius analysis — 'if I change this, what breaks?'
    Paths are relative to the repo working directory."""
    blocked = _record_inspection("find_references", context)
    if blocked:
        return blocked
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
def git_diff(base: str = "", path: str = "", context: ToolContext = None) -> str:
    """Show diff of current changes vs a base branch or commit.
    Optionally scoped to a specific file or directory."""
    blocked = _record_inspection("git_diff", context)
    if blocked:
        return blocked
    actual_base = base or f"origin/{_BASE_BRANCH}"
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
def git_status(context: ToolContext = None) -> str:
    """Show current branch, status, and diff stat for the working tree."""
    blocked = _record_inspection("git_status", context)
    if blocked:
        return blocked
    try:
        branch = _combined_output(_run_list(["git", "branch", "--show-current"], timeout=15))
        status = _combined_output(_run_list(["git", "status", "--short"], timeout=15))
        stat = _combined_output(_run_list(["git", "diff", "--stat"], timeout=30))
        return (
            f"branch: {branch or '(detached)'}\n\n"
            f"## git status --short\n{status or '(clean)'}\n\n"
            f"## git diff --stat\n{stat or '(no working tree diff)'}"
        )
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
def lint_and_format(context: ToolContext = None) -> str:
    """Run the project's linter and formatter. Commands are auto-detected from repo build files.
    If no commands were detected, use run_command with the appropriate command from repo_conventions."""
    blocked = _record_validation(context)
    if blocked:
        return blocked
    _ensure_repo_commands()
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
def build_check(context: ToolContext = None) -> str:
    """Compile/type-check the project. Commands are auto-detected from repo build files.
    If no commands were detected, use run_command with the appropriate command from repo_conventions."""
    blocked = _record_validation(context)
    if blocked:
        return blocked
    _ensure_repo_commands()
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
def run_unit_tests(command: str = "", context: ToolContext = None) -> str:
    """Run unit tests. Uses auto-detected command or a custom one.
    If command is provided, uses it instead of the auto-detected one."""
    blocked = _record_validation(context)
    if blocked:
        return blocked
    if command:
        blocked = _block_validation_inspection(command)
        if blocked:
            return blocked
    else:
        _ensure_repo_commands()
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
def run_e2e_tests(command: str = "", context: ToolContext = None) -> str:
    """Run end-to-end tests. Provide the command to run.
    Discover the e2e test runner from the repo's CI config or convention files."""
    blocked = _record_validation(context)
    if blocked:
        return blocked
    if not command:
        return "No e2e command provided. Check repo_conventions for the e2e test runner command, then call run_e2e_tests(command='...')."
    blocked = _block_validation_inspection(command)
    if blocked:
        return blocked
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
    "task_brief",
    "design",
    "coder_context",
    "qa_findings",
    "pr_result",
    "architecture_design_test",
    "coder_plan",
    "implementation",
    "implementation_report",
    "qa_testing",
    # Inner reviewer's verdict + rationale, written each plan→execute→review
    # round and consumed by the next round's refine_planner.
    "review_feedback",
}


def _contextbook_dir() -> Path:
    """Return the contextbook directory, inside the working directory."""
    base = Path(_WORKING_DIR) if _WORKING_DIR else Path.cwd()
    return base / ".contextbook"


@tool(stateful=True)
def contextbook_write(section: str, content: str, append: bool = False) -> str:
    """Write to a named section of the team contextbook.
    Sections are validated against _VALID_SECTIONS.
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


def _make_contextbook_writer(tool_name: str, fixed_section: str, max_calls: int = 2, doc: str = ""):
    """Create a contextbook_write tool locked to a specific section."""

    def _fn(content: str, append: bool = False) -> str:
        return contextbook_write(fixed_section, content, append)

    _fn.__name__ = tool_name
    _fn.__qualname__ = tool_name
    _fn.__doc__ = doc or (
        f"Write to the '{fixed_section}' contextbook section.\n"
        f"append=True adds to existing content; append=False replaces."
    )
    # Apply @tool decorator with explicit name AFTER setting __name__
    return tool(name=tool_name, stateful=True, max_calls=max_calls)(_fn)


# Per-agent contextbook writers — section name is baked in, LLM can't pick wrong one
write_task_brief = _make_contextbook_writer(
    "write_task_brief",
    "task_brief",
    max_calls=2,
    doc=(
        "Write the fetcher's Task Brief for the Coder. Content must contain the "
        "four markdown sections: '## Synopsis', '## Issue Comments', "
        "'## PR Comments', '## TODO'. append=False replaces the section."
    ),
)
write_coder_context = _make_contextbook_writer("write_coder_context", "coder_context", max_calls=3)


@tool(name="write_implementation_report", stateful=True, max_calls=1)
def write_implementation_report(
    content: str, append: bool = False, context: ToolContext = None
) -> str:
    """Write the coder implementation report after deterministic progress gates pass."""
    if _is_agent(context, "issue_fixer_coder"):
        progress = _load_progress(context)
        if not progress.get("successful_edit_seen"):
            return (
                "Error: implementation_report is blocked until this coder execution has "
                "a successful write_file, edit_file, edit_files, or apply_patch result."
            )
        if int(progress.get("validation_count") or 0) < 1:
            return (
                "Error: implementation_report is blocked until this coder execution runs "
                "at least one validation tool: build_check, run_unit_tests, or lint_and_format."
            )
    return contextbook_write("implementation_report", content, append)


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
    for pattern in _RUN_COMMAND_INSPECTION_PATTERNS:
        if pattern.search(command):
            return _RUN_COMMAND_INSPECTION_BLOCK
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


def _ensure_git_identity() -> None:
    email = _run_list(["git", "config", "user.email"], timeout=10)
    if email.returncode != 0 or not email.stdout.strip():
        _run_list(["git", "config", "user.email", "agentspan@example.invalid"], timeout=10)
    name = _run_list(["git", "config", "user.name"], timeout=10)
    if name.returncode != 0 or not name.stdout.strip():
        _run_list(["git", "config", "user.name", "Agentspan Issue Fixer"], timeout=10)


def _build_pr_body(repo: str, issue_number: int) -> str:
    implementation = _read_context_section("implementation_report")
    coder_context = _read_context_section("coder_context")
    issue = _read_context_section("issue_pr")
    agent_context = json.dumps(
        {"repo": repo, "issue": issue_number, "source": "agentspan_issue_fixer"},
        indent=2,
    )
    return (
        f"Fixes #{issue_number}\n\n"
        "## Summary\n\n"
        f"{implementation[:2000] or 'See implementation context below.'}\n\n"
        "<details><summary>Coder Context</summary>\n\n"
        f"{coder_context[:12000]}\n\n"
        "</details>\n\n"
        "<details><summary>Issue / PR Context</summary>\n\n"
        f"{issue[:20000]}\n\n"
        "</details>\n\n"
        "<details><summary>Agent Context</summary>\n\n"
        f"```json\n{agent_context}\n```\n\n"
        "</details>\n"
    )


@tool(credentials=["GITHUB_TOKEN"])
def finalize_pr_update(
    repo: str,
    issue_number: int,
    pr_number: int = 0,
    branch_prefix: str = "fix/issue-",
    commit_message: str = "",
) -> dict:
    """Commit, push, and create/update a PR after the coder produced a report.

    Avoids shell execution and records the result in ``pr_result``.
    """
    try:
        repo = _normalize_repo(repo)
    except ValueError as exc:
        return {"passed": False, "error": str(exc)}

    implementation = _read_context_section("implementation_report").strip()
    if not implementation:
        result = {
            "passed": False,
            "status": "skipped",
            "reason": "implementation_report is missing",
        }
        _write_context_section("pr_result", json.dumps(result, indent=2))
        return result

    if not (Path(_cwd()) / ".git").exists():
        result = {
            "passed": False,
            "status": "failed",
            "reason": "working directory is not a git repo",
        }
        _write_context_section("pr_result", json.dumps(result, indent=2))
        return result

    _ensure_contextbook_excluded()
    _ensure_git_identity()

    branch_proc = _run_list(["git", "branch", "--show-current"], timeout=15)
    branch = branch_proc.stdout.strip() if branch_proc.returncode == 0 else ""
    if not branch:
        branch = f"{branch_prefix}{issue_number}"

    _run_list(["git", "add", "-A", "--", ":!.contextbook"], timeout=60)
    staged = _run_list(["git", "diff", "--cached", "--quiet"], timeout=30)
    committed = False
    commit_out = ""
    if staged.returncode != 0:
        message = commit_message.strip() or f"fix: address issue #{issue_number}"
        commit = _run_list(["git", "commit", "-m", message], timeout=120)
        commit_out = _combined_output(commit)
        if commit.returncode != 0:
            result = {
                "passed": False,
                "status": "failed",
                "reason": "git commit failed",
                "output": commit_out,
            }
            _write_context_section("pr_result", json.dumps(result, indent=2))
            return result
        committed = True

    push = _run_list(["git", "push", "-u", "origin", branch], timeout=180)
    if push.returncode != 0:
        result = {
            "passed": False,
            "status": "failed",
            "reason": "git push failed",
            "output": _combined_output(push),
        }
        _write_context_section("pr_result", json.dumps(result, indent=2))
        return result

    body_path = _contextbook_dir() / "pr_body.md"
    body_path.write_text(_build_pr_body(repo, issue_number), encoding="utf-8")

    if pr_number:
        comment = _run_list(
            ["gh", "pr", "comment", str(pr_number), "--repo", repo, "--body-file", str(body_path)],
            timeout=120,
        )
        view = _run_list(
            ["gh", "pr", "view", str(pr_number), "--repo", repo, "--json", "number,url"],
            timeout=60,
        )
        try:
            data = json.loads(view.stdout) if view.returncode == 0 else {}
        except json.JSONDecodeError:
            data = {}
        result = {
            "passed": comment.returncode == 0 and bool(data.get("url")),
            "status": "updated" if comment.returncode == 0 else "failed",
            "pr_number": data.get("number", pr_number),
            "url": data.get("url", ""),
            "branch": branch,
            "committed": committed,
            "commit_output": commit_out,
            "output": _combined_output(comment),
        }
        _write_context_section("pr_result", json.dumps(result, indent=2))
        return result

    existing = _run_list(
        ["gh", "pr", "list", "--repo", repo, "--head", branch, "--json", "number,url"],
        timeout=60,
    )
    existing_pr = None
    if existing.returncode == 0:
        try:
            prs = json.loads(existing.stdout)
            existing_pr = prs[0] if isinstance(prs, list) and prs else None
        except json.JSONDecodeError:
            existing_pr = None

    if existing_pr:
        comment = _run_list(
            [
                "gh",
                "pr",
                "comment",
                str(existing_pr.get("number")),
                "--repo",
                repo,
                "--body-file",
                str(body_path),
            ],
            timeout=120,
        )
        result = {
            "passed": comment.returncode == 0,
            "status": "updated" if comment.returncode == 0 else "failed",
            "pr_number": existing_pr.get("number"),
            "url": existing_pr.get("url", ""),
            "branch": branch,
            "committed": committed,
            "commit_output": commit_out,
            "output": _combined_output(comment),
        }
        _write_context_section("pr_result", json.dumps(result, indent=2))
        return result

    create = _run_list(
        [
            "gh",
            "pr",
            "create",
            "--repo",
            repo,
            "--base",
            _BASE_BRANCH,
            "--head",
            branch,
            "--title",
            f"fix: address issue #{issue_number}",
            "--body-file",
            str(body_path),
        ],
        timeout=120,
    )
    url = create.stdout.strip().splitlines()[-1] if create.stdout.strip() else ""
    result = {
        "passed": create.returncode == 0 and "github.com" in url and "/pull/" in url,
        "status": "created" if create.returncode == 0 else "failed",
        "url": url,
        "branch": branch,
        "committed": committed,
        "commit_output": commit_out,
        "output": _combined_output(create),
    }
    _write_context_section("pr_result", json.dumps(result, indent=2))
    return result


@tool
def validate_pr_result() -> str:
    """Validate that finalization produced a PR URL and recorded it in contextbook."""
    raw = _read_context_section("pr_result").strip()
    if not raw:
        return json.dumps({"passed": False, "reason": "missing pr_result"})
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        return json.dumps({"passed": False, "reason": f"invalid pr_result JSON: {exc}"})
    url = str(result.get("url", ""))
    return json.dumps(
        {
            "passed": bool(result.get("passed")) and "github.com" in url and "/pull/" in url,
            "status": result.get("status"),
            "url": url,
        }
    )


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


# ── Repo conventions (deterministic, prefilled) ─────────────


# Cache: per-execution, repo-doc content keyed by resolved path. Multiple
# read_repo_docs() calls return the same cached content so the agent can
# reference it across turns without re-paying I/O. Cleared on cwd change
# via set_working_dir.
_repo_docs_cache: dict[str, str] = {}

_REPO_DOC_CANDIDATES = (
    "CLAUDE.md",
    "AGENTS.md",
    "AGENT.md",
    "CONTRIBUTING.md",
    ".cursor/rules/agent.md",
    "docs/AGENTS.md",
)
_MAX_REPO_DOC_CHARS = 16_000


@tool
def read_repo_docs() -> str:
    """Load this repo's agent / contributor docs.

    Looks for, in priority order: ``CLAUDE.md``, ``AGENTS.md``,
    ``AGENT.md``, ``CONTRIBUTING.md``, ``.cursor/rules/agent.md``,
    ``docs/AGENTS.md`` at the repo root. Returns the first found, capped
    at ~16K chars. If multiple are present, the highest-priority one
    wins (the rest can be read explicitly via ``read_file`` if needed).

    The point: most modern repos document their test / build / lint
    commands in one of these files. Reading them once at the start of
    a review or planning session beats trial-and-error against the
    shell. Idempotent within an execution — repeat calls return the
    cached content.

    Returns a header line (``# <filename>``) plus the file content, or
    a short notice if no doc was found.
    """
    base = Path(_WORKING_DIR) if _WORKING_DIR else Path.cwd()
    cache_key = str(base)
    if cache_key in _repo_docs_cache:
        return _repo_docs_cache[cache_key]

    for relative in _REPO_DOC_CANDIDATES:
        path = base / relative
        if not path.is_file():
            continue
        try:
            content = path.read_text(errors="replace")
        except Exception:
            continue
        if len(content) > _MAX_REPO_DOC_CHARS:
            content = content[:_MAX_REPO_DOC_CHARS] + (
                f"\n\n[truncated — file is {len(content):,} chars; first "
                f"{_MAX_REPO_DOC_CHARS:,} shown]"
            )
        result = f"# {relative}\n\n{content}"
        _repo_docs_cache[cache_key] = result
        return result

    notice = (
        "[no repo docs found — searched: "
        + ", ".join(_REPO_DOC_CANDIDATES)
        + ". Fall back to inferring test/build commands from the repo "
        + "files (look for package.json, pyproject.toml, go.mod, "
        + "Makefile, build.gradle, pom.xml, Cargo.toml).]"
    )
    _repo_docs_cache[cache_key] = notice
    return notice


# ── Composite Tools (deterministic, reduce LLM turns) ───────


@tool
def get_coder_context() -> str:
    """Legacy composite context reader for the older issue-fixer pipeline.

    Returns only sections that have been written (skips empty ones).
    The v2 issue fixer uses prefill_tools for explicit context sections instead."""
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


def _join_shell_commands(commands: list[str]) -> str:
    """Join distinct shell commands so each runs from repo root."""
    unique: list[str] = []
    for command in commands:
        if command and command not in unique:
            unique.append(command)
    return " && ".join(f"({command})" for command in unique)


def _fill_missing_monorepo_commands(base: Path) -> None:
    """Detect common nested project commands when repo-root files are thin wrappers."""
    nested: dict[str, list[str]] = {"lint": [], "build": [], "test": []}

    server_dir = base / "server"
    if (server_dir / "gradlew").exists():
        nested["lint"].append("cd server && ./gradlew spotlessApply")
        nested["build"].append("cd server && ./gradlew testClasses")
        nested["test"].append("cd server && ./gradlew test")

    cli_dir = base / "cli"
    if (cli_dir / "go.mod").exists():
        nested["lint"].append("cd cli && gofmt -w . && go vet ./...")
        nested["build"].append("cd cli && go build ./...")
        nested["test"].append("cd cli && go test ./...")

    for key, commands in nested.items():
        if commands and not _REPO_COMMANDS.get(key):
            _REPO_COMMANDS[key] = _join_shell_commands(commands)


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

    _fill_missing_monorepo_commands(base)

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


@tool(max_calls=1, credentials=["GITHUB_TOKEN"])
def prepare_issue_workspace(
    repo: str,
    issue_number: int,
    pr_number: int = 0,
    branch_prefix: str = "fix/issue-",
) -> dict:
    """Deterministically fetch issue/PR context, clone/fetch the repo, and write contextbook.

    This tool is intended for a static PLAN_EXECUTE setup stage. It has no LLM
    decisions and does not push or commit. Paths are resolved from the shared
    working directory set by ``set_working_dir``.
    """
    global _BASE_BRANCH

    errors: list[str] = []
    try:
        repo = _normalize_repo(repo)
    except ValueError as exc:
        return {"passed": False, "error": str(exc)}

    def _run(args: list[str], timeout: int = 60) -> str:
        try:
            proc = _run_list(args, timeout=timeout)
            out = _combined_output(proc)
            if proc.returncode != 0:
                errors.append(f"[{proc.returncode}] {' '.join(args)}: {out[:500]}")
            return out
        except Exception as exc:
            errors.append(f"{' '.join(args)}: {exc}")
            return ""

    # Fetch issue details before clone so auth/permissions fail early.
    issue_json_raw = _run(
        [
            "gh",
            "issue",
            "view",
            str(issue_number),
            "--repo",
            repo,
            "--json",
            "number,title,body,author,labels,comments,assignees,"
            "milestone,state,createdAt,updatedAt,closedAt,reactionGroups",
        ],
        timeout=120,
    )
    try:
        issue_data = json.loads(issue_json_raw) if issue_json_raw.strip() else {}
    except json.JSONDecodeError:
        issue_data = {}
        errors.append("Could not parse gh issue JSON output.")

    # Clone or refresh the repository. The working directory itself is the repo root.
    if (Path(_cwd()) / ".git").exists():
        _run(["git", "fetch", "origin", "--prune"], timeout=120)
    else:
        _run(["gh", "repo", "clone", repo, "."], timeout=180)

    pr_data: dict = {}
    if pr_number:
        pr_json_raw = _run(
            [
                "gh",
                "pr",
                "view",
                str(pr_number),
                "--repo",
                repo,
                "--json",
                "number,title,body,state,headRefName,baseRefName,"
                "comments,reviews,reviewRequests,author,labels",
            ],
            timeout=120,
        )
        try:
            pr_data = json.loads(pr_json_raw) if pr_json_raw.strip() else {}
        except json.JSONDecodeError:
            pr_data = {}
            errors.append("Could not parse gh PR JSON output.")
        base_ref = pr_data.get("baseRefName")
        if base_ref:
            _BASE_BRANCH = str(base_ref)
        _run(["gh", "pr", "checkout", str(pr_number), "--repo", repo], timeout=120)
        branch = _run(["git", "branch", "--show-current"], timeout=15).strip()
        if not branch:
            branch = str(pr_data.get("headRefName") or f"{branch_prefix}{issue_number}")
    else:
        branch = f"{branch_prefix}{issue_number}"
        # Discover default branch before checkout so the local branch starts from remote base.
        try:
            remote_head = _run(["git", "symbolic-ref", "refs/remotes/origin/HEAD"], timeout=10)
            if remote_head.strip():
                _BASE_BRANCH = remote_head.strip().split("/")[-1]
        except Exception:
            pass
        _run(["git", "checkout", "-B", branch, f"origin/{_BASE_BRANCH}"], timeout=60)

    _reset_contextbook()
    _ensure_contextbook_excluded()

    conventions = _discover_repo_conventions()

    issue_pr_parts = [
        f"# Issue #{issue_number}: {issue_data.get('title', 'unknown')}",
        f"Author: {issue_data.get('author', {}).get('login', 'unknown')}",
        f"Labels: {', '.join(lb.get('name', '') for lb in issue_data.get('labels', [])) or 'none'}",
        f"Repo: {repo}",
        f"Branch: {branch}",
        f"Mode: {'PR feedback' if pr_number else 'new issue fix'}",
        "",
        "## Issue Body",
        issue_data.get("body", "(empty)"),
    ]

    issue_comments = issue_data.get("comments", [])
    if issue_comments:
        issue_pr_parts.append("\n## Issue Comments")
        for c in issue_comments:
            author = c.get("author", {}).get("login", "unknown")
            body = c.get("body", "")
            issue_pr_parts.append(f"\n**@{author}:**\n{body}")

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

        inline_raw = _run(
            [
                "gh",
                "api",
                f"repos/{repo}/pulls/{pr_number}/comments",
                "--paginate",
                "--jq",
                "[.[] | {path:.path,line:.line,original_line:.original_line,"
                "diff_hunk:.diff_hunk,body:.body,author:.user.login,"
                "in_reply_to_id:.in_reply_to_id,created_at:.created_at}]",
            ],
            timeout=120,
        )
        try:
            inline_comments = json.loads(inline_raw) if inline_raw.strip() else []
        except json.JSONDecodeError:
            inline_comments = []
        if inline_comments:
            issue_pr_parts.append("\n### Inline Review Comments")
            for ic in inline_comments:
                line_ref = ic.get("line") or ic.get("original_line") or "?"
                reply_note = " (reply)" if ic.get("in_reply_to_id") else ""
                issue_pr_parts.append(
                    f"\n**@{ic.get('author', '?')}**{reply_note} at "
                    f"`{ic.get('path', '?')}:{line_ref}`:\n{ic.get('body', '')}"
                )

    issue_pr_content = "\n".join(issue_pr_parts)
    _write_context_section("issue_pr", issue_pr_content)
    _write_context_section("repo_conventions", conventions)

    return {
        "passed": not errors and bool(issue_data) and (Path(_cwd()) / ".git").exists(),
        "repo": repo,
        "issue": issue_number,
        "pr": pr_number,
        "branch": branch,
        "base_branch": _BASE_BRANCH,
        "warnings": errors,
    }


@tool
def validate_issue_workspace() -> str:
    """Validate that deterministic setup wrote the context needed by later agents."""
    cb = _contextbook_dir()
    required = ["issue_pr", "repo_conventions"]
    missing = [name for name in required if not (cb / f"{name}.md").is_file()]
    unexpected = (
        sorted(path.stem for path in cb.glob("*.md") if path.stem not in set(required))
        if cb.exists()
        else []
    )
    has_git = (Path(_cwd()) / ".git").exists()

    issue_pr = _read_context_section("issue_pr")
    branch_match = re.search(r"^Branch:\s*(.+)$", issue_pr, flags=re.MULTILINE)
    mode_match = re.search(r"^Mode:\s*(.+)$", issue_pr, flags=re.MULTILINE)
    expected_branch = branch_match.group(1).strip() if branch_match else ""
    mode = mode_match.group(1).strip().lower() if mode_match else ""
    branch_proc = _run_list(["git", "branch", "--show-current"], timeout=15)
    current_branch = branch_proc.stdout.strip() if branch_proc.returncode == 0 else ""
    branch_errors = []
    if not current_branch:
        branch_errors.append("current git branch is empty or unavailable")
    if expected_branch and current_branch and current_branch != expected_branch:
        branch_errors.append(
            f"context branch {expected_branch!r} does not match current branch {current_branch!r}"
        )
    if mode == "new issue fix" and current_branch in {_BASE_BRANCH, "main", "master"}:
        branch_errors.append(f"new issue fix is on default branch {current_branch!r}")

    return json.dumps(
        {
            "passed": not missing and has_git and not unexpected and not branch_errors,
            "missing": missing,
            "unexpected": unexpected,
            "has_git": has_git,
            "expected_branch": expected_branch,
            "current_branch": current_branch,
            "branch_errors": branch_errors,
        }
    )


@tool(max_calls=1, credentials=["GITHUB_TOKEN"])
def setup_repo(
    repo: str, issue_number: int, pr_number: int = 0, branch_prefix: str = "fix/issue-"
) -> str:
    """Backward-compatible wrapper for the deterministic setup tool.

    Older examples called ``setup_repo`` directly from an LLM agent. The real
    implementation now delegates to ``prepare_issue_workspace`` so setup has no
    push/commit side effects and does not use a shell.
    """
    result = prepare_issue_workspace(repo, issue_number, pr_number, branch_prefix)
    issue_pr = _read_context_section("issue_pr")
    summary = [
        f"REPO: {result.get('repo', repo)}",
        f"BRANCH: {result.get('branch', '')}",
        f"ISSUE: #{issue_number}",
        f"PR: #{pr_number}" if pr_number else "",
        f"SETUP_PASSED: {result.get('passed')}",
    ]
    warnings = result.get("warnings") or []
    if warnings:
        summary.append("WARNINGS:\n" + "\n".join(str(w) for w in warnings))
    summary.append("\n---\n\n" + issue_pr)
    return "\n".join(part for part in summary if part)


# ── Batch Tools (force parallel operations in a single call) ──


@tool
def edit_files(edits_json: str, context: ToolContext = None) -> str:
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
            if old_string == new_string:
                results.append(f"[{i + 1}] No change: old_string and new_string are identical.")
                continue
            new_content = content.replace(old_string, new_string, 1)
            target.write_text(new_content, encoding="utf-8")
            _file_read_hashes.pop(str(target.resolve()), None)
            _read_file_cache.pop(str(target.resolve()), None)
            _read_file_count.pop(str(target.resolve()), None)
            results.append(
                f"[{i + 1}] OK: {path!r} edited ({len(old_string)} → {len(new_string)} chars)."
            )
            any_success = True
        except Exception as exc:
            results.append(f"[{i + 1}] Error editing {path!r}: {exc}")
    if any_success:
        _grep_cache.clear()
        _mark_successful_edit(context)
    return "\n".join(results)
