# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""OpenAI Agents SDK migration — shell agent (local workspace).

This example shows the same pattern as the old sandbox/basic.py from the
openai-agents SDK with exactly ONE line changed. The old sandbox API
(SandboxAgent, agents.sandbox) was removed in openai-agents ≥ 0.12. This
version uses a @function_tool to execute shell commands in a temporary
workspace — no Docker required.

Before (runs directly against OpenAI):
    from agents import Runner

After (runs on Agentspan — durable, observable, scalable):
    from agentspan import Runner

The diff:
    -from agents import Runner
    +from agentspan import Runner

Architecture:
    ShellAgent   — standard openai-agents Agent with a shell execution tool
    Workspace    — temporary directory populated with demo files
    AgentspanRunner — routes execution through Agentspan instead of OpenAI

Requirements:
    - uv add openai-agents          (in sdk/python/)
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o

Usage (from sdk/python/):
    uv run python examples/97_openai_runner_shell.py
    uv run python examples/97_openai_runner_shell.py --question "List all files."
    uv run python examples/97_openai_runner_shell.py --model gpt-4o-mini
"""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile

try:
    from agents import Agent, function_tool
except ImportError:
    raise SystemExit(
        "openai-agents not installed.\n"
        "Install it with (from sdk/python/): uv add openai-agents\n"
        "Then run with: uv run python examples/97_openai_runner_shell.py"
    )

# ── Only this line changes ──────────────────────────────────────────────────
# from agents import Runner          # ← original (runs directly on OpenAI)
from agentspan import Runner         # ← agentspan (runs on Agentspan)
# ───────────────────────────────────────────────────────────────────────────

DEFAULT_QUESTION = "Summarize this project in 2 sentences."
DEFAULT_MODEL = "gpt-4o"

# Module-level workspace path set in main() before the agent runs.
_WORKSPACE_DIR: str = ""


def _create_workspace() -> str:
    """Create a temporary workspace with demo files and return its path."""
    workspace = tempfile.mkdtemp(prefix="agentspan_shell_")

    files = {
        "README.md": (
            "# Demo Project\n\n"
            "A tiny demo project for the Agentspan shell runner example.\n"
            "The model can inspect files using shell commands.\n"
        ),
        "src/app.py": 'def greet(name: str) -> str:\n    return f"Hello, {name}!"\n',
        "docs/notes.md": (
            "# Notes\n\n"
            "- Example is intentionally minimal.\n"
            "- Model should inspect files before answering.\n"
        ),
    }
    for rel_path, content in files.items():
        abs_path = os.path.join(workspace, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w") as f:
            f.write(content)

    return workspace


@function_tool
def run_shell(command: str) -> str:
    """Execute a shell command in the workspace directory and return its output.

    Use standard Unix commands (ls, cat, find, grep, head) to inspect files.
    """
    if not _WORKSPACE_DIR:
        return "Error: workspace not initialised"
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=10,
            cwd=_WORKSPACE_DIR,
        )
        output = result.stdout
        if result.stderr:
            output += "\n[stderr] " + result.stderr.strip()
        return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: command timed out"
    except Exception as exc:
        return f"Error: {exc}"


def _build_agent(model: str) -> Agent:
    return Agent(
        name="ShellAssistant",
        model=model,
        instructions=(
            "Answer questions about the workspace. "
            "Use the run_shell tool to inspect files before answering. "
            "Keep responses concise."
        ),
        tools=[run_shell],
    )


def main(model: str, question: str) -> None:
    global _WORKSPACE_DIR
    _WORKSPACE_DIR = _create_workspace()

    print(f"Workspace: {_WORKSPACE_DIR}")
    print(f"Files: {os.listdir(_WORKSPACE_DIR)}\n")

    agent = _build_agent(model)

    result = Runner.run_sync(agent, question)
    print("assistant>", result.final_output)
    print(f"\nExecution ID: {result.execution_id}")
    print("(View full run in the Agentspan UI)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agentspan shell agent (local workspace)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="LLM model to use")
    parser.add_argument("--question", default=DEFAULT_QUESTION, help="Question to ask")
    args = parser.parse_args()
    main(args.model, args.question)
