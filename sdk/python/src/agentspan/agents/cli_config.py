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

from contextvars import ContextVar
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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


_cli_runtime_overrides: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "agentspan_cli_runtime_overrides",
    default=None,
)


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


def _set_cli_runtime_overrides(
    *,
    allowed_commands: Optional[List[str]] = None,
    allow_shell: Optional[bool] = None,
    timeout: Optional[int] = None,
    working_dir: Optional[str] = None,
):
    """Install per-task CLI policy overrides for the current execution context."""
    overrides: Dict[str, Any] = {}
    if allowed_commands is not None:
        overrides["allowed_commands"] = list(allowed_commands)
    if allow_shell is not None:
        overrides["allow_shell"] = bool(allow_shell)
    if timeout is not None:
        overrides["timeout"] = int(timeout)
    if working_dir is not None:
        overrides["working_dir"] = working_dir
    return _cli_runtime_overrides.set(overrides or None)


def _reset_cli_runtime_overrides(token) -> None:
    """Reset the current per-task CLI policy overrides."""
    _cli_runtime_overrides.reset(token)


def _get_effective_cli_policy(
    *,
    allowed_commands: List[str],
    allow_shell: bool,
    timeout: int,
    working_dir: Optional[str],
) -> Dict[str, Any]:
    """Resolve effective CLI policy from per-task overrides with config fallback."""
    overrides = _cli_runtime_overrides.get() or {}
    return {
        "allowed_commands": list(overrides.get("allowed_commands", allowed_commands)),
        "allow_shell": bool(overrides.get("allow_shell", allow_shell)),
        "timeout": int(overrides.get("timeout", timeout)),
        "working_dir": overrides.get("working_dir", working_dir),
    }


# ── Tool factory ───────────────────────────────────────────────────────


def _make_cli_tool(
    allowed_commands: List[str],
    timeout: int = 30,
    working_dir: Optional[str] = None,
    allow_shell: bool = False,
) -> Any:
    """Create a ``@tool``-decorated ``run_command`` function.

    The returned function can be appended to ``Agent.tools`` directly.
    """
    from agentspan.agents.tool import tool

    @tool(name="run_command")
    def run_command(
        command: str,
        args: list = [],
        cwd: str = "",
        shell: bool = False,
    ) -> dict:
        """Run a CLI command."""
        if not command or not isinstance(command, str):
            return {
                "status": "error",
                "stdout": "",
                "stderr": "No command provided.",
            }

        policy = _get_effective_cli_policy(
            allowed_commands=allowed_commands,
            allow_shell=allow_shell,
            timeout=timeout,
            working_dir=working_dir,
        )

        # Validate against whitelist
        _validate_cli_command(command, policy["allowed_commands"])

        # Shell gate
        if shell and not policy["allow_shell"]:
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
        effective_cwd = cwd if cwd else policy["working_dir"]

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
                    timeout=policy["timeout"],
                    cwd=effective_cwd or None,
                )
            else:
                result = subprocess.run(
                    [command] + [str(a) for a in args],
                    capture_output=True,
                    text=True,
                    timeout=policy["timeout"],
                    cwd=effective_cwd or None,
                )

            if result.returncode == 0:
                return {
                    "status": "success",
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            else:
                return {
                    "status": "error",
                    "stdout": result.stdout,
                    "stderr": (result.stderr or "")
                    + f"\nExit code: {result.returncode}",
                }

        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "stdout": "",
                "stderr": f"Command timed out after {policy['timeout']}s",
            }
        except FileNotFoundError:
            return {
                "status": "error",
                "stdout": "",
                "stderr": f"Command not found: {command}",
            }
        except Exception as e:
            return {
                "status": "error",
                "stdout": "",
                "stderr": str(e),
            }

    # Build dynamic description
    desc = (
        "Run a CLI command directly. "
        f"Timeout: {timeout}s."
    )
    if allowed_commands:
        desc += f" Allowed commands: {', '.join(sorted(allowed_commands))}."
    if not allow_shell:
        desc += " Shell mode is disabled — do not set shell=True."
    run_command._tool_def.description = desc
    run_command._tool_def.tool_type = "cli"
    run_command._tool_def.config = {
        "allowedCommands": list(allowed_commands),
        "allowShell": allow_shell,
        "timeout": timeout,
    }
    if working_dir:
        run_command._tool_def.config["workingDir"] = working_dir

    return run_command
