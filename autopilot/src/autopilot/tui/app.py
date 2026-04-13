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
import logging
import os
import queue
import sys
import threading
import traceback
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
from autopilot.orchestrator.tools import get_orchestrator_tools
from autopilot.tui.commands import CommandResult, HELP_TEXT, parse_command
from autopilot.tui.dashboard import render_dashboard
from autopilot.tui.events import format_event, render_welcome
from autopilot.tui.notifications import Notification, NotificationManager
from autopilot.tui.poller import DashboardPoller

logger = logging.getLogger(__name__)


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
# TUI-safe credential acquisition
# ---------------------------------------------------------------------------

def _make_tui_safe_acquire_credentials(append_fn):
    """Create a TUI-safe version of acquire_credentials.

    Instead of calling input() (which crashes prompt_toolkit), this version:
    - For OAuth flows: opens the browser and shows instructions in the output area.
      The local callback server captures the token without terminal input.
    - For API keys: shows the URL and instructions. Returns a message telling
      the orchestrator to ask the user to paste the key via chat.
    - For AWS: reads from ~/.aws/credentials. Falls back to instructions.
    - For manual: returns instructions for the user to provide via chat.

    Args:
        append_fn: Function to append text to the TUI output area.

    Returns:
        A @tool-decorated function safe for use inside prompt_toolkit.
    """
    @tool
    def acquire_credentials(credential_name: str) -> str:
        """Acquire a missing credential — TUI-safe (no stdin input).

        For OAuth: opens browser, captures token via local callback server.
        For API keys: shows URL, asks user to paste via chat.
        For AWS: reads from ~/.aws/credentials.
        """
        from autopilot.credentials.acquisition import (
            CREDENTIAL_REGISTRY,
            _store_credential,
            _find_free_port,
            _run_oauth_callback_server,
            read_aws_credentials_file,
        )
        import urllib.parse
        import webbrowser

        info = CREDENTIAL_REGISTRY.get(credential_name)

        if info is None:
            append_fn(
                f"\n  Unknown credential: {credential_name}\n"
                f"  Please provide the value in your next message.\n"
            )
            return (
                f"Unknown credential '{credential_name}'. "
                f"Ask the user to provide the value in their next chat message, "
                f"then store it with the agentspan CLI."
            )

        acq_type = info.acquisition_type
        service = info.service

        # -- OAuth (Google / Microsoft) --
        if acq_type in ("oauth_google", "oauth_microsoft"):
            client_id_env = (
                "GOOGLE_CLIENT_ID" if acq_type == "oauth_google" else "MICROSOFT_CLIENT_ID"
            )
            client_secret_env = (
                "GOOGLE_CLIENT_SECRET" if acq_type == "oauth_google" else "MICROSOFT_CLIENT_SECRET"
            )
            client_id = os.environ.get(client_id_env, "")
            client_secret = os.environ.get(client_secret_env, "")

            if not client_id or not client_secret:
                provider = "Google" if acq_type == "oauth_google" else "Microsoft"
                append_fn(
                    f"\n  {service} requires OAuth authorization.\n"
                    f"  Set {client_id_env} and {client_secret_env} environment variables,\n"
                    f"  then retry.\n"
                )
                return (
                    f"OAuth credentials for {service} require {client_id_env} and "
                    f"{client_secret_env} environment variables to be set. "
                    f"Tell the user to set these env vars and try again."
                )

            # Build OAuth URL and open browser
            port = _find_free_port()
            redirect_uri = f"http://localhost:{port}/callback"

            if acq_type == "oauth_google":
                auth_url_base = "https://accounts.google.com/o/oauth2/v2/auth"
                token_url = "https://oauth2.googleapis.com/token"
                params = {
                    "client_id": client_id,
                    "redirect_uri": redirect_uri,
                    "response_type": "code",
                    "scope": " ".join(info.scopes),
                    "access_type": "offline",
                    "prompt": "consent",
                }
            else:
                auth_url_base = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
                token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
                params = {
                    "client_id": client_id,
                    "redirect_uri": redirect_uri,
                    "response_type": "code",
                    "scope": " ".join(info.scopes),
                    "response_mode": "query",
                }

            auth_url = f"{auth_url_base}?{urllib.parse.urlencode(params)}"

            append_fn(
                f"\n  Opening browser for {service} authorization...\n"
                f"  (Complete the sign-in in your browser)\n"
            )

            try:
                webbrowser.open(auth_url)
            except Exception:
                append_fn(f"  Could not open browser. Visit:\n  {auth_url}\n")

            # Wait for callback in a background thread to avoid blocking
            auth_code = _run_oauth_callback_server(port, timeout=120.0)
            if not auth_code:
                append_fn(f"  Authorization timed out or was cancelled.\n")
                return f"Error: OAuth authorization failed or timed out for {credential_name}."

            # Exchange code for token
            try:
                import httpx
                token_data = {
                    "code": auth_code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                }
                resp = httpx.post(token_url, data=token_data, timeout=15.0)
                if resp.status_code != 200:
                    return f"Error: Token exchange failed ({resp.status_code}): {resp.text}"
                tokens = resp.json()
                access_token = tokens.get("access_token", "")
                if not access_token:
                    return f"Error: No access token in response."
                stored = _store_credential(credential_name, access_token)
                if stored:
                    append_fn(f"  \u2713 {service} credential acquired and stored.\n")
                    return f"{credential_name} acquired and stored successfully."
                else:
                    os.environ[credential_name] = access_token
                    append_fn(f"  \u2713 {service} credential acquired (session only).\n")
                    return f"{credential_name} acquired. Set for current session."
            except Exception as exc:
                return f"Error exchanging token: {exc}"

        # -- API key --
        if acq_type == "api_key":
            from autopilot.credentials.acquisition import _API_KEY_URLS
            url = _API_KEY_URLS.get(credential_name, "")
            if url:
                append_fn(
                    f"\n  Opening browser for {service} API key...\n"
                    f"  {url}\n"
                    f"  Paste your API key in the chat below.\n"
                )
                try:
                    webbrowser.open(url)
                except Exception:
                    pass
            else:
                append_fn(
                    f"\n  {info.instructions}\n"
                    f"  Paste your {credential_name} in the chat below.\n"
                )
            return (
                f"Browser opened for {service} API key setup. "
                f"The user should paste the API key in the chat. "
                f"When they do, store it with: agentspan credentials set {credential_name} <value>"
            )

        # -- AWS --
        if acq_type == "aws":
            creds = read_aws_credentials_file()
            if creds:
                access_key = creds.get("aws_access_key_id", "")
                secret_key = creds.get("aws_secret_access_key", "")
                _store_credential("AWS_ACCESS_KEY_ID", access_key)
                _store_credential("AWS_SECRET_ACCESS_KEY", secret_key)
                append_fn(f"  \u2713 AWS credentials read from ~/.aws/credentials\n")
                return (
                    "AWS credentials read from ~/.aws/credentials and stored. "
                    "Both AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are now available."
                )
            append_fn(
                f"\n  No ~/.aws/credentials file found.\n"
                f"  Create AWS access keys in the IAM console and paste them in the chat.\n"
            )
            return (
                "No ~/.aws/credentials file found. "
                "Ask the user to provide AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY via chat."
            )

        # -- Manual --
        append_fn(
            f"\n  {info.instructions}\n"
            f"  Please provide the value for {credential_name} in the chat below.\n"
        )
        return (
            f"Credential '{credential_name}' requires manual input. "
            f"The user should type the value in the chat. "
            f"When they do, store it with: agentspan credentials set {credential_name} <value>"
        )

    return acquire_credentials


# ---------------------------------------------------------------------------
# Orchestrator agent builder
# ---------------------------------------------------------------------------

def build_orchestrator(tui_append_fn=None):
    """Build the Claw orchestrator agent with full orchestrator toolset.

    Args:
        tui_append_fn: Optional callback to append text to TUI output.
            When provided, credential tools use TUI-safe versions that
            don't call input().
    """

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

    # Get orchestrator tools and replace acquire_credentials with TUI-safe version
    orch_tools = get_orchestrator_tools()

    if tui_append_fn is not None:
        tui_safe_acquire = _make_tui_safe_acquire_credentials(tui_append_fn)
        # Replace the original acquire_credentials with the TUI-safe one
        orch_tools = [
            tui_safe_acquire if (hasattr(t, "_tool_def") and t._tool_def.name == "acquire_credentials")
            else t
            for t in orch_tools
        ]

    # Core TUI tools + all orchestrator creation/management/credential tools
    all_tools = [
        receive_message,
        reply_to_user,
        read_agent_config,
    ] + orch_tools

    agent = Agent(
        name="claw_orchestrator",
        model=model,
        tools=all_tools,
        max_turns=100_000,
        stateful=True,
        instructions="""\
You are the Agentspan Claw orchestrator -- an AI assistant that autonomously
creates, deploys, and manages agents on behalf of the user.

Your job is to turn lazy, minimal user prompts into fully functional agents.

## Workflow

When a user asks you to create an agent:

1. Ask 1-2 critical clarifying questions (only when there is no reasonable default).
2. Call expand_prompt() with the user's request and any clarifications.
3. Use the returned template to generate a complete YAML agent specification.
4. Call generate_agent() with the YAML spec to create the agent files.
5. **Validation gates** -- run each gate in order, fix issues before proceeding:
   a. Call validate_spec() -- if FAIL, fix the spec and retry (up to 3 times).
   b. Call validate_code() -- if FAIL, regenerate or fix worker code and retry (up to 3 times).
   c. Call validate_integrations() -- if FAIL, resolve missing integrations/credentials and retry (up to 3 times).
   d. Call validate_deployment() -- if FAIL, fix the issue and retry (up to 3 times).
   If a gate still fails after 3 retries, report the errors to the user and stop.
6. If all gates pass, call deploy_agent() to start the agent.
7. Report back to the user with what was created and deployed.

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
- Use acquire_credentials() to set up a missing credential.

## Principles

- Be proactive: smart-default everything you can.
- Be concise: don't over-explain unless asked.
- Be honest: if something fails, say what went wrong and suggest a fix.
- Never invent credentials -- check what's needed and guide the user to set them up.

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
    _app_exited = threading.Event()
    _done_execution_ids: list[str] = []  # tracks completed executions
    _current_handle = [handle]  # mutable ref so we can restart
    _current_execution_id = [execution_id]

    # ---- Output area (read-only, scrollable) ----
    output_area = TextArea(
        text=render_welcome(execution_id),
        read_only=True,
        scrollbar=True,
        wrap_lines=True,
        focusable=False,
    )

    def _append(text: str) -> None:
        """Append text to the output area — thread-safe."""
        if not text:
            return
        if _app_exited.is_set():
            return
        try:
            output_area.text += text
            output_area.buffer.cursor_position = len(output_area.text)
            if app.is_running:
                app.invalidate()
        except Exception:
            pass  # Safely ignore if app is shutting down

    # ---- Input handler ----

    def _on_input(buff: Buffer) -> None:
        raw = buff.text.strip()
        if not raw:
            return

        cmd = parse_command(raw)

        # Handle exit commands
        if cmd.action in ("quit", "stop"):
            _append("Stopping...\n")
            _stop_requested[0] = True
            try:
                _current_handle[0].stop()
            except Exception:
                pass
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
            try:
                _current_handle[0].cancel()
            except Exception:
                pass
            threading.Timer(0.5, lambda: app.exit() if app.is_running else None).start()
            return

        # Handle informational commands
        if cmd.output:
            _append(cmd.output + "\n")
            return

        # Handle action commands that need server interaction
        if cmd.action == "signal" and cmd.agent_name and cmd.message:
            runtime.signal(_current_execution_id[0], f"[signal:{cmd.agent_name}] {cmd.message}")
            _append(f"  \u2713 Signal sent to {cmd.agent_name}: {cmd.message}\n")
            return

        if cmd.action == "change" and cmd.agent_name and cmd.message:
            _append(f"\n{_THIN_SEP}\nYou: change {cmd.agent_name}: {cmd.message}\n{_THIN_SEP}\n")
            runtime.send_message(_current_execution_id[0], {"text": f"Change agent '{cmd.agent_name}': {cmd.message}"})
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
                agents = _discover_agents(config)
                state_label = agent_state[0].value
                _append(
                    f"\n  Session: {_current_execution_id[0]}\n"
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
            runtime.signal(
                _current_execution_id[0],
                f"[{cmd.action}:{cmd.agent_name}]",
            )
            _append(f"  {cmd.action.title()} signal sent for {cmd.agent_name}.\n")
            return

        # Normal chat message
        if cmd.message:
            _append(f"\n{_THIN_SEP}\nYou: {cmd.message}\n{_THIN_SEP}\n")

            # If the previous execution ended (DONE), start a new one
            if _done_execution_ids and _current_execution_id[0] in _done_execution_ids:
                _append("  Resuming session...\n")
                try:
                    from autopilot.tui.app import build_orchestrator
                    agent = build_orchestrator()
                    new_handle = runtime.start(agent, cmd.message)
                    _current_handle[0] = new_handle
                    _current_execution_id[0] = new_handle.execution_id
                    agent_state[0] = AgentState.BUSY

                    # Start a new stream thread for the new execution
                    def _stream_new():
                        try:
                            for ev in new_handle.stream():
                                if _stop_requested[0]:
                                    return
                                _event_queue.put(ev)
                        except Exception as exc:
                            if not _stop_requested[0]:
                                _event_queue.put(("__error__", str(exc)))

                    threading.Thread(target=_stream_new, daemon=True, name="claw-stream").start()

                    # Restart the consumer if it exited
                    threading.Thread(target=_consume_events, daemon=True, name="claw-consumer").start()
                except Exception as exc:
                    _append(f"  Error restarting session: {exc}\n")
            else:
                if agent_state[0] == AgentState.BUSY:
                    _append("  (queued \u2014 agent is busy)\n")
                runtime.send_message(_current_execution_id[0], {"text": cmd.message})

    input_area = TextArea(
        height=1,
        prompt="You: ",
        multiline=False,
        accept_handler=_on_input,
        focusable=True,
    )

    # ---- Key bindings ----
    kb = KeyBindings()

    @kb.add("c-c")
    def _ctrl_c(event):
        if _stop_requested[0]:
            event.app.exit()
            return
        _stop_requested[0] = True
        _append("\n\nCtrl+C \u2014 stopping (Ctrl+C again to force exit)...\n")
        try:
            _current_handle[0].stop()
        except Exception:
            pass

    @kb.add("pageup")
    def _page_up(event):
        output_area.buffer.cursor_up(count=20)
        app.invalidate()

    @kb.add("pagedown")
    def _page_down(event):
        output_area.buffer.cursor_position = len(output_area.text)
        app.invalidate()

    # ---- Layout ----
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

    # ---- Stream thread (with exception handling) ----
    def _stream_events():
        try:
            for event in handle.stream():
                if _stop_requested[0]:
                    return
                _event_queue.put(event)
        except Exception as exc:
            logger.debug("Stream thread error: %s", exc)
            if not _stop_requested[0]:
                _event_queue.put(("__error__", str(exc)))

    threading.Thread(target=_stream_events, daemon=True, name="claw-stream").start()

    # ---- Event consumer thread (with exception handling) ----
    def _consume_events():
        try:
            while True:
                try:
                    event = _event_queue.get(timeout=1.0)
                except queue.Empty:
                    if _stop_requested[0]:
                        if app.is_running:
                            try:
                                app.exit()
                            except Exception:
                                pass
                        return
                    continue

                # Handle internal error sentinel
                if isinstance(event, tuple) and len(event) == 2 and event[0] == "__error__":
                    _append(f"\n  Connection error: {event[1]}\n")
                    continue

                # Process event type
                if event.type == EventType.WAITING:
                    agent_state[0] = AgentState.WAITING
                    _append(f"{_SEPARATOR}\n")
                elif event.type in (EventType.TOOL_CALL, EventType.THINKING):
                    agent_state[0] = AgentState.BUSY
                elif event.type == EventType.ERROR:
                    agent_state[0] = AgentState.DONE
                    text = format_event(event)
                    _append(text)
                    _append("\nSession ended due to error.\n")
                    if app.is_running:
                        try:
                            app.exit()
                        except Exception:
                            pass
                    return

                elif event.type == EventType.DONE:
                    # For stateful orchestrator agents, DONE means the workflow
                    # completed — likely because the LLM didn't loop back to
                    # wait_for_message. Don't exit the TUI. Show the output
                    # and keep the UI alive for the user to send more messages.
                    text = format_event(event)
                    _append(text)
                    if event.output:
                        out = event.output
                        if isinstance(out, dict):
                            out = out.get("result", str(out))
                        if out and str(out).strip():
                            _append(f"\n{str(out).strip()}\n")

                    agent_state[0] = AgentState.WAITING
                    _append(f"\n{_SEPARATOR}\n")

                    # The stream has ended. We can't receive more events from
                    # this execution. But we keep the TUI alive — when the user
                    # sends the next message, _on_input will start a new execution.
                    _done_execution_ids.append(_current_execution_id[0])
                    return  # Exit consumer — TUI stays alive

                # Format and display the event
                text = format_event(event)
                _append(text)

        except Exception as exc:
            logger.debug("Consumer thread error: %s\n%s", exc, traceback.format_exc())
            _append(f"\n  Internal error in event consumer: {exc}\n")

    threading.Thread(target=_consume_events, daemon=True, name="claw-consumer").start()

    # ---- Background poller (with safe invalidate) ----
    def _safe_invalidate():
        """Only invalidate if the app is still running."""
        if not _app_exited.is_set() and app.is_running:
            try:
                app.invalidate()
            except Exception:
                pass

    poller = DashboardPoller(
        interval_seconds=30,
        on_update=_safe_invalidate,
    )
    poller.start()

    # ---- Run the TUI ----
    print("About to call app.run()...", file=sys.stderr, flush=True)
    try:
        app.run()
        print("app.run() returned normally.", file=sys.stderr, flush=True)
    except Exception as exc:
        print(f"app.run() raised: {exc}", file=sys.stderr, flush=True)
    finally:
        _app_exited.set()
        print("TUI cleanup complete.", file=sys.stderr, flush=True)
        poller.stop()


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

    # Check if we're running in an interactive terminal
    if not sys.stdin.isatty():
        print("Error: Agentspan Claw TUI requires an interactive terminal.")
        print("Run this command directly in your terminal, not from a script or pipe.")
        print()
        print("  uv run python -m autopilot")
        print()
        raise SystemExit(1)

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
        # Build with TUI-safe credential handling
        _deferred_output: list[str] = []

        def _deferred_append(text: str) -> None:
            _deferred_output.append(text)

        agent = build_orchestrator(tui_append_fn=_deferred_append)

    # Ensure session file directory exists
    args.session_file.parent.mkdir(parents=True, exist_ok=True)

    print("Starting Agentspan Claw...")

    try:
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

            print(f"Session: {execution_id[:16]}...")
            print("Launching TUI...", file=sys.stderr, flush=True)
            _run_tui_repl(runtime, handle, execution_id)
            print("TUI exited.", file=sys.stderr, flush=True)
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as exc:
        print(f"\nError: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
