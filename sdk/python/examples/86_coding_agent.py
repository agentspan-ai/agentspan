#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Coding Agent Harness — deterministic, plan-first file editing.

Demonstrates Strategy.PLAN_EXECUTE with a single-agent harness (planner only,
no fallback).  The planner explores the repo with read-only tools and a
``write_coder_plan`` commit tool, then outputs a JSON plan.  The plan is
compiled into a deterministic Conductor sub-workflow that calls ``edit_file``,
``write_file``, and ``run_command`` as SIMPLE tasks.

There is intentionally NO fallback agent.  If the plan fails, the workflow
terminates with FAILED status so problems are visible rather than silently
patched by an agentic recovery loop.

Architecture:

    coder_planner (agentic LLM)
      ├── reads: read_file, list_files, grep_search, run_command
      └── commits: write_coder_plan (stores JSON plan in _plan_store)
      ↓ outputs JSON plan text
    plan executor (deterministic Conductor workflow compiled from JSON plan)
      ├── step: create_files  (parallel: write_file generate blocks)
      ├── step: modify_files  (parallel: edit_file generate blocks)
      └── validation: run_command (e.g. pytest --tb=short)

Plan JSON schema (Section 6 of CODING_AGENT_HARNESS_DESIGN.md):

    {
      "steps": [
        {
          "id": "create_files",
          "parallel": true,
          "operations": [
            {
              "tool": "write_file",
              "generate": {
                "instructions": "Write ...",
                "context": "Existing patterns: ...",
                "output_schema": "{\"path\": \"src/foo.py\", \"content\": \"...\"}"
              }
            }
          ]
        },
        {
          "id": "modify_files",
          "depends_on": ["create_files"],
          "parallel": true,
          "operations": [
            {
              "tool": "edit_file",
              "generate": {
                "instructions": "Change X to Y in src/bar.py",
                "context": "Current file:\\n<full file contents>",
                "output_schema": "{\"path\": \"src/bar.py\", \"old_string\": \"...\", \"new_string\": \"...\"}"
              }
            }
          ]
        }
      ],
      "validation": [
        {
          "tool": "run_command",
          "args": {"command": "python -m pytest tests/ --tb=short -q"},
          "success_condition": "$.indexOf('passed') >= 0 || $.indexOf('no tests ran') >= 0"
        }
      ],
      "on_success": []
    }

Usage:
    python 86_coding_agent.py "Add a greet() function that returns 'Hello, <name>!'"
    python 86_coding_agent.py "Fix the failing test in tests/test_math.py"

Requirements:
    - Agentspan server with PLAN_EXECUTE strategy support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - AGENTSPAN_LLM_MODEL set (or defaults to openai/gpt-4o-mini)
"""

import os
import subprocess
import sys
import tempfile

from agentspan.agents import Agent, AgentRuntime, Strategy, tool
from settings import settings

# ── Demo repo setup ───────────────────────────────────────────────────────────

DEMO_REPO = os.path.join(tempfile.gettempdir(), "coding-agent-demo")

_INITIAL_FILES = {
    "src/__init__.py": "",
    "src/math_utils.py": """\
\"\"\"Simple math utilities.\"\"\"


def add(a: int, b: int) -> int:
    return a + b


def subtract(a: int, b: int) -> int:
    return a - b
""",
    "tests/__init__.py": "",
    "tests/test_math.py": """\
from src.math_utils import add, subtract


def test_add():
    assert add(2, 3) == 5


def test_subtract():
    assert subtract(10, 4) == 6
""",
}


def _ensure_demo_repo() -> str:
    """Create the demo repo if it does not exist."""
    if not os.path.isdir(DEMO_REPO):
        os.makedirs(DEMO_REPO, exist_ok=True)
        for rel, content in _INITIAL_FILES.items():
            full = os.path.join(DEMO_REPO, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w") as f:
                f.write(content)
        print(f"Created demo repo at: {DEMO_REPO}")
    return DEMO_REPO


# ── Planner-accessible tools (read-only + write_coder_plan) ──────────────────
# The planner uses these during exploration.  None of them make permanent edits
# to the codebase — write_coder_plan stores the plan only for the executor.

_PLAN_STORE: dict = {}  # in-process store; in production use a durable store


@tool
def read_file(path: str) -> str:
    """Read the contents of a file in the demo repo.

    Args:
        path: Relative path inside the demo repo.
    """
    full = os.path.join(DEMO_REPO, path)
    if not os.path.isfile(full):
        return f"ERROR: file not found: {path}"
    with open(full) as f:
        return f.read()


@tool
def list_files(directory: str = "") -> str:
    """List files (recursively) in a directory of the demo repo.

    Args:
        directory: Relative path to a directory (empty = repo root).
    """
    root = os.path.join(DEMO_REPO, directory)
    if not os.path.isdir(root):
        return f"ERROR: directory not found: {directory or '.'}"
    results = []
    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            rel = os.path.relpath(os.path.join(dirpath, fname), DEMO_REPO)
            results.append(rel)
    return "\n".join(sorted(results)) if results else "(empty)"


@tool
def grep_search(pattern: str, path: str = "") -> str:
    """Search for a text pattern in the demo repo using grep.

    Args:
        pattern: Regex or literal string to search for.
        path:    Relative path to scope the search (empty = whole repo).
    """
    root = os.path.join(DEMO_REPO, path)
    try:
        out = subprocess.run(
            ["grep", "-rn", "--include=*.py", pattern, root],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return (out.stdout or "(no matches)").strip()
    except Exception as e:
        return f"ERROR: {e}"


@tool
def run_command(command: str) -> str:
    """Run a shell command inside the demo repo and return its output.

    Args:
        command: Shell command to execute.
    """
    try:
        out = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=DEMO_REPO,
        )
        combined = (out.stdout + out.stderr).strip()
        return combined or f"(exit {out.returncode})"
    except subprocess.TimeoutExpired:
        return "ERROR: command timed out after 60s"
    except Exception as e:
        return f"ERROR: {e}"


@tool(max_calls=2)
def write_coder_plan(content: str) -> str:
    """Store the coding plan for the executor.

    Call this once after you have explored the codebase and written the plan.
    The content must be Markdown followed by a ```json fence containing the
    structured execution plan.

    Args:
        content: Full plan text: Markdown change map + JSON fence.
    """
    _PLAN_STORE["plan"] = content
    return "Plan stored successfully."


# ── Executor tools — declared on the harness, called by the compiled plan ────
# The planner does NOT have these.  They are declared on the ``coder`` harness
# via ``tools=`` so Agentspan registers their Conductor task definitions.
# The compiled plan calls them by name as SIMPLE tasks.

@tool
def edit_file(path: str, old_string: str, new_string: str) -> str:
    """Apply an exact string replacement to a file in the demo repo.

    Args:
        path:       Relative file path.
        old_string: Exact string to find (must match exactly).
        new_string: Replacement string.
    """
    full = os.path.join(DEMO_REPO, path)
    if not os.path.isfile(full):
        return f"ERROR: file not found: {path}"
    with open(full) as f:
        content = f.read()
    if old_string not in content:
        return f"ERROR: old_string not found in {path}"
    updated = content.replace(old_string, new_string, 1)
    with open(full, "w") as f:
        f.write(updated)
    return f"Edited {path}: replaced {len(old_string)} chars with {len(new_string)} chars."


@tool
def write_file(path: str, content: str) -> str:
    """Write (create or overwrite) a file in the demo repo.

    Args:
        path:    Relative file path.
        content: Full file content to write.
    """
    full = os.path.join(DEMO_REPO, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(content)
    return f"Wrote {len(content)} bytes to {path}."


# ── Planner instructions ──────────────────────────────────────────────────────

PLANNER_INSTRUCTIONS = f"""\
You are a coding agent planner.  Your job is to explore the codebase, \
understand what changes are needed, write a precise plan, and call \
write_coder_plan() with the plan text.

## Workflow

1. EXPLORE — use read_file, list_files, grep_search to understand the repo.
   Always read every file you plan to modify BEFORE writing the plan.
2. PLAN — write a Markdown change map followed by a ```json fence.
3. COMMIT — call write_coder_plan(content=<your full plan text>).
   After calling write_coder_plan, you are DONE.

## Available tools during exploration

- read_file(path)        — read a file
- list_files(directory)  — list files
- grep_search(pattern)   — search by pattern
- run_command(command)   — run read-only commands (ls, find, grep, python -m pytest --collect-only …)
- write_coder_plan(content) — FINAL tool: store the plan

Do NOT call edit_file or write_file — those are executor tools only.

## Demo repo

Working directory: {DEMO_REPO}
The repo contains src/ and tests/ directories.

## Plan JSON schema

Your plan MUST end with a ```json fence.  The JSON has this structure:

```json
{{
  "steps": [
    {{
      "id": "create_files",
      "parallel": true,
      "operations": [
        {{
          "tool": "write_file",
          "generate": {{
            "instructions": "Write a Python module at src/greet.py that …",
            "context": "Existing src/math_utils.py for style reference:\\n<paste content>",
            "output_schema": "{{\\"path\\": \\"src/greet.py\\", \\"content\\": \\"\\"}}"
          }}
        }}
      ]
    }},
    {{
      "id": "modify_files",
      "depends_on": ["create_files"],
      "parallel": true,
      "operations": [
        {{
          "tool": "edit_file",
          "generate": {{
            "instructions": "In src/math_utils.py add a multiply() function …",
            "context": "Current file:\\n<paste FULL file content here>",
            "output_schema": "{{\\"path\\": \\"src/math_utils.py\\", \\"old_string\\": \\"\\", \\"new_string\\": \\"\\"}}"
          }}
        }}
      ]
    }}
  ],
  "validation": [
    {{
      "tool": "run_command",
      "args": {{"command": "python -m pytest tests/ --tb=short -q"}},
      "success_condition": "$.indexOf('passed') >= 0 || $.indexOf('no tests ran') >= 0"
    }}
  ],
  "on_success": []
}}
```

## Rules

1. Read every file before writing instructions about it.
2. For MODIFY ops: generate.context MUST contain the FULL current file contents.
3. For CREATE ops: generate.context should contain similar existing files for style.
4. output_schema keys must exactly match the tool signature:
   - edit_file:  {{"path": "str", "old_string": "str", "new_string": "str"}}
   - write_file: {{"path": "str", "content": "str"}}
5. success_condition is a JavaScript expression where $ is the command output string.
   Use $.indexOf('passed') >= 0 for pytest.
6. Omit steps that have no operations (e.g. skip "modify_files" if nothing to modify).
7. The JSON must be valid — double-check bracket matching.
8. Always include a validation step using run_command + pytest.
"""


# ── Agents ────────────────────────────────────────────────────────────────────

coder_planner = Agent(
    name="coder_planner",
    model=settings.llm_model,
    instructions=PLANNER_INSTRUCTIONS,
    tools=[read_file, list_files, grep_search, run_command, write_coder_plan],
    max_turns=15,
    max_tokens=16000,
)

# The harness: PLAN_EXECUTE with planner only (no fallback).
# tools= declares the executor tools so Agentspan registers their task
# definitions; the compiled plan calls them as SIMPLE Conductor tasks.
coder = Agent(
    name="coder",
    model=settings.llm_model,
    agents=[coder_planner],  # no fallback — plan must succeed
    strategy=Strategy.PLAN_EXECUTE,
    tools=[edit_file, write_file, run_command],
)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    task = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else (
        "Add a greet(name) function to src/math_utils.py that returns "
        "'Hello, <name>!' and add a test for it in tests/test_math.py"
    )

    repo = _ensure_demo_repo()
    print(f"Task   : {task}")
    print(f"Repo   : {repo}")
    print(f"Strategy: PLAN_EXECUTE (single planner, no fallback)")
    print()

    with AgentRuntime() as rt:
        result = rt.run(coder, task)
        result.print_result()

    # Show plan that was stored (if planner ran locally in same process)
    if _PLAN_STORE.get("plan"):
        print("\n--- Stored plan (first 600 chars) ---")
        print(_PLAN_STORE["plan"][:600])


if __name__ == "__main__":
    main()
