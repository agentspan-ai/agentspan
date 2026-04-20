# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""OpenAI Agents SDK migration — agent with shell tool.

An openai-agents script that gives an agent shell access to a local
workspace, migrated to Agentspan by changing ONE line.

Before (runs directly against OpenAI):
    from agents import Runner

After (runs on Agentspan — durable, observable, scalable):
    from agentspan import Runner

The diff:
    -from agents import Runner
    +from agentspan import Runner

The agent, @function_tool definition, and Runner.run_sync() call are
unchanged. Agentspan records every shell command the model executes in
the execution history — visible in the Agentspan UI.

Requirements:
    - uv add openai-agents          (from sdk/python/)
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
import shlex
import subprocess
import tempfile

try:
    from agents import Agent, function_tool
except ImportError:
    raise SystemExit(
        "openai-agents not installed.\n"
        "Install it with (from sdk/python/): uv add openai-agents\n"
        "Then run: uv run python examples/97_openai_runner_shell.py"
    )

# ── Only this line changes ──────────────────────────────────────────────────
# from agents import Runner          # ← original (runs directly on OpenAI)
from agentspan import Runner         # ← agentspan (runs on Agentspan)
# ───────────────────────────────────────────────────────────────────────────

DEFAULT_QUESTION = "Summarize this project in 2 sentences."
DEFAULT_MODEL = "gpt-4o"


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


def _make_shell_tool(workspace: str):
    """Return a @function_tool that runs commands inside *workspace*."""

    @function_tool
    def run_shell(command: str) -> str:
        """Run a shell command in the workspace and return its output.

        Use standard Unix commands (ls, cat, find, grep) to inspect files.
        """
        try:
            result = subprocess.run(
                shlex.split(command),
                capture_output=True,
                text=True,
                timeout=10,
                cwd=workspace,
            )
            output = result.stdout
            if result.stderr:
                output += "\n[stderr] " + result.stderr.strip()
            return output.strip() or "(no output)"
        except subprocess.TimeoutExpired:
            return "Error: command timed out"
        except Exception as exc:
            return f"Error: {exc}"

    return run_shell


def main(model: str, question: str) -> None:
    workspace = _create_workspace()
    print(f"Workspace: {workspace}")
    print(f"Files: {os.listdir(workspace)}\n")

    agent = Agent(
        name="ShellAssistant",
        model=model,
        instructions=(
            "Answer questions about the workspace. "
            "Use the run_shell tool to inspect files before answering. "
            "Keep responses concise."
        ),
        tools=[_make_shell_tool(workspace)],
    )

    result = Runner.run_sync(agent, question)
    print("assistant>", result.final_output)
    print(f"\nExecution ID: {result.execution_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agentspan shell agent")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    args = parser.parse_args()
    main(args.model, args.question)
