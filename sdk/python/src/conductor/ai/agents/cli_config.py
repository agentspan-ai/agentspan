# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""First-class CLI command execution configuration for agents.

Provides :class:`CliConfig` for declarative CLI tool attachment on
:class:`Agent`, a validation helper, and a factory function that
auto-creates a ``run_command`` tool.

Example::

    from conductor.ai.agents import Agent, CliConfig

    # Simple — just flip the flag
    agent = Agent(
        name="ops",
        model="openai/gpt-4o",
        cli_commands=True,
        cli_allowed_commands=["git", "gh", "curl"],
    )

    # Full control
    agent = Agent(
        name="ops",
        model="openai/gpt-4o",
        cli_config=CliConfig(
            allowed_commands=["git", "gh"],
            timeout=60,
            allow_shell=True,
        ),
    )
"""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class TerminalToolError(Exception):
    """Non-retryable CLI tool failure (e.g. command not found, timeout).

    When raised, causes the Conductor task to be marked
    ``FAILED_WITH_TERMINAL_ERROR`` instead of retrying.
    """


@dataclass
class CliConfig:
    """Configuration for first-class CLI command execution on an Agent.

    Attributes:
        enabled: Whether CLI execution is active (default ``True``).
        allowed_commands: Command whitelist (e.g. ``["git", "gh"]``).
            Empty list means **no restrictions**.
        timeout: Maximum execution time in seconds (default ``30``).
        working_dir: Default working directory for commands.
        allow_shell: Config-level gate: can the LLM use ``shell=True``?
    """

    enabled: bool = True
    allowed_commands: List[str] = field(default_factory=list)
    timeout: int = 30
    working_dir: Optional[str] = None
    allow_shell: bool = False


# ── Validation ─────────────────────────────────────────────────────────


def _executable_of(command: str) -> str:
    """Return the executable token of *command*.

    Accepts either a bare executable (``"gh"``) or a full command line
    (``"gh repo list --limit 5"``) — LLMs frequently pass the latter — and
    returns the first token. Falls back to whitespace splitting if the string
    is not validly quoted.
    """
    if not command:
        return command
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    return tokens[0] if tokens else command


def _validate_cli_command(command: str, allowed_commands: List[str]) -> None:
    """Validate *command* against the whitelist.

    Keys off the executable, so both a bare command (``git``) and a full command
    line (``git status -s``) validate the same way. Strips path prefix
    (``/usr/bin/git`` → ``git``) before checking. Empty whitelist permits all.

    Raises:
        ValueError: If the executable is not in the whitelist.
    """
    if not allowed_commands:
        return  # no restrictions
    base = os.path.basename(_executable_of(command))
    if base not in allowed_commands:
        raise ValueError(
            f"Command '{base}' is not allowed. "
            f"Allowed commands: {', '.join(sorted(allowed_commands))}"
        )


# ── Tool factory ───────────────────────────────────────────────────────


def _make_cli_tool(
    allowed_commands: List[str],
    timeout: int = 30,
    working_dir: Optional[str] = None,
    allow_shell: bool = False,
    agent_name: Optional[str] = None,
) -> Any:
    """Create a ``@tool``-decorated ``run_command`` function.

    The returned function can be appended to ``Agent.tools`` directly.
    """
    from conductor.ai.agents.tool import tool

    task_name = f"{agent_name}_run_command" if agent_name else "run_command"

    @tool(name=task_name)
    def run_command(
        command: str,
        args: list = [],
        cwd: str = "",
        shell: bool = False,
        context_key: str = "",
        context: Any = None,
    ) -> dict:
        """Run a CLI command."""
        if not command or not isinstance(command, str):
            return {
                "status": "error",
                "stdout": "",
                "stderr": "No command provided.",
            }

        # Models frequently pass the entire command line as `command`
        # (e.g. "gh repo list --limit 5") rather than splitting executable/args.
        # Tokenize so both styles work: validation keys off the executable and
        # execution gets a proper argv.
        try:
            tokens = shlex.split(command)
        except ValueError as e:
            return {
                "status": "error",
                "stdout": "",
                "stderr": f"Could not parse command: {e}",
            }
        if not tokens:
            return {
                "status": "error",
                "stdout": "",
                "stderr": "No command provided.",
            }
        executable = tokens[0]

        # Validate against whitelist (on the executable)
        _validate_cli_command(executable, allowed_commands)

        # Shell gate
        if shell and not allow_shell:
            raise ValueError("Shell mode is disabled for this agent. Do not set shell=True.")

        # Normalise args
        if args is None:
            args = []
        if not isinstance(args, list):
            args = [str(args)]

        # Merge any args embedded in the command line with the explicit args list
        argv = tokens[1:] + [str(a) for a in args]

        # Resolve working directory
        effective_cwd = cwd if cwd else working_dir

        try:
            if shell:
                # Build a safe shell command string
                cmd_str = " ".join(shlex.quote(str(a)) for a in [executable] + argv)
                result = subprocess.run(
                    cmd_str,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=effective_cwd or None,
                )
            else:
                result = subprocess.run(
                    [executable] + argv,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=effective_cwd or None,
                )

            if result.returncode == 0:
                # Save stdout to context state if context_key is set
                if context_key and context is not None:
                    value = (result.stdout or "").strip() or (result.stderr or "").strip()
                    if value:
                        context.state[context_key] = value
                return {
                    "status": "success",
                    "exit_code": 0,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            else:
                return {
                    "status": "error",
                    "exit_code": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }

        except subprocess.TimeoutExpired:
            raise TerminalToolError(f"Command timed out after {timeout}s")
        except FileNotFoundError:
            raise TerminalToolError(f"Command not found: {command}")
        except Exception as e:
            raise TerminalToolError(str(e))

    # Build dynamic description
    desc = f"Run a CLI command directly. Timeout: {timeout}s."
    if allowed_commands:
        desc += f" Allowed commands: {', '.join(sorted(allowed_commands))}."
    if not allow_shell:
        desc += " Shell mode is disabled — do not set shell=True."
    desc += (
        " If you need to save a command's output for later pipeline steps,"
        " set context_key. Well-known keys: repo, branch, working_dir,"
        " issue_number, pr_url, commit_sha."
    )
    run_command._tool_def.description = desc

    return run_command
