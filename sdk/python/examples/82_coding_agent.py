# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Coding Agent REPL — a filesystem-aware coding assistant backed by the Conductor server.

This example is a Claude Code-style assistant you can actually use in a working session.
It runs as a durable Conductor workflow, giving you things a local agent cannot:

  - Sessions survive disconnects — reconnect with --resume and pick up where you left off
  - Every tool call, LLM decision, and token is logged on the server automatically
  - /signal injects context mid-task without restarting the agent
  - Ctrl+C stops gracefully (current task finishes, output preserved)
  - View the full execution graph live at http://localhost:8080

Usage:
    python 82_coding_agent.py                      # new session in current dir
    python 82_coding_agent.py --cwd /path/to/repo  # new session in a specific dir
    python 82_coding_agent.py --resume             # resume last session

Requirements:
    - Conductor server (conductor.workflow-message-queue.enabled=true)
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - AGENTSPAN_LLM_MODEL=anthropic/claude-sonnet-4-20250514
"""

import argparse
import os
import queue
import signal
import subprocess
import threading
from pathlib import Path

os.environ.setdefault("AGENTSPAN_LOG_LEVEL", "WARNING")

from agentspan.agents import Agent, AgentRuntime, EventType, tool, wait_for_message_tool
from settings import settings

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SESSION_FILE = Path("/tmp/agentspan_coding_agent.session")
_DEFAULT_SHELL_TIMEOUT = 30   # seconds per shell command
_MAX_FILE_BYTES = 200_000     # 200 KB — refuse larger files in read_file
_MAX_SHELL_OUTPUT = 8_000     # truncate shell output shown to the LLM
_MAX_SHELL_DISPLAY = 2_000    # truncate shell output shown in the terminal


# ---------------------------------------------------------------------------
# Terminal display
# ---------------------------------------------------------------------------

_HELP_TEXT = """
Commands:
  <message>            Send a task to the coding agent
  /signal <text>       Inject a persistent signal into agent context mid-task
  /signal              Clear the current signal
  /stop                Gracefully stop the agent (current task finishes, COMPLETED)
  /cancel              Immediately terminate the agent (TERMINATED)
  /disconnect          Exit without stopping — resume later with --resume
  /cwd                 Show the current working directory
  /timeout <secs>      Change shell command timeout (default: 30s)
  /status              Show session ID and current settings
  /help                Show this message
  quit / exit          Gracefully stop the agent and exit

Resume a previous session:
  python 82_coding_agent.py --resume

Tip: use /signal to redirect the agent mid-task without interrupting it.
     e.g.  /signal focus on fixing the failing test, skip the refactor
"""


def _display_event(event) -> None:
    """Print a single stream event to the terminal."""
    etype = event.type
    args = event.args or {}

    if etype == EventType.TOOL_CALL:
        tool_name = event.tool_name or ""

        if tool_name == "reply_to_user":
            msg = args.get("message", "")
            print(f"\nAgent: {msg}\n")

        elif tool_name == "wait_for_message":
            pass  # silent — WAITING event handles the prompt

        elif tool_name == "run_shell":
            print(f"  $ {args.get('command', '')}")

        elif tool_name == "read_file":
            print(f"  [read]  {args.get('path', '')}")

        elif tool_name == "write_file":
            content = args.get("content", "")
            print(f"  [write] {args.get('path', '')}  ({len(content):,} bytes)")

        elif tool_name == "list_dir":
            print(f"  [ls]    {args.get('path', '.')}")

        elif tool_name == "find_files":
            print(f"  [find]  {args.get('pattern', '')}  in {args.get('path', '.')}")

        elif tool_name == "search_in_files":
            print(f"  [grep]  {args.get('regex', '')}  in {args.get('path', '.')}")

        else:
            print(f"  [{tool_name}] {args}")

    elif etype == EventType.TOOL_RESULT:
        tool_name = event.tool_name or ""
        # Show shell output inline so the user can follow along.
        if tool_name == "run_shell" and event.result:
            raw = str(event.result)
            # Strip the "[exit N]" line we prepend — show only the command output.
            output_lines = [ln for ln in raw.splitlines() if not ln.startswith("[exit ")]
            display = "\n".join(output_lines)
            if len(display) > _MAX_SHELL_DISPLAY:
                display = display[:_MAX_SHELL_DISPLAY] + "\n  ... (truncated)"
            if display.strip():
                for line in display.splitlines():
                    print(f"  {line}")

    elif etype == EventType.ERROR:
        print(f"\n[ERROR] {event.content}\n")

    # THINKING, HANDOFF, GUARDRAIL_* events are suppressed.


# ---------------------------------------------------------------------------
# REPL loop
# ---------------------------------------------------------------------------


def _run_repl(
    runtime: AgentRuntime,
    handle,
    execution_id: str,
    working_dir: str,
    shell_timeout: int,
) -> None:
    """Stream events → display → wait for WAITING → prompt → send → repeat.

    Uses a single long-lived stream (background thread) to avoid the SSE
    replay-on-reconnect problem: if handle.stream() is called more than once,
    the server replays all buffered events from the beginning (no Last-Event-ID
    on a fresh connection), causing the WAITING event to fire again immediately
    and swallowing all subsequent TOOL_CALL output.

    Pattern: stream thread fills a queue; main thread drains the queue and
    blocks on input() only when WAITING arrives.
    """

    # Mutable settings that REPL commands can change at runtime.
    _shell_timeout = [shell_timeout]
    _event_queue: "queue.Queue" = queue.Queue()

    print(f"\n{'=' * 62}")
    print("Coding Agent REPL")
    print(f"  Working dir : {working_dir}")
    print(f"  Session ID  : {execution_id}")
    print(f"  Type /help for commands, 'quit' to stop and exit")
    print(f"{'=' * 62}\n")

    # ── Stream thread: one connection, runs until DONE/ERROR ─────────
    def _stream_events() -> None:
        for event in handle.stream():
            _event_queue.put(event)

    threading.Thread(target=_stream_events, daemon=True).start()

    # ── Main thread: process events; block on input() at WAITING ─────
    while True:
        event = _event_queue.get()

        if event.type == EventType.WAITING:
            # Agent is blocked on wait_for_message — prompt user in a
            # tight inner loop so commands that don't send a message
            # (e.g. /help, /cwd) re-prompt without waiting for more events.
            while True:
                try:
                    raw = input("You: ").strip()
                except EOFError:
                    print()
                    return
                except KeyboardInterrupt:
                    print()
                    continue

                if not raw:
                    continue

                lower = raw.lower()

                if lower in ("quit", "exit"):
                    print("Stopping agent...")
                    handle.stop()
                    handle.join(timeout=30)
                    return

                if lower == "/disconnect":
                    print("Disconnected. Resume with: python 82_coding_agent.py --resume")
                    return

                if lower in ("/stop", "stop"):
                    print("Stopping agent gracefully...")
                    handle.stop()
                    handle.join(timeout=30)
                    return

                if lower == "/cancel":
                    print("Cancelling agent immediately...")
                    handle.cancel()
                    return

                if lower in ("/help", "help"):
                    print(_HELP_TEXT)
                    continue

                if lower == "/cwd":
                    print(f"  {working_dir}")
                    continue

                if lower == "/status":
                    print(f"  execution_id  : {execution_id}")
                    print(f"  working_dir   : {working_dir}")
                    print(f"  shell_timeout : {_shell_timeout[0]}s")
                    continue

                if lower.startswith("/timeout "):
                    try:
                        secs = int(raw[9:].strip())
                        _shell_timeout[0] = secs
                        print(f"  Shell timeout → {secs}s")
                    except ValueError:
                        print("  Usage: /timeout <seconds>")
                    continue

                if lower.startswith("/signal "):
                    msg = raw[8:].strip()
                    runtime.signal(execution_id, msg)
                    print(f"  Signal injected: {msg!r}")
                    continue

                if lower == "/signal":
                    runtime.signal(execution_id, "")
                    print("  Signal cleared.")
                    continue

                # Normal message → send and break inner loop.
                runtime.send_message(execution_id, {"text": raw})
                break

        elif event.type == EventType.DONE:
            output = event.output
            if output:
                print(f"\nAgent: {output}\n")
            print("Session ended.")
            return

        else:
            _display_event(event)


# ---------------------------------------------------------------------------
# Agent builder
# ---------------------------------------------------------------------------

def build_agent(working_dir: str, shell_timeout: int = _DEFAULT_SHELL_TIMEOUT) -> Agent:
    """Build the coding agent. All tools close over working_dir and shell_timeout."""

    receive_message = wait_for_message_tool(
        name="wait_for_message",
        description="Wait for the next user message. Payload has a 'text' field.",
    )

    @tool
    def read_file(path: str) -> str:
        """Read a file and return its text contents. Paths may be absolute or relative to the working directory."""
        target = Path(path) if os.path.isabs(path) else Path(working_dir) / path
        if not target.exists():
            return f"Error: {path!r} does not exist."
        if target.is_dir():
            return f"Error: {path!r} is a directory. Use list_dir to browse it."
        size = target.stat().st_size
        if size > _MAX_FILE_BYTES:
            return (
                f"Error: {path!r} is {size:,} bytes (limit {_MAX_FILE_BYTES:,}). "
                "Use search_in_files to find specific content instead."
            )
        try:
            return target.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return f"Error reading {path!r}: {exc}"

    @tool
    def write_file(path: str, content: str) -> str:
        """Write content to a file, creating parent directories as needed. Overwrites existing files."""
        target = Path(path) if os.path.isabs(path) else Path(working_dir) / path
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return f"Wrote {len(content):,} bytes to {str(target)!r}."
        except Exception as exc:
            return f"Error writing {path!r}: {exc}"

    @tool
    def list_dir(path: str = ".") -> str:
        """List directory contents with file sizes. Paths may be absolute or relative to the working directory."""
        target = Path(path) if os.path.isabs(path) else Path(working_dir) / path
        if not target.exists():
            return f"Error: {path!r} does not exist."
        if not target.is_dir():
            return f"Error: {path!r} is not a directory."
        try:
            entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name))
            lines = []
            for entry in entries:
                if entry.is_dir():
                    lines.append(f"  {entry.name}/")
                else:
                    lines.append(f"  {entry.name}  ({entry.stat().st_size:,} bytes)")
            header = str(target) + "/"
            return header + "\n" + "\n".join(lines) if lines else header + " (empty)"
        except Exception as exc:
            return f"Error listing {path!r}: {exc}"

    @tool
    def find_files(pattern: str, path: str = ".") -> str:
        """Find files matching a glob pattern (e.g. '**/*.py'). Path relative to working directory."""
        base = Path(path) if os.path.isabs(path) else Path(working_dir) / path
        if not base.exists():
            return f"Error: {path!r} does not exist."
        if not base.is_dir():
            return f"Error: {path!r} is not a directory."
        try:
            matches = sorted(m for m in base.glob(pattern) if m.is_file())
            if not matches:
                return f"No files matching {pattern!r} under {str(base)!r}."
            lines = []
            for m in matches[:200]:
                try:
                    rel = m.relative_to(working_dir)
                except ValueError:
                    rel = m
                lines.append(str(rel))
            suffix = f"\n... ({len(matches) - 200} more)" if len(matches) > 200 else ""
            return "\n".join(lines) + suffix
        except Exception as exc:
            return f"Error finding files: {exc}"

    @tool
    def search_in_files(regex: str, path: str = ".", file_glob: str = "**/*") -> str:
        """Search for a regex pattern in file contents. Returns file:line: matching_line entries."""
        import re as _re
        base = Path(path) if os.path.isabs(path) else Path(working_dir) / path
        try:
            compiled = _re.compile(regex)
        except _re.error as exc:
            return f"Invalid regex {regex!r}: {exc}"
        results = []
        for filepath in sorted(base.glob(file_glob)):
            if not filepath.is_file() or filepath.stat().st_size > _MAX_FILE_BYTES:
                continue
            try:
                for lineno, line in enumerate(
                    filepath.read_text(encoding="utf-8", errors="replace").splitlines(), 1
                ):
                    if compiled.search(line):
                        try:
                            label = str(filepath.relative_to(working_dir))
                        except ValueError:
                            label = str(filepath)
                        results.append(f"{label}:{lineno}: {line.rstrip()}")
                        if len(results) >= 100:
                            break
            except Exception:
                continue
            if len(results) >= 100:
                break
        if not results:
            return f"No matches for {regex!r} in {str(base)!r} ({file_glob})."
        suffix = "\n... (truncated at 100 matches)" if len(results) >= 100 else ""
        return "\n".join(results) + suffix

    @tool
    def run_shell(command: str) -> str:
        """Run a shell command in the working directory. Returns stdout + stderr with exit code."""
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=shell_timeout,
            )
            combined = (proc.stdout + proc.stderr).strip()
            if len(combined) > _MAX_SHELL_OUTPUT:
                combined = combined[:_MAX_SHELL_OUTPUT] + f"\n... (truncated, {len(combined):,} chars total)"
            return f"[exit {proc.returncode}]\n{combined}" if combined else f"[exit {proc.returncode}] (no output)"
        except subprocess.TimeoutExpired:
            return f"Error: command timed out after {shell_timeout}s."
        except Exception as exc:
            return f"Error: {exc}"

    @tool
    def reply_to_user(message: str) -> str:
        """Send your response to the user. Call this when the task is complete."""
        return "ok"

    return Agent(
        name="coding_agent",
        model=settings.llm_model,
        tools=[
            receive_message,
            read_file,
            write_file,
            list_dir,
            run_shell,
            find_files,
            search_in_files,
            reply_to_user,
        ],
        max_turns=100_000,
        stateful=True,
        instructions=f"""You are a coding assistant with direct filesystem and shell access.
Working directory: {working_dir}

Available tools:
- read_file(path)                              read any text file
- write_file(path, content)                    create or overwrite a file
- list_dir(path=".")                           list directory contents
- run_shell(command)                           run a shell command (cwd: {working_dir}, timeout: {shell_timeout}s)
- find_files(pattern, path=".")               find files by glob, e.g. "**/*.py"
- search_in_files(regex, path=".", file_glob) grep files by regex
- reply_to_user(message)                       send your response to the user

Rules:
- Work autonomously. Do not ask for permission before reading files, running commands, or writing.
- Make as many tool calls as needed to fully complete the task before replying.
- Keep replies concise: what was done, what changed, key output. No lengthy explanations.
- If the task is ambiguous, make a reasonable assumption and proceed.
- If you see [SIGNALS] ... [/SIGNALS] in a message, those are runtime instructions — follow them.

Repeat indefinitely:
1. Call wait_for_message to receive the next task.
2. Think through the task. Explore, read, search, modify, and run as needed.
3. Complete the task fully.
4. Call reply_to_user with a concise summary.
5. Return to step 1 immediately.
""",
    )


# ---------------------------------------------------------------------------
# CLI + main
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Coding Agent REPL — coding assistant on Conductor.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume the last session from the session file.",
    )
    parser.add_argument(
        "--session-file",
        type=Path,
        default=SESSION_FILE,
        metavar="PATH",
        help=f"Session file path (default: {SESSION_FILE}).",
    )
    parser.add_argument(
        "--cwd",
        type=str,
        default=None,
        metavar="DIR",
        help="Working directory for the agent (default: current directory).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=_DEFAULT_SHELL_TIMEOUT,
        metavar="SECS",
        help=f"Shell command timeout in seconds (default: {_DEFAULT_SHELL_TIMEOUT}).",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    working_dir = os.path.abspath(args.cwd or os.getcwd())
    agent = build_agent(working_dir, shell_timeout=args.timeout)

    # Track whether a graceful stop has been requested so a second Ctrl+C
    # force-exits without waiting.
    _stop_pending = [False]

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
                f"Begin. Working directory: {working_dir}. Wait for the user's first task.",
            )
            execution_id = handle.execution_id
            args.session_file.write_text(execution_id)
            print(f"Session saved to {args.session_file}")

        def _sigint(sig, frame):
            if _stop_pending[0]:
                print("\nForce exit.")
                raise SystemExit(1)
            _stop_pending[0] = True
            print(
                "\n\nCtrl+C received — stopping agent gracefully "
                "(Ctrl+C again to force exit)..."
            )
            handle.stop()

        signal.signal(signal.SIGINT, _sigint)

        _run_repl(runtime, handle, execution_id, working_dir, args.timeout)


if __name__ == "__main__":
    main()
