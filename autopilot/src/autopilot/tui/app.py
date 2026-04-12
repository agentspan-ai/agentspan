#!/usr/bin/env python3
"""Agentspan Claw TUI — chat interface for creating and managing autonomous agents.

Usage:
    python -m autopilot.tui.app                          # new session
    python -m autopilot.tui.app --resume                 # resume last session
    python -m autopilot.tui.app --agent deep_researcher  # run a specific agent interactively

Requirements:
    - pip install prompt_toolkit
    - Agentspan server running (default: localhost:6767)
    - AGENTSPAN_LLM_MODEL (default: openai/gpt-4o)
"""

from __future__ import annotations

import argparse
import enum
import os
import queue
import sys
import threading
from pathlib import Path

os.environ.setdefault("AGENTSPAN_LOG_LEVEL", "WARNING")

from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.widgets import TextArea

import yaml

from agentspan.agents import Agent, AgentRuntime, EventType, tool, wait_for_message_tool

from autopilot.config import AutopilotConfig
from autopilot.tui.commands import CommandResult, HELP_TEXT, parse_command
from autopilot.tui.dashboard import render_dashboard
from autopilot.tui.events import format_event
from autopilot.tui.notifications import Notification, NotificationManager


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SESSION_FILE = Path.home() / ".agentspan" / "autopilot" / "session"
_SEPARATOR = "\u2500" * 62
_THIN_SEP = "\u2504" * 62


class AgentState(enum.Enum):
    BUSY = "busy"
    WAITING = "waiting"
    DONE = "done"


# ---------------------------------------------------------------------------
# Agent discovery from local filesystem
# ---------------------------------------------------------------------------

def _discover_agents(config: AutopilotConfig) -> list[dict]:
    """Read agent directories from disk and return agent info dicts."""
    agents_dir = config.agents_dir
    if not agents_dir.exists():
        return []

    agents = []
    for d in sorted(agents_dir.iterdir()):
        if not d.is_dir():
            continue
        yaml_path = d / "agent.yaml"
        if not yaml_path.exists():
            continue

        info: dict = {"name": d.name, "status": "active", "last_run": "", "trigger": ""}
        try:
            raw = yaml.safe_load(yaml_path.read_text()) or {}
            trigger_cfg = raw.get("trigger", {})
            if isinstance(trigger_cfg, dict):
                info["trigger"] = trigger_cfg.get("type", "")
            elif isinstance(trigger_cfg, str):
                info["trigger"] = trigger_cfg
            metadata = raw.get("metadata", {})
            if isinstance(metadata, dict):
                info["last_run"] = metadata.get("last_deployed", "")
        except Exception:
            info["status"] = "error"

        agents.append(info)

    return agents


# ---------------------------------------------------------------------------
# Orchestrator agent builder
# ---------------------------------------------------------------------------

def build_orchestrator():
    """Build the Claw orchestrator agent with full orchestrator toolset."""

    model = os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o")

    receive_message = wait_for_message_tool(
        name="wait_for_message",
        description="Wait for the next user message. Payload has a 'text' field.",
    )

    @tool
    def reply_to_user(message: str) -> str:
        """Send your response to the user. Call this when done with the current request."""
        return "ok"

    @tool
    def read_agent_config(agent_name: str) -> str:
        """Read an agent's configuration (agent.yaml and expanded_prompt.md)."""
        agent_dir = Path.home() / ".agentspan" / "autopilot" / "agents" / agent_name
        if not agent_dir.exists():
            return f"Error: agent '{agent_name}' not found."
        result = []
        yaml_path = agent_dir / "agent.yaml"
        if yaml_path.exists():
            result.append(f"=== agent.yaml ===\n{yaml_path.read_text()}")
        prompt_path = agent_dir / "expanded_prompt.md"
        if prompt_path.exists():
            result.append(f"=== expanded_prompt.md ===\n{prompt_path.read_text()}")
        return "\n\n".join(result) if result else f"Agent '{agent_name}' has no config files."

    # Core TUI tools + all orchestrator creation/management/credential tools
    all_tools = [
        receive_message,
        reply_to_user,
        read_agent_config,
    ] + get_orchestrator_tools()

    agent = Agent(
        name="claw_orchestrator",
        model=model,
        tools=all_tools,
        max_turns=100_000,
        stateful=True,
        instructions="""\
You are the Agentspan Claw orchestrator — an AI assistant that autonomously
creates, deploys, and manages agents on behalf of the user.

Your job is to turn lazy, minimal user prompts into fully functional agents.

## Workflow

When a user asks you to create an agent:

1. Ask 1-2 critical clarifying questions (only when there is no reasonable default).
2. Call expand_prompt() with the user's request and any clarifications.
3. Use the returned template to generate a complete YAML agent specification.
4. Call generate_agent() with the YAML spec to create the agent files.
5. Call resolve_integrations() to check what's available and what's missing.
6. Call check_credentials() to verify credential requirements.
7. If everything is ready, call deploy_agent() to start the agent.
8. Report back to the user with what was created and deployed.

## Agent Management

When a user asks to manage existing agents:

- Use list_agents() to show all agents and their status.
- Use get_agent_status() for detailed info on a specific agent.
- Use signal_agent() for transient, one-time instructions to a running agent.
- Use update_agent() for permanent changes to an agent's behavior.
- Use pause_agent() and resume_agent() to control execution.
- Use archive_agent() to deactivate an agent while keeping its files.
- Use get_notifications() to check for recent agent outputs and alerts.
- Use read_agent_config() to read raw config files for a specific agent.

## Credentials

- Use check_credentials() to see what credentials an agent needs.
- Use prompt_credentials() to guide the user through setting up a credential.

## Principles

- Be proactive: smart-default everything you can.
- Be concise: don't over-explain unless asked.
- Be honest: if something fails, say what went wrong and suggest a fix.
- Never invent credentials — check what's needed and guide the user to set them up.

## Interaction Loop

Repeat indefinitely:
1. Call wait_for_message to receive the next user message.
2. Process the request using available tools.
3. Call reply_to_user with your response.
4. Return to step 1.
""",
    )

    return agent


# ---------------------------------------------------------------------------
# Agent runner builder (for running specific agents interactively)
# ---------------------------------------------------------------------------

def build_interactive_agent(agent_name: str):
    """Build an agent for interactive running from its directory."""
    agents_dir = Path.home() / ".agentspan" / "autopilot" / "agents" / agent_name

    # Try to find a run_interactive.py in the agent directory
    interactive_script = agents_dir / "run_interactive.py"
    if interactive_script.exists():
        return None  # Signal to use the script directly

    # Try to load agent.yaml via the loader
    try:
        from autopilot.loader import load_agent
        agent = load_agent(agents_dir)
        return agent
    except Exception as e:
        print(f"Error loading agent '{agent_name}': {e}")
        return None


# ---------------------------------------------------------------------------
# TUI REPL
# ---------------------------------------------------------------------------

def _run_tui_repl(
    runtime: AgentRuntime,
    handle,
    execution_id: str,
) -> None:
    """Full-screen TUI: scrollable output on top, persistent input on bottom."""

    config = AutopilotConfig.from_env()
    notif_manager = NotificationManager(config)

    agent_state = [AgentState.BUSY]
    _event_queue: queue.Queue = queue.Queue()
    _stop_requested = [False]

    # ── Output area (read-only, scrollable) ────────────────────────
    output_area = TextArea(
        text=(
            f"{'=' * 62}\n"
            f"  Agentspan Claw\n"
            f"  Session: {execution_id[:16]}...\n"
            f"  Type /help for commands, quit to exit\n"
            f"{'=' * 62}\n\n"
        ),
        read_only=True,
        scrollbar=True,
        wrap_lines=True,
        focusable=False,
    )

    def _append(text: str) -> None:
        if not text:
            return
        output_area.text += text
        output_area.buffer.cursor_position = len(output_area.text)
        if app.is_running:
            app.invalidate()

    # ── Input handler ──────────────────────────────────────────────

    def _on_input(buff: Buffer) -> None:
        raw = buff.text.strip()
        if not raw:
            return

        cmd = parse_command(raw)

        # Handle exit commands
        if cmd.action in ("quit", "stop"):
            _append("Stopping...\n")
            _stop_requested[0] = True
            handle.stop()
            threading.Timer(1.0, lambda: app.exit() if app.is_running else None).start()
            return

        if cmd.action == "disconnect":
            _append(f"Disconnected. Resume with: python -m autopilot.tui.app --resume\n")
            _stop_requested[0] = True
            threading.Timer(0.5, lambda: app.exit() if app.is_running else None).start()
            return

        if cmd.action == "cancel":
            _append("Cancelling...\n")
            _stop_requested[0] = True
            handle.cancel()
            threading.Timer(0.5, lambda: app.exit() if app.is_running else None).start()
            return

        # Handle informational commands
        if cmd.output:
            _append(cmd.output + "\n")
            return

        # Handle action commands that need server interaction
        if cmd.action == "signal" and cmd.agent_name and cmd.message:
            # Signal the orchestrator's execution — the agent_name is passed
            # as context so the orchestrator can route it to the right agent.
            runtime.signal(execution_id, f"[signal:{cmd.agent_name}] {cmd.message}")
            _append(f"  Signal sent to {cmd.agent_name}: {cmd.message}\n")
            return

        if cmd.action == "change" and cmd.agent_name and cmd.message:
            # Send as chat message — orchestrator will handle the change
            _append(f"\n{_THIN_SEP}\nYou: change {cmd.agent_name}: {cmd.message}\n{_THIN_SEP}\n")
            runtime.send_message(execution_id, {"text": f"Change agent '{cmd.agent_name}': {cmd.message}"})
            return

        if cmd.action == "list_agents":
            agents = _discover_agents(config)
            if not agents:
                _append("\n  No agents found.\n")
            else:
                _append(f"\n  {'Name':<24} {'Status':<10} {'Trigger'}\n")
                _append(f"  {'----':<24} {'------':<10} {'-------'}\n")
                for a in agents:
                    _append(f"  {a['name']:<24} {a['status']:<10} {a['trigger']}\n")
                _append("")
            return

        if cmd.action == "status":
            if cmd.agent_name:
                # Show status for a specific agent
                agents = _discover_agents(config)
                found = [a for a in agents if a["name"] == cmd.agent_name]
                if found:
                    a = found[0]
                    _append(
                        f"\n  Agent: {a['name']}\n"
                        f"  Status: {a['status']}\n"
                        f"  Trigger: {a['trigger']}\n"
                        f"  Last run: {a['last_run'] or 'never'}\n"
                    )
                else:
                    _append(f"\n  Agent '{cmd.agent_name}' not found.\n")
            else:
                # Overall status
                agents = _discover_agents(config)
                state_label = agent_state[0].value
                _append(
                    f"\n  Session: {execution_id}\n"
                    f"  Orchestrator: {state_label}\n"
                    f"  Agents: {len(agents)} configured\n"
                    f"  Notifications: {notif_manager.unread_count()} unread\n"
                )
            return

        if cmd.action == "dashboard":
            agents = _discover_agents(config)
            notifs = [
                {
                    "agent_name": n.agent_name,
                    "timestamp": n.timestamp,
                    "summary": n.summary,
                    "priority": n.priority,
                    "read": n.read,
                }
                for n in notif_manager.get_all(limit=10)
            ]
            _append(render_dashboard(agents, notifs))
            return

        if cmd.action == "notifications":
            unread = notif_manager.get_unread()
            if not unread:
                _append("\n  No unread notifications.\n")
            else:
                _append(f"\n  Unread notifications ({len(unread)}):\n")
                for n in unread:
                    icon = {"urgent": "(!)", "normal": "( )", "info": "(i)"}.get(n.priority, "( )")
                    _append(f"  {icon} {n.timestamp[:16]}  {n.agent_name}: {n.summary}\n")
                _append("")
            return

        if cmd.action in ("pause", "resume") and cmd.agent_name:
            # Signal the orchestrator to pause/resume the agent
            runtime.signal(
                execution_id,
                f"[{cmd.action}:{cmd.agent_name}]",
            )
            _append(f"  {cmd.action.title()} signal sent for {cmd.agent_name}.\n")
            return

        # Normal chat message
        if cmd.message:
            _append(f"\n{_THIN_SEP}\nYou: {cmd.message}\n{_THIN_SEP}\n")
            if agent_state[0] == AgentState.BUSY:
                _append("  (queued \u2014 agent is busy)\n")
            runtime.send_message(execution_id, {"text": cmd.message})

    input_area = TextArea(
        height=1,
        prompt="You: ",
        multiline=False,
        accept_handler=_on_input,
        focusable=True,
    )

    # ── Key bindings ───────────────────────────────────────────────
    kb = KeyBindings()

    @kb.add("c-c")
    def _ctrl_c(event):
        if _stop_requested[0]:
            event.app.exit()
            return
        _stop_requested[0] = True
        _append("\n\nCtrl+C \u2014 stopping (Ctrl+C again to force exit)...\n")
        handle.stop()

    @kb.add("pageup")
    def _page_up(event):
        output_area.buffer.cursor_up(count=20)
        app.invalidate()

    @kb.add("pagedown")
    def _page_down(event):
        output_area.buffer.cursor_position = len(output_area.text)
        app.invalidate()

    # ── Layout ─────────────────────────────────────────────────────
    layout = Layout(
        HSplit([
            output_area,
            Window(height=1, char="\u2501"),
            input_area,
        ]),
        focused_element=input_area,
    )

    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=True,
    )

    # ── Stream thread ──────────────────────────────────────────────
    def _stream_events():
        for event in handle.stream():
            _event_queue.put(event)

    threading.Thread(target=_stream_events, daemon=True).start()

    # ── Event consumer thread ──────────────────────────────────────
    def _consume_events():
        while True:
            try:
                event = _event_queue.get(timeout=1.0)
            except queue.Empty:
                if _stop_requested[0]:
                    if app.is_running:
                        app.exit()
                    return
                continue

            if event.type == EventType.WAITING:
                agent_state[0] = AgentState.WAITING
                _append(f"{_SEPARATOR}\n")
            elif event.type in (EventType.TOOL_CALL, EventType.THINKING):
                agent_state[0] = AgentState.BUSY
            elif event.type in (EventType.DONE, EventType.ERROR):
                agent_state[0] = AgentState.DONE
                text = format_event(event)
                _append(text)
                if event.type == EventType.DONE and event.output:
                    _append(f"\n{'--- Claw ' + '-' * 53}\n{event.output}\n")
                _append("\nSession ended.\n")
                if app.is_running:
                    app.exit()
                return

            text = format_event(event)
            _append(text)

    threading.Thread(target=_consume_events, daemon=True).start()

    # ── Run the TUI ────────────────────────────────────────────────
    app.run()


# ---------------------------------------------------------------------------
# CLI + main
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Agentspan Claw TUI \u2014 manage autonomous agents.",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume the last session.",
    )
    parser.add_argument(
        "--session-file", type=Path, default=SESSION_FILE,
        help=f"Session file path (default: {SESSION_FILE}).",
    )
    parser.add_argument(
        "--agent", type=str, default=None,
        help="Run a specific agent interactively instead of the orchestrator.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    # Build the agent
    if args.agent:
        # Check for run_interactive.py script first
        agent_dir = Path.home() / ".agentspan" / "autopilot" / "agents" / args.agent
        interactive_script = agent_dir / "run_interactive.py"
        if interactive_script.exists():
            print(f"Running interactive script for '{args.agent}'...")
            os.execvp(sys.executable, [sys.executable, str(interactive_script)])
            return
        agent = build_interactive_agent(args.agent)
        if agent is None:
            print(f"Could not load agent '{args.agent}'.")
            raise SystemExit(1)
    else:
        agent = build_orchestrator()

    # Ensure session file directory exists
    args.session_file.parent.mkdir(parents=True, exist_ok=True)

    with AgentRuntime() as runtime:
        if args.resume:
            if not args.session_file.exists():
                print(f"No session file found at {args.session_file}.")
                print("Start a new session first (without --resume).")
                raise SystemExit(1)
            saved_eid = args.session_file.read_text().strip()
            print(f"Resuming session: {saved_eid}")
            handle = runtime.resume(saved_eid, agent)
            execution_id = handle.execution_id
        else:
            handle = runtime.start(
                agent,
                "Begin. You are the Agentspan Claw orchestrator. Wait for the user's first message.",
            )
            execution_id = handle.execution_id
            args.session_file.write_text(execution_id)

        _run_tui_repl(runtime, handle, execution_id)


if __name__ == "__main__":
    main()
