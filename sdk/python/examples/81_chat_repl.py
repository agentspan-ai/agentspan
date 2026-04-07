# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Chat REPL — interactive conversation with a long-running agent via WMQ.

This example turns a running agent into a conversational REPL.  Every message
you type is sent into the agent's Workflow Message Queue via
runtime.send_message(); the agent dequeues it, thinks, and pushes a reply back
via a tool call.  The session stays alive across as many turns as you want —
the agent is a persistent running workflow, not a one-shot call.

Key WMQ concept — bidirectional conversation loop:
    The agent uses wait_for_message_tool to receive user input and reply_to_user
    (a @tool backed by filesystem IPC) to send responses back.  There is no
    streaming, no polling for SSE events — the main thread simply blocks on a
    sentinel file written by the reply_to_user worker, reads the reply, and
    prompts again.  Workers run as separate OS processes so the reply is
    communicated via the shared filesystem rather than an in-process queue.

Ephemeral tools via /tool <name>:
    Conductor compiles tool definitions into a workflow at startup — you cannot
    add new Conductor task types mid-execution.  However, a single generic
    run_task(name, input) tool backed by a file-based registry lets the operator
    activate predefined text-processing tasks at runtime.  The agent is notified
    via a WMQ message and can start using the new capability immediately.

    Built-in tasks (activate with /tool <name>):
        word_count   — count words in input
        char_count   — count characters in input
        reverse      — reverse the input string
        to_upper     — convert input to UPPER CASE
        to_lower     — convert input to lower case
        title_case   — Title Case the input
        contains     — check if input contains a word (format: "word|text")
        bullet_split — split input into one bullet point per sentence

Requirements:
    - Conductor server with WMQ support (conductor.workflow-message-queue.enabled=true)
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=anthropic/claude-sonnet-4-20250514 as environment variable
"""

import json
import shutil
import tempfile
import time
from pathlib import Path

from settings import settings

from agentspan.agents import Agent, AgentRuntime, tool, wait_for_message_tool

# ---------------------------------------------------------------------------
# Ephemeral task registry — predefined implementations keyed by task name.
# Workers are separate OS processes; the registry is serialised to a JSON file
# so both the REPL process (writer) and worker process (reader) share state.
# ---------------------------------------------------------------------------

_TASK_IMPLEMENTATIONS: dict = {
    "word_count":   ("Count the number of words in the input text.",
                     lambda inp: str(len(inp.split()))),
    "char_count":   ("Count the number of characters in the input text.",
                     lambda inp: str(len(inp))),
    "reverse":      ("Reverse the input string character by character.",
                     lambda inp: inp[::-1]),
    "to_upper":     ("Convert the input text to UPPER CASE.",
                     lambda inp: inp.upper()),
    "to_lower":     ("Convert the input text to lower case.",
                     lambda inp: inp.lower()),
    "title_case":   ("Convert the input text to Title Case.",
                     lambda inp: inp.title()),
    "contains":     ('Check whether the input text contains a word. '
                     'Pass input as "word|text to search" (pipe-separated).',
                     lambda inp: str(inp.split("|", 1)[1].__contains__(inp.split("|", 1)[0])
                                    if "|" in inp else "Error: use 'word|text' format")),
    "bullet_split": ("Split the input text into a bullet list, one sentence per bullet.",
                     lambda inp: "\n".join(
                         f"• {s.strip()}" for s in inp.replace("!", ".").replace("?", ".").split(".")
                         if s.strip()
                     )),
}


# ---------------------------------------------------------------------------
# Filesystem IPC setup
# ---------------------------------------------------------------------------

_ipc_dir = Path(tempfile.mkdtemp(prefix="chat_repl_"))
_REPLY_FILE = _ipc_dir / "reply.txt"       # agent writes reply here
_REPLY_READY = _ipc_dir / "reply.ready"    # sentinel: reply is ready to read
_REGISTRY_FILE = _ipc_dir / "registry.json"  # active ephemeral tasks


def _write_registry(active: dict) -> None:
    """Write the active task registry (name → description) to the shared file."""
    _REGISTRY_FILE.write_text(json.dumps(active))


def _read_registry() -> dict:
    """Read the active task registry from the shared file."""
    if not _REGISTRY_FILE.exists():
        return {}
    return json.loads(_REGISTRY_FILE.read_text())


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

def build_agent() -> Agent:
    receive_message = wait_for_message_tool(
        name="wait_for_message",
        description=(
            "Wait for the next user message or a control signal. "
            "User messages have a 'text' field. "
            "Stop signal: {stop: true}. "
            "New-tool notification: {tool_registered: name, tool_description: desc}."
        ),
    )

    @tool
    def reply_to_user(message: str) -> str:
        """Send a reply back to the user in the REPL.

        Writes the reply to a shared file and touches a sentinel so the main
        thread knows a new reply is ready to display.
        """
        _REPLY_FILE.write_text(message)
        _REPLY_READY.touch()
        return "reply sent"

    @tool
    def run_task(task_name: str, task_input: str) -> str:
        """Run a registered ephemeral task by name.

        Reads the active task registry at call time — newly registered tasks
        are available immediately.  Returns the task output or an error if the
        task name is not registered.
        """
        registry = _read_registry()
        if task_name not in registry:
            available = ", ".join(registry) or "(none)"
            return f"Error: task '{task_name}' not found. Available: {available}"
        impl_fn = _TASK_IMPLEMENTATIONS.get(task_name)
        if impl_fn is None:
            return f"Error: task '{task_name}' has no implementation."
        _, fn = impl_fn
        try:
            return fn(task_input)
        except Exception as exc:
            return f"Error running '{task_name}': {exc}"

    return Agent(
        name="chat_repl_agent",
        model=settings.llm_model,
        tools=[receive_message, reply_to_user, run_task],
        max_turns=10000,
        stateful=True,
        instructions=(
            "You are a helpful conversational assistant in an interactive REPL. "
            "Repeat indefinitely:\n\n"
            "1. Call wait_for_message to receive the next event.\n"
            "2. If the message contains 'stop: true', respond with 'Goodbye!' "
            "   and call no further tools.\n"
            "3. If the message contains 'tool_registered', acknowledge the new "
            "   capability in your reply: say what the tool does and that you can "
            "   now use it. Call reply_to_user with your acknowledgment.\n"
            "4. Otherwise, respond naturally to the user's 'text' field. "
            "   If a registered ephemeral task (via run_task) would help answer "
            "   the user's question, call it first and incorporate the result. "
            "   Always call reply_to_user with your final response.\n"
            "5. Return to step 1 immediately."
        ),
    )


# ---------------------------------------------------------------------------
# REPL main loop
# ---------------------------------------------------------------------------

HELP_TEXT = """
Commands:
  <message>           Send a message to the agent
  /tool <name>        Activate an ephemeral task tool (see list below)
  /tools              List available ephemeral tasks
  quit / exit         End the session

Available ephemeral tasks:
""" + "\n".join(f"  {name:12s}  {desc}" for name, (desc, _) in _TASK_IMPLEMENTATIONS.items())


def _wait_for_reply() -> str:
    """Block until the agent writes a reply, then read and return it."""
    while not _REPLY_READY.exists():
        time.sleep(0.05)
    reply = _REPLY_FILE.read_text()
    _REPLY_READY.unlink()
    return reply


try:
    active_tasks: dict[str, str] = {}
    _write_registry(active_tasks)

    with AgentRuntime() as runtime:
        handle = runtime.start(build_agent(), "Begin. Wait for the user's first message.")
        execution_id = handle.execution_id
        print(f"Agent started: {execution_id}")
        time.sleep(4)

        print("\n" + "=" * 60)
        print("Chat REPL — type 'help' for commands, 'quit' to exit")
        print("=" * 60 + "\n")

        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if not user_input:
                continue

            if user_input.lower() in ("quit", "exit"):
                runtime.send_message(execution_id, {"stop": True})
                reply = _wait_for_reply()
                print(f"Agent: {reply}\n")
                break

            if user_input.lower() == "help":
                print(HELP_TEXT)
                continue

            if user_input.lower() == "/tools":
                if active_tasks:
                    print("Active ephemeral tasks:")
                    for name, desc in active_tasks.items():
                        print(f"  {name:12s}  {desc}")
                else:
                    print("No ephemeral tasks activated yet. Use /tool <name>.")
                print()
                continue

            if user_input.lower().startswith("/tool "):
                task_name = user_input[6:].strip()
                if task_name not in _TASK_IMPLEMENTATIONS:
                    print(f"Unknown task '{task_name}'. "
                          f"Available: {', '.join(_TASK_IMPLEMENTATIONS)}\n")
                    continue
                desc, _ = _TASK_IMPLEMENTATIONS[task_name]
                active_tasks[task_name] = desc
                _write_registry(active_tasks)
                print(f"  → Registered ephemeral task '{task_name}'.\n")
                # Notify the agent so it can acknowledge and use it in the next turn.
                runtime.send_message(execution_id, {
                    "tool_registered": task_name,
                    "tool_description": desc,
                })
                reply = _wait_for_reply()
                print(f"Agent: {reply}\n")
                continue

            # Normal user message.
            runtime.send_message(execution_id, {"text": user_input})
            reply = _wait_for_reply()
            print(f"Agent: {reply}\n")

        print("Session ended.")
finally:
    shutil.rmtree(_ipc_dir, ignore_errors=True)
