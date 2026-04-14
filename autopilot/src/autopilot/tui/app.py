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
from autopilot.orchestrator.tools import build_integration_catalog, get_orchestrator_tools
from autopilot.tui.commands import CommandResult, HELP_TEXT, parse_command
from autopilot.tui.dashboard import render_dashboard
from autopilot.tui.events import format_event, render_welcome
from autopilot.tui.notifications import Notification, NotificationManager
from autopilot.tui.poller import DashboardPoller
from autopilot.tui.sessions import SessionManager

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
    """Read agent directories from disk and enrich with live server status."""
    agents_dir = config.agents_dir
    if not agents_dir.exists():
        return []

    # Fetch live server status for enrichment
    server_running: dict[str, dict] = {}
    try:
        from autopilot.orchestrator.server import get_running_agents
        for ex in get_running_agents(config=config):
            aname = ex.get("agentName", "")
            if aname:
                server_running[aname] = ex
    except Exception:
        pass  # Server unreachable — use local data only

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

        # Enrich with live server status
        if d.name in server_running:
            info["status"] = "running"
            ex = server_running[d.name]
            if ex.get("startTime"):
                info["last_run"] = ex["startTime"]

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
    integration_catalog = build_integration_catalog()

    receive_message = wait_for_message_tool(
        name="wait_for_message",
        description="Wait for the next user message. Payload has a 'text' field.",
    )

    @tool
    def reply_to_user(message: str) -> str:
        """Send your response to the user. Call this ONLY when ALL work is complete."""
        _FUTURE = ["i'll ", "i will ", "going to ", "let me investigate",
                    "need to investigate", "will get back", "will investigate",
                    "let me look into", "i'm going to", "will try to"]
        if any(p in message.lower() for p in _FUTURE):
            return (
                "WARNING: Your reply uses future tense. Complete all work BEFORE replying. "
                "Fix errors NOW or report what happened in past tense. "
                "Rewrite your reply without future promises and call reply_to_user again."
            )
        return "ok"

    @tool
    def read_agent_config(agent_name: str) -> str:
        """Read an agent's configuration (agent.yaml and expanded_prompt.md)."""
        config = AutopilotConfig.from_env()
        agent_dir = config.agents_dir / agent_name
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

    # Orchestrator has ONLY agent management tools — no web_search, no local_fs.
    # If the user wants to search, the orchestrator creates a search agent.
    # This forces agent creation for EVERY request.
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
        # NOTE: stateful=False to avoid domain-scoped workers.
        # With stateful=True, each runtime.start() creates a new domain
        # but the WorkerManager doesn't restart workers for the new domain
        # (it sees the same tool names and skips). This causes tools like
        # generate_agent to sit in SCHEDULED state with pollCount=0.
        stateful=False,
        instructions=f"""\
You are the Agentspan Claw orchestrator. You create agents for EVERY user request.

## CRITICAL RULES

1. ANY ACTION must be done by an agent. You do NOT have tools to act directly.
   You can ONLY create agents that act. Even "search for X" → create a search agent.
2. You CAN ask 1-2 clarifying questions if the request is genuinely ambiguous.
   But once you understand what the user wants, CREATE AN AGENT. Don't discuss — build.
3. After EVERY reply_to_user, call wait_for_message. ALWAYS.
4. NEVER use future tense ("I'll", "going to", "will"). Report what you DID.
5. Be concise. Show results, not explanations.

## Check for existing agents FIRST

Before creating a new agent, check if a matching agent already exists:
- Call list_agents() to see what's available
- If the user's request matches an existing agent (by name or purpose),
  call deploy_agent(existing_name) to run it instead of creating a new one
- Only create a new agent if no existing agent fits the request

## Agent Creation -- for EVERY action

For ANY user request that requires action:

### Step 1: Determine what the agent needs
Think about:
- What the agent should do (step by step)
- Does a builtin integration cover this? (web_search for web queries, local_fs for files, etc.)
- If NO builtin integration fits the task, you MUST create a custom worker

### Step 2: If a builtin integration fits → use it
Write a YAML spec with `tools: [builtin:<name>]`

### Step 3: If NO builtin fits → create a custom worker
Call generate_worker with REAL Python implementation code and dependencies.
The worker must contain actual executable Python — NOT pseudocode or placeholders.

Example: for "generate a QR code":
  generate_worker(
    agent_name="qr_gen",
    tool_name="create_qr_code",
    description="Generate a QR code image from a URL or text",
    parameters="data: str, output_path: str = '/tmp/qrcode.png'",
    implementation="import qrcode\\nimg = qrcode.make(data)\\nimg.save(output_path)\\nreturn f'QR code saved to {{output_path}}'",
    dependencies="qrcode,pillow"
  )

IMPORTANT:
- implementation: REAL Python code, not a skeleton. Include imports inside the function if needed.
- dependencies: comma-separated pip packages the code needs. These get installed automatically.
- The worker runs in its own process — all imports must be self-contained.
- Use try/except for error handling in the implementation.
- Always return a string result.

Then include the worker name in the agent's tools list (NOT as builtin:).

### Step 4: Write the YAML spec
   name: <snake_case_descriptive_name>
   version: 1
   model: {model}
   instructions: |
     <Detailed instructions. At least 10 lines. MUST include these resilience rules:
     - If a tool returns an error, try a different approach. Do NOT give up.
     - If a search returns no results, try different search terms.
     - If a page can't be fetched, try a different URL from the search results.
     - If tools fail after retrying, clearly state what you tried and what didn't work. Be honest.
     - If all tools fail, explain what went wrong. Do NOT make up results.
     - Clearly distinguish between results from tools (real data) and your own knowledge (may be outdated).
     - Always return a complete, useful response. Partial results are better than no results.>
   trigger:
     type: <cron or daemon>
     schedule: "<cron expression>"  # only for type: cron
   tools:
     - builtin:<integration_name>  # for builtin integrations
     - <worker_name>  # for custom workers (no builtin: prefix)
   credentials:
     - <EXACT_CREDENTIAL_NAME>
   error_handling:
     max_retries: 3
     backoff: exponential
     on_failure: pause_and_notify

### Step 5: Create, validate, deploy, auto-fix
3. Call generate_agent(spec_yaml=<YAML>, agent_name=<name>)
4. Call validate_spec(agent_name=<name>)
5. If the agent has custom workers, call validate_code(agent_name=<name>)
6. Call validate_integrations(agent_name=<name>)
7. Call validate_deployment(agent_name=<name>)
8. Call deploy_agent(agent_name=<name>) to run the agent
9. CHECK the deploy result:
   - If it contains "Error" or "failed": FIX IT. Read the error, fix the worker
     or agent config, and call deploy_agent AGAIN. Do NOT report errors to the user.
     The user is not technical. Fix it yourself. Retry up to 3 times.
   - If it succeeded: extract the agent output from the result.
10. Call reply_to_user with the agent's output VERBATIM. Do NOT summarize.
    Prefix with: "Agent <name> (Execution ID: <id>):\n\n" then the full output.
11. Call wait_for_message

## Available integrations

{integration_catalog}

CRITICAL RULES for specs:
1. model MUST be "{model}" -- do not change it
2. tools entries MUST use format "builtin:name" with NO SPACE after the colon
3. credentials MUST use the EXACT names listed above for each integration
4. instructions MUST be detailed (at least 10 lines) -- not a one-liner

## When the user asks about output or status
Call get_agent_status(agent_name) and show the result. No preamble.

## Smart defaults -- use these, don't ask

- Model: use the configured model ({model})
- Schedule: if user says "every 15 mins" -> cron "*/15 * * * *". If unclear -> daemon
- Integrations: pick the most obvious ones from the request
- Notifications: default to replying in chat
- Error handling: 3 retries, exponential backoff, pause on failure
- Names: generate a clear snake_case name from the request

## Agent Management

- list_agents() -- show all agents
- get_agent_status(name) -- detailed status
- signal_agent(name, message) -- one-time instruction
- update_agent(name, changes) -- get current config + change instructions (step 1)
- save_agent_config(name, updated_yaml) -- persist changes to disk (step 2)
- pause_agent/resume_agent -- control execution
- archive_agent -- deactivate
- check_credentials/acquire_credentials -- handle auth

## Interaction Loop -- MANDATORY

1. Call wait_for_message
2. Process the request (call tools as needed)
3. Call reply_to_user with the result
4. GOTO 1 -- you MUST call wait_for_message again. Do NOT stop.
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
    agent=None,
    session_manager: SessionManager | None = None,
) -> str:
    """Full-screen TUI: scrollable output on top, persistent input on bottom.

    Returns:
        ``"new_session"`` if the user typed ``/new`` (caller should restart
        with a fresh ``runtime.start``), or ``""`` for any other exit.
    """

    config = AutopilotConfig.from_env()
    notif_manager = NotificationManager(config)

    agent_state = [AgentState.BUSY]
    _event_queue: queue.Queue = queue.Queue()
    _stop_requested = [False]
    _app_exited = threading.Event()
    _needs_restart = [False]  # True when workflow completes, next message auto-restarts
    _new_session_requested = [False]  # True when user types /new
    _current_handle = [handle]  # mutable ref so we can restart
    _current_execution_id = [execution_id]
    _active_threads: list[threading.Thread] = []  # track spawned threads
    # F4: Use threading.Event per stream lifecycle instead of a boolean flag
    _current_stop_event = threading.Event()
    _current_stop_event_ref = [_current_stop_event]  # mutable ref for swapping

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
            if session_manager:
                session_manager.mark_disconnected(_current_execution_id[0])
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

        if cmd.action == "list_sessions":
            if session_manager:
                sessions = session_manager.list_sessions()
                if not sessions:
                    _append("\n  No sessions.\n")
                else:
                    current = session_manager.get_current()
                    _append(f"\n  {'ID':<40} {'Status':<14} {'Last Active'}\n")
                    _append(f"  {'----':<40} {'------':<14} {'-----------'}\n")
                    for s in sessions:
                        marker = " *" if s.execution_id == current else ""
                        short_id = s.execution_id[:36]
                        last = s.last_active[:19] if s.last_active else ""
                        _append(
                            f"  {short_id:<40} {s.status:<14} {last}{marker}\n"
                        )
                    _append("")
            else:
                _append("\n  Session manager not available.\n")
            return

        if cmd.action == "switch_session":
            if session_manager and cmd.message:
                try:
                    target = session_manager.find_by_id(cmd.message)
                except ValueError as ve:
                    _append(f"\n  {ve}\n")
                    return
                if not target:
                    _append(f"\n  Session '{cmd.message}' not found.\n")
                    return
                try:
                    # Signal old stream to stop
                    _current_stop_event.set()
                    for t in _active_threads:
                        if t.is_alive():
                            t.join(timeout=1.0)
                    _active_threads.clear()

                    new_handle = runtime.resume(target.execution_id, agent)
                    _current_handle[0] = new_handle
                    _current_execution_id[0] = target.execution_id
                    session_manager.set_current(target.execution_id)
                    session_manager.update_last_active(target.execution_id)
                    agent_state[0] = AgentState.BUSY

                    # Remove from done list if it was there
                    if target.execution_id in _done_execution_ids:
                        _done_execution_ids.remove(target.execution_id)

                    # F4: New stop event for this stream lifecycle
                    stop_ev = threading.Event()
                    _current_stop_event_ref[0] = stop_ev

                    def _stream_switched():
                        try:
                            for ev in new_handle.stream():
                                if _stop_requested[0] or stop_ev.is_set():
                                    return
                                _event_queue.put(ev)
                        except Exception as exc:
                            if not _stop_requested[0]:
                                _event_queue.put(("__error__", str(exc)))

                    t_stream = threading.Thread(
                        target=_stream_switched, daemon=True, name="claw-stream",
                    )
                    t_consumer = threading.Thread(
                        target=_consume_events, daemon=True, name="claw-consumer",
                    )
                    _active_threads.extend([t_stream, t_consumer])
                    t_stream.start()
                    t_consumer.start()
                    # F10: Visual separator on /switch
                    new_eid = target.execution_id
                    _append(
                        f"\n{'=' * 62}\n"
                        f"  Switched to session {new_eid[:16]}...\n"
                        f"{'=' * 62}\n\n"
                    )
                except Exception as exc:
                    _append(f"\n  Could not switch: {exc}\n")
            else:
                _append("\n  Session manager not available.\n")
            return

        if cmd.action == "new_session":
            _new_session_requested[0] = True
            if session_manager:
                session_manager.mark_disconnected(_current_execution_id[0])
            _stop_requested[0] = True
            try:
                _current_handle[0].stop()
            except Exception:
                pass
            threading.Timer(0.3, lambda: app.exit() if app.is_running else None).start()
            return

        # Normal chat message
        if cmd.message:
            _append(f"\n{_THIN_SEP}\nYou: {cmd.message}\n{_THIN_SEP}\n")

            # If the previous execution ended (DONE), transparently start a new one
            # with conversation history for context continuity
            if _needs_restart[0]:
                _needs_restart[0] = False
                _append("  Working...\n")
                try:
                    # Carry conversation history so the orchestrator has context
                    history_text = output_area.text
                    # Take the last 3000 chars as context (keeps it manageable)
                    if len(history_text) > 3000:
                        history_text = history_text[-3000:]
                    context_prompt = (
                        "CONVERSATION CONTEXT (previous exchanges in this session — "
                        "use this to understand what the user is referring to, "
                        "do NOT repeat or reference this context directly):\n"
                        f"---\n{history_text}\n---\n\n"
                        f"User's new message: {cmd.message}"
                    )
                    new_handle = runtime.start(agent, context_prompt)
                    _current_handle[0] = new_handle
                    _current_execution_id[0] = new_handle.execution_id
                    agent_state[0] = AgentState.BUSY

                    # Start new stream + consumer threads
                    stop_ev = threading.Event()

                    def _stream_restarted():
                        try:
                            for ev in new_handle.stream():
                                if _stop_requested[0] or stop_ev.is_set():
                                    return
                                _event_queue.put(ev)
                        except Exception as exc:
                            if not _stop_requested[0]:
                                _event_queue.put(("__error__", str(exc)))

                    threading.Thread(target=_stream_restarted, daemon=True, name="claw-stream").start()
                    threading.Thread(target=_consume_events, daemon=True, name="claw-consumer").start()
                except Exception as exc:
                    _append(f"  Error: {exc}\n")
            elif agent_state[0] == AgentState.BUSY:
                _append("  (queued \u2014 agent is busy)\n")
                runtime.send_message(_current_execution_id[0], {"text": cmd.message})
            else:
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
    _initial_stop_ev = _current_stop_event_ref[0]

    def _stream_events():
        try:
            for event in handle.stream():
                if _stop_requested[0] or _initial_stop_ev.is_set():
                    return
                _event_queue.put(event)
        except Exception as exc:
            logger.debug("Stream thread error: %s", exc)
            if not _stop_requested[0]:
                _event_queue.put(("__error__", str(exc)))

    _t_initial_stream = threading.Thread(target=_stream_events, daemon=True, name="claw-stream")
    _active_threads.append(_t_initial_stream)
    _t_initial_stream.start()

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
                    _append(f"\n{_SEPARATOR}\n  Ready for your next request.\n{_SEPARATOR}\n")
                elif event.type in (EventType.TOOL_CALL, EventType.THINKING):
                    if agent_state[0] == AgentState.WAITING:
                        # Transition from waiting → busy: show activity indicator
                        _append("  Working...\n")
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
                    # The workflow completed — the LLM didn't call
                    # wait_for_message. Show any output, then silently
                    # mark as ready for next message. The session NEVER
                    # ends unless the user types /end or /stop.
                    text = format_event(event)
                    _append(text)
                    if event.output:
                        out = event.output
                        if isinstance(out, dict):
                            out = out.get("result", str(out))
                        if out and str(out).strip():
                            _append(f"\n{str(out).strip()}\n")

                    # Mark as needing restart on next message, but
                    # DON'T show "Session ended" — just show ready prompt
                    agent_state[0] = AgentState.WAITING
                    _needs_restart[0] = True
                    _append(f"\n{_SEPARATOR}\n  Ready for your next request.\n{_SEPARATOR}\n")
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
        interval_seconds=config.poll_interval_seconds,
        on_update=_safe_invalidate,
    )
    poller.start()

    # ---- Run the TUI ----
    try:
        app.run()
    finally:
        _app_exited.set()
        poller.stop()

    return "new_session" if _new_session_requested[0] else ""


# ---------------------------------------------------------------------------
# CLI + main
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Agentspan Claw TUI \u2014 manage autonomous agents.",
    )
    parser.add_argument(
        "--resume", nargs="?", const=True, default=None,
        help="Resume the most recent session, or a specific session by ID.",
    )
    parser.add_argument(
        "--new", action="store_true",
        help="Force start a new session (don't resume existing).",
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

    config = AutopilotConfig.from_env()
    sm = SessionManager(config.autopilot_dir / "sessions.json")
    # F8: Clean up old completed sessions on startup
    sm.cleanup()

    print("Starting Agentspan Claw...")

    _start_prompt = "Begin. You are the Agentspan Claw orchestrator. Wait for the user's first message."

    try:
        with AgentRuntime() as runtime:
            handle = None
            execution_id = None

            if args.new:
                # Force new session
                handle = runtime.start(agent, _start_prompt)
                execution_id = handle.execution_id
                sm.create(execution_id)
                # Also write legacy session file for backward compat
                args.session_file.parent.mkdir(parents=True, exist_ok=True)
                args.session_file.write_text(execution_id)

            elif args.resume is not None:
                # --resume (no value) or --resume <id>
                if args.resume is True:
                    # Resume most recent session
                    session = sm.get_most_recent()
                    if session is None:
                        # Fall back to legacy session file
                        if args.session_file.exists():
                            saved_eid = args.session_file.read_text().strip()
                            session_eid = saved_eid
                        else:
                            print("No sessions found. Start a new session (without --resume).")
                            raise SystemExit(1)
                    else:
                        session_eid = session.execution_id
                else:
                    # --resume <specific-id>
                    found = sm.find_by_id(args.resume)
                    if found:
                        session_eid = found.execution_id
                    else:
                        # Try as a raw execution ID
                        session_eid = args.resume

                print(f"Resuming session: {session_eid}")
                handle = runtime.resume(session_eid, agent)
                execution_id = handle.execution_id
                sm.update_last_active(execution_id)

            else:
                # Always start a new session. User can switch to existing
                # sessions with /switch or /sessions if needed.
                handle = runtime.start(agent, _start_prompt)
                execution_id = handle.execution_id
                sm.create(execution_id)
                args.session_file.parent.mkdir(parents=True, exist_ok=True)
                args.session_file.write_text(execution_id)

            # Loop: run the TUI; if user types /new, start a fresh session
            while True:
                print(f"Session: {execution_id[:16]}...")
                result = _run_tui_repl(
                    runtime, handle, execution_id, agent=agent, session_manager=sm,
                )
                if result != "new_session":
                    break
                # /new requested — start a fresh execution at the top level
                # where AgentRuntime has full control over worker registration
                print("Starting new session...")
                handle = runtime.start(agent, _start_prompt)
                execution_id = handle.execution_id
                sm.create(execution_id)
                args.session_file.parent.mkdir(parents=True, exist_ok=True)
                args.session_file.write_text(execution_id)

    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as exc:
        print(f"\nError: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
