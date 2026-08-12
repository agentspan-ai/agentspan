"""TUI commands — /help, /signal, /change, /dashboard, /agents, etc."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class CommandResult:
    """Result of parsing and executing a TUI command."""

    handled: bool = False
    output: Optional[str] = None
    action: Optional[str] = None  # "quit", "disconnect", "stop", "cancel", "dashboard", etc.
    agent_name: Optional[str] = None
    message: Optional[str] = None


HELP_TEXT = """\
Commands:
  <message>                        Chat with the orchestrator (create/manage agents)
  /agents                          List all agents with status
  /dashboard                       Toggle dashboard view
  /signal <agent> <message>        Send transient signal to a running agent
  /change <agent> <instruction>    Permanently modify an agent's behavior
  /pause <agent>                   Pause a scheduled agent
  /resume <agent>                  Resume a paused agent
  /status [agent]                  Show status of an agent or the orchestrator
  /notifications                   Show unread notifications
  /sessions                        List all sessions
  /switch <session-id>             Switch to a different active session
  /new                             Start a new session
  /stop                            Gracefully stop the orchestrator
  /cancel                          Immediately terminate
  /disconnect                      Exit without stopping — resume later with --resume
  /help                            Show this message
  quit / exit                      Gracefully stop and exit

Resume a previous session:
  python -m autopilot.tui.app --resume
"""


def parse_command(raw: str) -> CommandResult:
    """Parse user input and return a CommandResult.

    Returns handled=True for commands that are fully handled here (like /help).
    Returns handled=False with action set for commands that need the TUI to act.
    """
    text = raw.strip()
    if not text:
        return CommandResult(handled=True)

    lower = text.lower()

    # Quit/exit
    if lower in ("quit", "exit"):
        return CommandResult(handled=True, action="quit")

    if lower == "/disconnect":
        return CommandResult(handled=True, action="disconnect")

    if lower in ("/stop", "stop"):
        return CommandResult(handled=True, action="stop")

    if lower == "/cancel":
        return CommandResult(handled=True, action="cancel")

    if lower in ("/help", "help"):
        return CommandResult(handled=True, output=HELP_TEXT)

    if lower == "/agents":
        return CommandResult(handled=True, action="list_agents")

    if lower == "/dashboard":
        return CommandResult(handled=True, action="dashboard")

    if lower == "/notifications":
        return CommandResult(handled=True, action="notifications")

    if lower == "/sessions":
        return CommandResult(handled=True, action="list_sessions")

    if lower == "/new":
        return CommandResult(handled=True, action="new_session")

    # /switch <session-id>
    if lower == "/switch" or lower.startswith("/switch "):
        session_id = text[7:].strip() if len(text) > 7 else ""
        if not session_id:
            return CommandResult(handled=True, output="Usage: /switch <session-id>\n")
        return CommandResult(handled=True, action="switch_session", message=session_id)

    # /signal <agent> <message>
    if lower.startswith("/signal "):
        parts = text[8:].strip().split(None, 1)
        if len(parts) < 2:
            return CommandResult(handled=True, output="Usage: /signal <agent-name> <message>\n")
        return CommandResult(
            handled=True,
            action="signal",
            agent_name=parts[0],
            message=parts[1],
        )

    # /change <agent> <instruction>
    if lower.startswith("/change "):
        parts = text[8:].strip().split(None, 1)
        if len(parts) < 2:
            return CommandResult(
                handled=True, output="Usage: /change <agent-name> <instruction>\n"
            )
        return CommandResult(
            handled=True,
            action="change",
            agent_name=parts[0],
            message=parts[1],
        )

    # /pause <agent>
    if lower.startswith("/pause "):
        agent_name = text[7:].strip()
        if not agent_name:
            return CommandResult(handled=True, output="Usage: /pause <agent-name>\n")
        return CommandResult(handled=True, action="pause", agent_name=agent_name)

    # /resume <agent>
    if lower.startswith("/resume "):
        agent_name = text[8:].strip()
        if not agent_name:
            return CommandResult(handled=True, output="Usage: /resume <agent-name>\n")
        return CommandResult(handled=True, action="resume", agent_name=agent_name)

    # /status [agent]
    if lower == "/status" or lower.startswith("/status "):
        agent_name = text[8:].strip() if len(text) > 7 else None
        return CommandResult(handled=True, action="status", agent_name=agent_name or None)

    # Not a command — it's a chat message
    return CommandResult(handled=False, message=text)
