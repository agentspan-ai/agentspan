# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Client Reconnect — hard-kill the SDK process and resume later.

Demonstrates:
    - Starting a workflow and saving its execution_id
    - Reaching a durable approval wait state on the server
    - Hard-killing the local client process with SIGKILL from another process
    - Re-registering the tool worker from a fresh process
    - Reconnecting later by execution_id and continuing the same workflow

This proves client-process durability. The local Python process can die, but
the workflow state remains stored on the Agentspan/Conductor server.

Requirements:
    - Agentspan server running
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
    - AGENTSPAN_LLM_MODEL set (default: openai/gpt-4o-mini via settings.py)
    - Provider API key configured on the server (for example OPENAI_API_KEY)
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import time
from pathlib import Path

from agentspan.agents import Agent, AgentRuntime, tool
from settings import settings

DEFAULT_WORKFLOW_FILE = Path("/tmp/agentspan_client_reconnect.execution_id")
DEFAULT_CLIENT_INFO_FILE = Path("/tmp/agentspan_client_reconnect.client.json")


@tool(approval_required=True)
def approve_release(change_id: str) -> dict:
    """Approve a production release change after human review."""
    return {"change_id": change_id, "approved": True}

agent = Agent(
    name="client_reconnect_demo",
    model=settings.llm_model,
    tools=[approve_release],
    instructions=(
        "You are a careful release coordinator. When asked whether to ship a change, "
        "you must call approve_release first. After approval, explain that the "
        "release is approved and ready to ship."
    ),
)


def save_text(path: Path, value: str) -> None:
    path.write_text(value + "\n", encoding="utf-8")


def load_text(path: Path) -> str:
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"File is empty: {path}")
    return value


def save_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def print_status(prefix: str, status: object) -> None:
    print(
        f"{prefix} status={status.status} "
        f"waiting={status.is_waiting} complete={status.is_complete}"
    )


def run_once(prompt: str) -> None:
    with AgentRuntime() as runtime:
        result = runtime.run(agent, prompt)
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.72_client_reconnect
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)
        #
        # Advanced reconnect demo:
        # python 72_client_reconnect.py start
        # python 72_client_reconnect.py kill-client
        # python 72_client_reconnect.py resume --approve


def start_workflow(prompt: str, workflow_file: Path, client_info_file: Path, timeout_seconds: int) -> None:
    try:
        os.setsid()
    except OSError:
        pass

    with AgentRuntime() as runtime:
        save_json(
            client_info_file,
            {"pid": os.getpid(), "pgid": os.getpgid(0)},
        )
        handle = runtime.start(agent, prompt)
        save_text(workflow_file, handle.execution_id)

        print(f"Client PID: {os.getpid()}")
        print(f"Client PGID: {os.getpgid(0)}")
        print(f"Workflow ID: {handle.execution_id}")
        print(f"Saved workflow ID to: {workflow_file}")
        print(f"Saved client info to: {client_info_file}")
        print("Waiting for the workflow to reach a durable WAITING state...")

        for second in range(timeout_seconds + 1):
            status = runtime.get_status(handle.execution_id)
            print_status(f"  [{second:02d}s]", status)
            if status.is_waiting:
                print()
                print("Workflow is durably paused on the server.")
                print("Now hard-kill this client from another terminal with:")
                print(f"  python {Path(__file__).name} kill-client --client-info-file {client_info_file}")
                print()
                break
            if status.is_complete:
                print("\nWorkflow completed before it paused.")
                print(status.output)
                return
            time.sleep(1)
        else:
            print("\nTimed out waiting for WAITING state.")
            return

        while True:
            status = runtime.get_status(handle.execution_id)
            print_status("  [hold]", status)
            time.sleep(2)


def kill_client(client_info_file: Path) -> None:
    info = load_json(client_info_file)
    pgid = int(info["pgid"])
    print(f"Sending SIGKILL to client process group {pgid}")
    os.killpg(pgid, signal.SIGKILL)


def show_status(execution_id: str, timeout_seconds: int) -> None:
    with AgentRuntime() as runtime:
        for second in range(timeout_seconds + 1):
            status = runtime.get_status(execution_id)
            print_status(f"  [{second:02d}s]", status)
            if status.is_complete:
                print("\nFinal output:")
                print(status.output)
                return
            time.sleep(1)

        print("\nTimed out waiting for completion.")


def resume_workflow(execution_id: str, timeout_seconds: int, approve: bool) -> None:
    with AgentRuntime() as runtime:
        runtime.serve(agent, blocking=False)
        print(f"Reconnected to workflow: {execution_id}")
        status = runtime.get_status(execution_id)
        print_status("  [initial]", status)

        if status.is_waiting and approve:
            print("Sending approval from this new process...")
            runtime.respond(execution_id, {"approved": True})
        elif status.is_waiting:
            print("Workflow is waiting. Re-run with --approve to continue it.")
            return

        show_status(execution_id, timeout_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Hard-kill the client process and reconnect to the same workflow later."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser(
        "start",
        help="Start the workflow, wait for WAITING, then hold so another process can SIGKILL it.",
    )
    start.add_argument(
        "--prompt",
        default="Ship change CHG-204: rotate the production API gateway certificates.",
        help="Prompt to send to the agent.",
    )
    start.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_WORKFLOW_FILE,
        help="Path to store execution_id.",
    )
    start.add_argument(
        "--client-info-file",
        type=Path,
        default=DEFAULT_CLIENT_INFO_FILE,
        help="Path to store the client PID/PGID info for kill-client.",
    )
    start.add_argument(
        "--timeout-seconds",
        type=int,
        default=90,
        help="How long to wait for WAITING before giving up.",
    )

    kill = sub.add_parser(
        "kill-client",
        help="Send SIGKILL to the saved client PID.",
    )
    kill.add_argument(
        "--client-info-file",
        type=Path,
        default=DEFAULT_CLIENT_INFO_FILE,
        help="Path containing the client PID/PGID info.",
    )

    status = sub.add_parser(
        "status",
        help="Query workflow status by execution_id or saved file.",
    )
    status.add_argument("--workflow-id", default="", help="Workflow ID (overrides --file).")
    status.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_WORKFLOW_FILE,
        help="Path containing saved execution_id.",
    )
    status.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        help="How long to poll before stopping.",
    )

    resume = sub.add_parser(
        "resume",
        help="Reconnect to the saved workflow and optionally approve it.",
    )
    resume.add_argument("--workflow-id", default="", help="Workflow ID (overrides --file).")
    resume.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_WORKFLOW_FILE,
        help="Path containing saved execution_id.",
    )
    resume.add_argument(
        "--approve",
        action="store_true",
        help="Send approval to the waiting HUMAN task before polling.",
    )
    resume.add_argument(
        "--timeout-seconds",
        type=int,
        default=90,
        help="How long to poll before giving up.",
    )

    return parser.parse_args()


if __name__ == "__main__":
    if len(sys.argv) == 1:
        run_once(
            "Ship change CHG-204: rotate the production API gateway certificates."
        )
    else:
        args = parse_args()

        if args.command == "start":
            start_workflow(args.prompt, args.file, args.client_info_file, args.timeout_seconds)
        elif args.command == "kill-client":
            kill_client(args.client_info_file)
        elif args.command == "status":
            execution_id = args.execution_id or load_text(args.file)
            show_status(execution_id, args.timeout_seconds)
        elif args.command == "resume":
            execution_id = args.execution_id or load_text(args.file)
            resume_workflow(execution_id, args.timeout_seconds, args.approve)
