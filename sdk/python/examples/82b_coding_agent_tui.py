# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Coding Agent TUI — a filesystem-aware coding assistant with a split-pane terminal UI.

Like 82_coding_agent.py, but with two improvements:

  - Background process tools: run servers and watchers without blocking the agent.
  - prompt_toolkit TUI: scrollable output + always-available input prompt.

Usage:
    python 82b_coding_agent_tui.py                      # new session in current dir
    python 82b_coding_agent_tui.py --cwd /path/to/repo  # new session in a specific dir
    python 82b_coding_agent_tui.py --resume             # resume last session

Requirements:
    - pip install prompt_toolkit
    - Conductor server (conductor.workflow-message-queue.enabled=true)
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - AGENTSPAN_LLM_MODEL=anthropic/claude-sonnet-4-20250514
"""

import argparse
import enum
import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

os.environ.setdefault("AGENTSPAN_LOG_LEVEL", "WARNING")

from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.widgets import TextArea

from agentspan.agents import Agent, AgentRuntime, EventType, tool, wait_for_message_tool
from settings import settings

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SESSION_FILE = Path("/tmp/agentspan_coding_agent_tui.session")
_DEFAULT_SHELL_TIMEOUT = 30
_MAX_FILE_BYTES = 200_000
_MAX_SHELL_OUTPUT = 8_000
_MAX_SHELL_DISPLAY = 2_000
_MAX_BG_BUFFER = 8_000

_SEPARATOR = "─" * 62
_THIN_SEP = "┄" * 62


_HELP_TEXT = """\
Commands:
  <message>            Send a task to the coding agent
  /signal <text>       Inject a persistent signal into agent context mid-task
  /signal              Clear the current signal
  /stop                Gracefully stop the agent (current task finishes)
  /cancel              Immediately terminate the agent
  /disconnect          Exit without stopping — resume later with --resume
  /cwd                 Show the current working directory
  /timeout <secs>      Change shell command timeout (default: 30s)
  /status              Show session ID and current settings
  /help                Show this message
  quit / exit          Gracefully stop and exit

Resume a previous session:
  python 82b_coding_agent_tui.py --resume
"""


# ---------------------------------------------------------------------------
# Agent state tracking
# ---------------------------------------------------------------------------

class AgentState(enum.Enum):
    BUSY = "busy"
    WAITING = "waiting"
    DONE = "done"


# ---------------------------------------------------------------------------
# Background process registry
# ---------------------------------------------------------------------------

@dataclass
class BgProcess:
    id: int
    command: str
    proc: subprocess.Popen
    buffer: list = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    started_at: float = field(default_factory=time.time)
    _read_pos: int = field(default=0, repr=False)


def _start_reader_thread(bg: BgProcess) -> None:
    """Daemon thread that reads stdout/stderr into the buffer."""
    def _read():
        try:
            for line in bg.proc.stdout:
                with bg.lock:
                    bg.buffer.append(line)
                    total = sum(len(ln) for ln in bg.buffer)
                    while total > _MAX_BG_BUFFER and len(bg.buffer) > 1:
                        total -= len(bg.buffer.pop(0))
                        bg._read_pos = max(0, bg._read_pos - 1)
        except Exception:
            pass
    threading.Thread(target=_read, daemon=True).start()


def _make_bg_tools(working_dir: str):
    """Create background process tools that close over a shared registry."""
    _bg_processes: dict[int, BgProcess] = {}
    _next_id = [0]

    @tool
    def run_background(command: str) -> str:
        """Start a long-running process in the background. Returns immediately with a process ID.
        Use for servers, file watchers, builds — anything that won't exit quickly."""
        _next_id[0] += 1
        bg_id = _next_id[0]
        try:
            proc = subprocess.Popen(
                command,
                shell=True,
                cwd=working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except Exception as exc:
            return f"Error starting background process: {exc}"
        bg = BgProcess(id=bg_id, command=command, proc=proc)
        _bg_processes[bg_id] = bg
        _start_reader_thread(bg)
        return f"[bg:{bg_id}] Started: {command} (PID {proc.pid})"

    @tool
    def check_process(id: int) -> str:
        """Get new output from a background process since the last check. Also reports if it is still running."""
        bg = _bg_processes.get(id)
        if bg is None:
            return f"Error: no background process with id {id}."
        with bg.lock:
            new_lines = bg.buffer[bg._read_pos:]
            bg._read_pos = len(bg.buffer)
            new_output = "".join(new_lines)
        status = "running" if bg.proc.poll() is None else f"exited (code {bg.proc.returncode})"
        if new_output.strip():
            return f"[bg:{id}] {status}\n{new_output}"
        return f"[bg:{id}] {status} (no new output)"

    @tool
    def stop_process(id: int) -> str:
        """Terminate a background process. Sends SIGTERM, then SIGKILL after 5 seconds."""
        bg = _bg_processes.get(id)
        if bg is None:
            return f"Error: no background process with id {id}."
        if bg.proc.poll() is not None:
            return f"[bg:{id}] already exited (code {bg.proc.returncode})"
        bg.proc.terminate()
        try:
            bg.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            bg.proc.kill()
            bg.proc.wait(timeout=2)
        with bg.lock:
            final = "".join(bg.buffer[bg._read_pos:])
            bg._read_pos = len(bg.buffer)
        status = f"exited (code {bg.proc.returncode})"
        if final.strip():
            return f"[bg:{id}] stopped — {status}\n{final}"
        return f"[bg:{id}] stopped — {status}"

    @tool
    def list_processes() -> str:
        """List all background processes with their status."""
        if not _bg_processes:
            return "No background processes."
        lines = []
        for bg in _bg_processes.values():
            status = "running" if bg.proc.poll() is None else f"exited ({bg.proc.returncode})"
            cmd_short = bg.command[:60] + ("..." if len(bg.command) > 60 else "")
            lines.append(f"  [bg:{bg.id}] PID {bg.proc.pid}  {status}  {cmd_short}")
        return "\n".join(lines)

    def cleanup_all():
        """Kill all background processes. Called on exit."""
        for bg in _bg_processes.values():
            if bg.proc.poll() is None:
                bg.proc.terminate()
        deadline = time.time() + 5
        for bg in _bg_processes.values():
            remaining = max(0, deadline - time.time())
            try:
                bg.proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                bg.proc.kill()

    return run_background, check_process, stop_process, list_processes, cleanup_all


# ---------------------------------------------------------------------------
# Event formatting
# ---------------------------------------------------------------------------

def _format_event(event) -> str:
    """Format a single stream event as display text. Returns empty string if suppressed."""
    etype = event.type
    args = event.args or {}

    if etype == EventType.TOOL_CALL:
        tool_name = event.tool_name or ""

        if tool_name == "reply_to_user":
            msg = args.get("message", "")
            return f"\n{'─── Agent ' + '─' * 52}\n{msg}\n"

        if tool_name == "wait_for_message":
            return ""

        if tool_name == "run_shell":
            return f"  $ {args.get('command', '')}\n"

        if tool_name == "run_background":
            return f"  $ (bg) {args.get('command', '')}\n"

        if tool_name == "read_file":
            return f"  [read]  {args.get('path', '')}\n"

        if tool_name == "write_file":
            content = args.get("content", "")
            return f"  [write] {args.get('path', '')}  ({len(content):,} bytes)\n"

        if tool_name == "list_dir":
            return f"  [ls]    {args.get('path', '.')}\n"

        if tool_name == "find_files":
            return f"  [find]  {args.get('pattern', '')}  in {args.get('path', '.')}\n"

        if tool_name == "search_in_files":
            return f"  [grep]  {args.get('regex', '')}  in {args.get('path', '.')}\n"

        if tool_name in ("check_process", "stop_process", "list_processes"):
            id_str = f" {args.get('id', '')}" if "id" in args else ""
            return f"  [{tool_name}{id_str}]\n"

        return f"  [{tool_name}] {args}\n"

    if etype == EventType.TOOL_RESULT:
        tool_name = event.tool_name or ""
        if tool_name == "run_shell" and event.result:
            raw = str(event.result)
            output_lines = [ln for ln in raw.splitlines() if not ln.startswith("[exit ")]
            display = "\n".join(output_lines)
            if len(display) > _MAX_SHELL_DISPLAY:
                display = display[:_MAX_SHELL_DISPLAY] + "\n  ... (truncated)"
            if display.strip():
                return "".join(f"  {line}\n" for line in display.splitlines())
        return ""

    if etype == EventType.ERROR:
        return f"\n[ERROR] {event.content}\n"

    return ""


# ---------------------------------------------------------------------------
# TUI REPL
# ---------------------------------------------------------------------------

def _run_tui_repl(
    runtime: AgentRuntime,
    handle,
    execution_id: str,
    working_dir: str,
    shell_timeout: int,
    cleanup_bg,
) -> None:
    """Full-screen TUI: scrollable output on top, persistent input on bottom."""

    agent_state = [AgentState.BUSY]
    _event_queue: "queue.Queue" = queue.Queue()
    _stop_requested = [False]

    # ── Output area (read-only, scrollable) ────────────────────────
    output_area = TextArea(
        text=(
            f"{'=' * 62}\n"
            f"Coding Agent TUI\n"
            f"  Working dir : {working_dir}\n"
            f"  Session ID  : {execution_id}\n"
            f"  Type /help for commands, quit to exit\n"
            f"{'=' * 62}\n\n"
        ),
        read_only=True,
        scrollbar=True,
        wrap_lines=True,
        focusable=False,
    )

    def _append_output(text: str) -> None:
        """Append text to the output area and scroll to the bottom."""
        if not text:
            return
        output_area.text += text
        output_area.buffer.cursor_position = len(output_area.text)
        if app.is_running:
            app.invalidate()

    # ── Input handler ──────────────────────────────────────────────

    def _on_input(buff: Buffer) -> None:
        """Handle submitted input from the input area."""
        raw = buff.text.strip()
        if not raw:
            return

        lower = raw.lower()

        if lower in ("quit", "exit"):
            _append_output("Stopping agent...\n")
            _stop_requested[0] = True
            handle.stop()
            # Delay exit slightly so the stop can propagate
            threading.Timer(1.0, lambda: app.exit() if app.is_running else None).start()
            return

        if lower == "/disconnect":
            _append_output("Disconnected. Resume with: python 82b_coding_agent_tui.py --resume\n")
            _stop_requested[0] = True
            threading.Timer(0.5, lambda: app.exit() if app.is_running else None).start()
            return

        if lower in ("/stop", "stop"):
            _append_output("Stopping agent gracefully...\n")
            _stop_requested[0] = True
            handle.stop()
            threading.Timer(1.0, lambda: app.exit() if app.is_running else None).start()
            return

        if lower == "/cancel":
            _append_output("Cancelling agent...\n")
            _stop_requested[0] = True
            handle.cancel()
            threading.Timer(0.5, lambda: app.exit() if app.is_running else None).start()
            return

        if lower in ("/help", "help"):
            _append_output(_HELP_TEXT + "\n")
            return

        if lower == "/cwd":
            _append_output(f"  {working_dir}\n")
            return

        if lower == "/status":
            state_label = agent_state[0].value
            _append_output(
                f"  execution_id  : {execution_id}\n"
                f"  working_dir   : {working_dir}\n"
                f"  shell_timeout : {shell_timeout}s\n"
                f"  agent_state   : {state_label}\n"
            )
            return

        if lower.startswith("/timeout "):
            try:
                secs = int(raw[9:].strip())
                _append_output(f"  Shell timeout -> {secs}s\n")
            except ValueError:
                _append_output("  Usage: /timeout <seconds>\n")
            return

        if lower.startswith("/signal "):
            msg = raw[8:].strip()
            runtime.signal(execution_id, msg)
            _append_output(f"  Signal injected: {msg!r}\n")
            return

        if lower == "/signal":
            runtime.signal(execution_id, "")
            _append_output("  Signal cleared.\n")
            return

        # ── Normal message ──
        _append_output(f"\n{'┄┄┄ You ' + '┄' * 54}\n{raw}\n{_THIN_SEP}\n")
        if agent_state[0] == AgentState.BUSY:
            _append_output("  (queued — agent is busy, will see this next)\n")
        runtime.send_message(execution_id, {"text": raw})

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
        _append_output(
            "\n\nCtrl+C — stopping agent gracefully "
            "(Ctrl+C again to force exit)...\n"
        )
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
            Window(height=1, char="━"),
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
                # After stop, if no events arrive within 1s, exit the app.
                if _stop_requested[0]:
                    if app.is_running:
                        app.exit()
                    return
                continue

            if event.type == EventType.WAITING:
                agent_state[0] = AgentState.WAITING
                _append_output(f"{_SEPARATOR}\n")
            elif event.type in (EventType.TOOL_CALL, EventType.THINKING):
                agent_state[0] = AgentState.BUSY
            elif event.type in (EventType.DONE, EventType.ERROR):
                agent_state[0] = AgentState.DONE
                text = _format_event(event)
                _append_output(text)
                if event.type == EventType.DONE and event.output:
                    _append_output(f"\n{'─── Agent ' + '─' * 52}\n{event.output}\n")
                _append_output("\nSession ended.\n")
                if app.is_running:
                    app.exit()
                return

            text = _format_event(event)
            _append_output(text)

    threading.Thread(target=_consume_events, daemon=True).start()

    # ── Run the TUI ────────────────────────────────────────────────
    try:
        app.run()
    finally:
        cleanup_bg()


# ---------------------------------------------------------------------------
# Agent builder
# ---------------------------------------------------------------------------

def build_agent(working_dir: str, shell_timeout: int = _DEFAULT_SHELL_TIMEOUT):
    """Build the coding agent and return (agent, cleanup_fn).

    Returns a tuple so the caller can clean up background processes on exit.
    """

    receive_message = wait_for_message_tool(
        name="wait_for_message",
        description="Wait for the next user message. Payload has a 'text' field.",
    )

    # Background process tools (shared registry via closure)
    run_background, check_process, stop_process, list_processes, cleanup_bg = (
        _make_bg_tools(working_dir)
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
        """Run a shell command in the working directory. Returns stdout + stderr with exit code.
        For long-running commands (servers, watchers), use run_background instead."""
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
            return f"Error: command timed out after {shell_timeout}s. Use run_background for long-running commands."
        except Exception as exc:
            return f"Error: {exc}"

    @tool
    def reply_to_user(message: str) -> str:
        """Send your response to the user. Call this when the task is complete."""
        return "ok"

    agent = Agent(
        name="coding_agent_tui",
        model=settings.llm_model,
        tools=[
            receive_message,
            read_file,
            write_file,
            list_dir,
            run_shell,
            run_background,
            find_files,
            search_in_files,
            check_process,
            stop_process,
            list_processes,
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
- run_shell(command)                           run a quick shell command (cwd: {working_dir}, timeout: {shell_timeout}s)
- run_background(command)                      start a long-running process (servers, watchers, builds)
- check_process(id)                            get new output from a background process
- stop_process(id)                             terminate a background process
- list_processes()                             list all background processes
- find_files(pattern, path=".")               find files by glob, e.g. "**/*.py"
- search_in_files(regex, path=".", file_glob) grep files by regex
- reply_to_user(message)                       send your response to the user

Rules:
- Work autonomously. Do not ask for permission before reading files, running commands, or writing.
- Make as many tool calls as needed to fully complete the task before replying.
- Keep replies concise: what was done, what changed, key output. No lengthy explanations.
- If the task is ambiguous, make a reasonable assumption and proceed.
- Use run_shell for commands that complete in seconds (ls, cat, grep, git, etc.).
- Use run_background for servers, file watchers, builds, and any command that won't exit quickly.
- If you see [SIGNALS] ... [/SIGNALS] in a message, those are runtime instructions — follow them.

Repeat indefinitely:
1. Call wait_for_message to receive the next task.
2. Think through the task. Explore, read, search, modify, and run as needed.
3. Complete the task fully.
4. Call reply_to_user with a concise summary.
5. Return to step 1 immediately.
""",
    )

    return agent, cleanup_bg


# ---------------------------------------------------------------------------
# CLI + main
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Coding Agent TUI — coding assistant with split-pane terminal UI.",
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
    agent, cleanup_bg = build_agent(working_dir, shell_timeout=args.timeout)

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

        _run_tui_repl(
            runtime, handle, execution_id, working_dir, args.timeout, cleanup_bg,
        )


if __name__ == "__main__":
    main()
