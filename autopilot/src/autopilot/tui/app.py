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

from agentspan.agents import Agent, AgentRuntime, EventType, tool, wait_for_message_tool

from autopilot.tui.commands import CommandResult, HELP_TEXT, parse_command
from autopilot.tui.events import format_event


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SESSION_FILE = Path("/tmp/agentspan_claw.session")
_SEPARATOR = "\u2500" * 62
_THIN_SEP = "\u2504" * 62


class AgentState(enum.Enum):
    BUSY = "busy"
    WAITING = "waiting"
    DONE = "done"


# ---------------------------------------------------------------------------
# Orchestrator agent builder
# ---------------------------------------------------------------------------

def build_orchestrator():
    """Build the Claw orchestrator agent."""

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
    def list_available_agents() -> str:
        """List all agent directories under ~/.agentspan/autopilot/agents/."""
        agents_dir = Path.home() / ".agentspan" / "autopilot" / "agents"
        if not agents_dir.exists():
            return "No agents directory found. No agents created yet."
        dirs = [d.name for d in agents_dir.iterdir() if d.is_dir() and (d / "agent.yaml").exists()]
        if not dirs:
            return "No agents found."
        return "Available agents:\n" + "\n".join(f"  - {d}" for d in sorted(dirs))

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

    agent = Agent(
        name="claw_orchestrator",
        model=model,
        tools=[
            receive_message,
            reply_to_user,
            list_available_agents,
            read_agent_config,
        ],
        max_turns=100_000,
        stateful=True,
        instructions=f"""You are the Agentspan Claw orchestrator — an AI assistant that helps users create and manage autonomous agents.

You can help users:
- Understand what agents are available
- Create new agents by expanding their requirements into full specifications
- Monitor and manage running agents
- Answer questions about agent capabilities

Available tools:
- reply_to_user(message): Send your response to the user
- list_available_agents(): List all configured agents
- read_agent_config(agent_name): Read an agent's configuration

When the user asks to create an agent, help them think through:
1. What the agent should do (the task)
2. What integrations it needs (email, web search, etc.)
3. How often it should run (schedule, event-driven, always-on)
4. What credentials it needs

Keep responses concise and actionable.

Repeat indefinitely:
1. Call wait_for_message to receive the next user message.
2. Process the request.
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
            # TODO: resolve agent_name to execution_id, then signal
            _append(f"  Signal sent to {cmd.agent_name}: {cmd.message}\n")
            return

        if cmd.action == "change" and cmd.agent_name and cmd.message:
            # Send as chat message — orchestrator will handle the change
            _append(f"\n{_THIN_SEP}\nYou: change {cmd.agent_name}: {cmd.message}\n{_THIN_SEP}\n")
            runtime.send_message(execution_id, {"text": f"Change agent '{cmd.agent_name}': {cmd.message}"})
            return

        if cmd.action == "list_agents":
            _append(f"\n{_THIN_SEP}\nYou: list agents\n{_THIN_SEP}\n")
            runtime.send_message(execution_id, {"text": "List all available agents and their status."})
            return

        if cmd.action == "status":
            msg = f"Show status of agent '{cmd.agent_name}'" if cmd.agent_name else "Show overall status"
            _append(f"\n{_THIN_SEP}\nYou: {msg}\n{_THIN_SEP}\n")
            runtime.send_message(execution_id, {"text": msg})
            return

        if cmd.action in ("dashboard", "notifications"):
            _append(f"  [{cmd.action}] Coming soon.\n")
            return

        if cmd.action in ("pause", "resume") and cmd.agent_name:
            _append(f"\n{_THIN_SEP}\nYou: {cmd.action} {cmd.agent_name}\n{_THIN_SEP}\n")
            runtime.send_message(execution_id, {"text": f"{cmd.action.title()} agent '{cmd.agent_name}'."})
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
