# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""First-class CLI command execution configuration for agents.

Provides :class:`CliConfig` for declarative CLI tool attachment on
:class:`Agent`, a validation helper, and a factory function that
auto-creates a ``run_command`` tool.

Example::

    from agentspan.agents import Agent, CliConfig

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


class TerminalToolError(RuntimeError):
    """Non-retryable tool failure.

    Causes the Conductor task to be marked FAILED_WITH_TERMINAL_ERROR
    instead of FAILED (which would trigger retries).
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


def _validate_cli_command(command: str, allowed_commands: List[str]) -> None:
    """Validate *command* against the whitelist.

    Strips path prefix (``/usr/bin/git`` → ``git``) before checking.
    Empty whitelist permits all commands.

    Raises:
        ValueError: If the command is not in the whitelist.
    """
    if not allowed_commands:
        return  # no restrictions
    base = os.path.basename(command)
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
    agent_name: str = "",
) -> Any:
    """Create a ``@tool``-decorated ``run_command`` function.

    The returned function can be appended to ``Agent.tools`` directly.
    The tool name is prefixed with the agent name to avoid collisions
    when multiple agents define CLI tools with different allowed commands.
    """
    from agentspan.agents.tool import tool

    task_name = f"{agent_name}_run_command" if agent_name else "run_command"

    @tool(name=task_name)
    def run_command(
        command: str,
        args: list = [],
        cwd: str = "",
        shell: bool = False,
        context_key: str = "",
        context: Any = None,
        _allowed_commands: list = None,
        _allow_shell: bool = None,
        _timeout: int = None,
        _working_dir: str = None,
    ) -> dict:
        """Run a CLI command."""
        if not command or not isinstance(command, str):
            return {
                "status": "error",
                "stdout": "",
                "stderr": "No command provided.",
            }

        # Per-task overrides from server take precedence over closure defaults
        effective_allowed = _allowed_commands if _allowed_commands is not None else allowed_commands
        effective_allow_shell = _allow_shell if _allow_shell is not None else allow_shell
        effective_timeout = _timeout if _timeout is not None else timeout
        effective_working_dir = _working_dir if _working_dir is not None else working_dir

        # Validate against whitelist
        _validate_cli_command(command, effective_allowed)

        # Shell gate
        if shell and not effective_allow_shell:
            raise ValueError(
                "Shell mode is disabled for this agent. "
                "Do not set shell=True."
            )

        # Normalise args
        if args is None:
            args = []
        if not isinstance(args, list):
            args = [str(args)]

        # Resolve working directory
        effective_cwd = cwd if cwd else effective_working_dir

        try:
            if shell:
                # Build a safe shell command string
                cmd_str = command + " " + " ".join(
                    shlex.quote(str(a)) for a in args
                )
                result = subprocess.run(
                    cmd_str,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=effective_timeout,
                    cwd=effective_cwd or None,
                )
            else:
                result = subprocess.run(
                    [command] + [str(a) for a in args],
                    capture_output=True,
                    text=True,
                    timeout=effective_timeout,
                    cwd=effective_cwd or None,
                )

            if result.returncode == 0:
                if context_key and context is not None and hasattr(context, "state"):
                    # Prefer stdout; fall back to stderr (e.g. git clone outputs to stderr)
                    value = result.stdout.strip() or result.stderr.strip()
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
            raise TerminalToolError(
                f"Command timed out after {effective_timeout}s"
            )
        except FileNotFoundError:
            raise TerminalToolError(f"Command not found: {command}")

    # Build dynamic description
    desc = (
        "Run a CLI command directly. "
        f"Timeout: {timeout}s."
    )
    if allowed_commands:
        desc += f" Allowed commands: {', '.join(sorted(allowed_commands))}."
    if not allow_shell:
        desc += " Shell mode is disabled — do not set shell=True."
    desc += (
        " If you need to save a command's output for later pipeline steps, set context_key."
        " Well-known keys: repo, branch, working_dir, issue_number, pr_url, commit_sha."
    )
    run_command._tool_def.description = desc
    run_command._tool_def.tool_type = "cli"
    run_command._tool_def.config = {"allowedCommands": list(allowed_commands)}

    return run_command
