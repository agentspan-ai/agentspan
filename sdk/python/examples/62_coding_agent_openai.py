# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Coding Agent (OpenAI fallback) — a Claude Code alternative via Agentspan.

Use this when Claude Code is unavailable (outages, rate limits, etc.). It
provides the same core workflow — read/edit files, run shell commands, execute
code, review changes — but runs on OpenAI GPT-4o (or any provider you set via
AGENTSPAN_LLM_MODEL).

Architecture:
    coder  ↔  qa_reviewer  (SWARM — LLM-driven handoffs)

    • coder        — reads files, makes changes, runs code/tests
    • qa_reviewer  — reviews diffs, runs the test suite, approves or bounces

Tools available to the agents:
    read_file    — read a file with line numbers
    write_file   — create or overwrite a file
    edit_file    — exact string replacement (like Claude Code's Edit)
    list_files   — glob files in a directory
    search_code  — regex search across files (like grep)
    run_command  — shell commands (bash, git, python, pytest, npm, …)
    execute_code — run Python/Bash snippets in-process (local_code_execution)

Usage:
    # Single task via CLI argument
    python 62_coding_agent_openai.py "add type hints to utils.py"

    # Interactive REPL (keeps conversation context between turns)
    python 62_coding_agent_openai.py

Environment variables:
    AGENTSPAN_SERVER_URL   — Agentspan server (default: http://localhost:6767/api)
    AGENTSPAN_LLM_MODEL    — override model (default: openai/gpt-4o)
    OPENAI_API_KEY         — required for default OpenAI model
    CODING_AGENT_CWD       — working directory for file ops (default: current dir)

Requirements:
    - Agentspan server running (agentspan server start)
    - AGENTSPAN_SERVER_URL set
    - OPENAI_API_KEY set (or AGENTSPAN_LLM_MODEL pointing to another provider)
"""

from __future__ import annotations

import glob as glob_module
import os
import re
import sys
from pathlib import Path

from agentspan.agents import Agent, AgentRuntime, ConversationMemory, Strategy
from agentspan.agents.cli_config import CliConfig
from agentspan.agents.tool import tool

# ── Configuration ─────────────────────────────────────────────────────────────

MODEL = os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o")
# Root directory that file tools operate within; agents see paths relative to it.
WORKDIR = os.environ.get("CODING_AGENT_CWD", os.getcwd())

# ── File system tools ─────────────────────────────────────────────────────────


@tool
def read_file(path: str) -> dict:
    """Read a file and return its contents with line numbers.

    Args:
        path: Absolute or relative path to the file.
    """
    full = Path(WORKDIR) / path if not Path(path).is_absolute() else Path(path)
    try:
        text = full.read_text(encoding="utf-8", errors="replace")
        numbered = "\n".join(f"{i + 1}\t{line}" for i, line in enumerate(text.splitlines()))
        return {"path": str(full), "content": numbered, "lines": text.count("\n") + 1}
    except FileNotFoundError:
        return {"error": f"File not found: {full}"}
    except Exception as e:
        return {"error": str(e)}


@tool
def write_file(path: str, content: str) -> dict:
    """Create or overwrite a file with the given content.

    Creates parent directories automatically. Use edit_file for small
    targeted changes — write_file replaces the entire file.

    Args:
        path: Absolute or relative path.
        content: Full file content (text).
    """
    full = Path(WORKDIR) / path if not Path(path).is_absolute() else Path(path)
    try:
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
        lines = content.count("\n") + 1
        return {"status": "written", "path": str(full), "lines": lines}
    except Exception as e:
        return {"error": str(e)}


@tool
def edit_file(path: str, old_string: str, new_string: str) -> dict:
    """Make an exact string replacement in a file.

    Fails if old_string is not found or appears more than once (use a
    larger context window to make the match unique in that case).

    Args:
        path: Path to the file to edit.
        old_string: The exact text to replace (must match verbatim, including whitespace).
        new_string: The replacement text.
    """
    full = Path(WORKDIR) / path if not Path(path).is_absolute() else Path(path)
    try:
        original = full.read_text(encoding="utf-8")
        count = original.count(old_string)
        if count == 0:
            return {"error": "old_string not found in file — check whitespace and indentation"}
        if count > 1:
            return {
                "error": (
                    f"old_string appears {count} times — add more surrounding context "
                    "to make it unique"
                )
            }
        updated = original.replace(old_string, new_string, 1)
        full.write_text(updated, encoding="utf-8")
        return {"status": "edited", "path": str(full), "replacements": 1}
    except FileNotFoundError:
        return {"error": f"File not found: {full}"}
    except Exception as e:
        return {"error": str(e)}


@tool
def list_files(pattern: str = "**/*", directory: str = "") -> dict:
    """List files matching a glob pattern.

    Args:
        pattern: Glob pattern (e.g. ``**/*.py``, ``src/**/*.ts``).
        directory: Sub-directory to search in (relative to working dir).
    """
    base = Path(WORKDIR) / directory if directory else Path(WORKDIR)
    try:
        matches = sorted(
            str(Path(p).relative_to(base))
            for p in glob_module.glob(str(base / pattern), recursive=True)
            if Path(p).is_file()
        )
        return {"directory": str(base), "pattern": pattern, "files": matches, "count": len(matches)}
    except Exception as e:
        return {"error": str(e)}


@tool
def search_code(
    pattern: str,
    path: str = "",
    file_glob: str = "*",
    context_lines: int = 2,
    case_insensitive: bool = False,
) -> dict:
    """Search for a regex pattern across files (like grep -n).

    Args:
        pattern: Regular expression to search for.
        path: Directory or file to search (relative to working dir).
        file_glob: Glob to filter files (e.g. ``*.py``, ``*.{ts,tsx}``).
        context_lines: Lines of context before/after each match.
        case_insensitive: If True, search is case-insensitive.
    """
    base = Path(WORKDIR) / path if path else Path(WORKDIR)
    flags = re.IGNORECASE if case_insensitive else 0
    try:
        compiled = re.compile(pattern, flags)
    except re.error as e:
        return {"error": f"Invalid regex: {e}"}

    results: list[dict] = []
    search_root = base if base.is_dir() else base.parent
    glob_iter = (
        search_root.glob(file_glob)
        if not base.is_dir() and base.is_file()
        else search_root.rglob(file_glob)
    )
    if base.is_file():
        glob_iter = iter([base])

    for fpath in glob_iter:
        if not fpath.is_file():
            continue
        try:
            lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines):
            if compiled.search(line):
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)
                snippet = "\n".join(
                    f"{'>' if j == i else ' '} {j + 1}\t{lines[j]}" for j in range(start, end)
                )
                results.append(
                    {
                        "file": str(fpath.relative_to(Path(WORKDIR))),
                        "line": i + 1,
                        "match": line,
                        "snippet": snippet,
                    }
                )

    return {
        "pattern": pattern,
        "matches": len(results),
        "results": results[:100],  # cap to avoid huge payloads
    }


# ── Shared CLI config ──────────────────────────────────────────────────────────

_CLI = CliConfig(
    allowed_commands=[
        "bash",
        "sh",
        "python",
        "python3",
        "pytest",
        "uv",
        "pip",
        "git",
        "gh",
        "npm",
        "npx",
        "node",
        "yarn",
        "pnpm",
        "cargo",
        "go",
        "make",
        "ls",
        "cat",
        "find",
        "echo",
        "curl",
        "jq",
        "ruff",
        "mypy",
    ],
    allow_shell=True,
    timeout=120,
    working_dir=WORKDIR,
)

_FILE_TOOLS = [read_file, write_file, edit_file, list_files, search_code]

# ── QA Reviewer ───────────────────────────────────────────────────────────────

qa_reviewer = Agent(
    name="qa_reviewer",
    model=MODEL,
    instructions="""\
You are a senior code reviewer and QA engineer. You receive code that the coder
has just written or modified.

Your job:
1. Read the changed files using read_file and list_files.
2. Check for correctness, edge cases, style issues, security problems.
3. Run the test suite (pytest, npm test, cargo test, go test, etc.) if it exists.
4. Run the linter if the project has one (ruff, eslint, etc.).

If you find critical bugs or test failures:
- Clearly describe each issue with the file name and line number.
- Transfer back to the coder with a concise list of fixes needed.

If everything looks good:
- Confirm the code is correct and the tests pass.
- Write a short QA report summarising what was checked.
- Do NOT transfer back to the coder.

IMPORTANT: Only transfer back if there are real problems. Do not nitpick style
issues that don't affect correctness unless the project has a strict linter.
""",
    tools=_FILE_TOOLS,
    local_code_execution=True,
    cli_config=_CLI,
    max_turns=12,
    max_tokens=8192,
)

# ── Coder ─────────────────────────────────────────────────────────────────────

coder = Agent(
    name="coder",
    model=MODEL,
    instructions=f"""\
You are an expert software engineer acting as a coding assistant.
Working directory: {WORKDIR}

Available tools:
  read_file      — read a file with line numbers
  write_file     — create or overwrite a file
  edit_file      — exact string replacement (PREFERRED for small edits)
  list_files     — glob files (use to explore the project)
  search_code    — regex search across files
  run_command    — run shell commands (git, python, pytest, npm, …)
  execute_code   — run Python/Bash snippets inline

Workflow for every task:
1. EXPLORE first — use list_files and read_file to understand what already exists.
2. PLAN — think through the change before writing any code.
3. IMPLEMENT — prefer edit_file for targeted changes, write_file for new files.
4. VERIFY — run the code / tests to confirm it works.
5. COMMIT (if asked) — stage and commit with a clear message.
6. HAND OFF to qa_reviewer once your changes are complete and tested.

Rules:
- Make the SMALLEST correct change that satisfies the request.
- Match existing code style exactly.
- Never skip verification — always run the code or tests before handing off.
- If a command fails, read the error, diagnose, and fix before retrying.
- If the task is ambiguous, make a reasonable assumption and state it clearly.
""",
    tools=_FILE_TOOLS,
    local_code_execution=True,
    cli_config=_CLI,
    agents=[qa_reviewer],
    strategy=Strategy.SWARM,
    max_turns=25,
    max_tokens=8192,
    timeout_seconds=600,
    memory=ConversationMemory(max_messages=50),
)

# ── Entry point ───────────────────────────────────────────────────────────────

def _banner() -> None:
    provider = MODEL.split("/")[0] if "/" in MODEL else MODEL
    print("=" * 60)
    print("  Coding Agent (Agentspan fallback for Claude Code outages)")
    print(f"  Model  : {MODEL}")
    print(f"  Workdir: {WORKDIR}")
    print("=" * 60)
    print("  Type your task and press Enter. Ctrl+C or Ctrl+D to exit.")
    print()


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        if len(sys.argv) > 1:
            # Non-interactive: task passed as CLI argument(s)
            task = " ".join(sys.argv[1:])
            print(f"Task: {task}\n")
            result = runtime.run(coder, task)
            result.print_result()
        else:
            # Interactive REPL
            _banner()
            while True:
                try:
                    task = input("> ").strip()
                except (KeyboardInterrupt, EOFError):
                    print("\nBye!")
                    break
                if not task:
                    continue
                print()
                result = runtime.run(coder, task)
                result.print_result()
                print()

        # Production deployment pattern:
        # 1. Deploy once:    runtime.deploy(coder)
        # 2. Serve workers:  runtime.serve(coder)
        # CLI:  agentspan deploy --package examples.62_coding_agent_openai
