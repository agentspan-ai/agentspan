# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Worker Service Recovery — workflow waits durably while workers are down.

Demonstrates:
    - Deploying an agent separately from running its worker service
    - Starting a workflow by name while no worker service is available
    - Hard-killing and restarting the worker service process group
    - Watching the same workflow complete after the worker service returns

This proves worker-service durability. The workflow remains stored on the
Agentspan/Conductor server while Python tool workers are unavailable, and it
continues when a worker service comes back online.

Requirements:
    - Agentspan server running
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in environment
    - AGENTSPAN_LLM_MODEL set (default: openai/gpt-4o-mini via settings.py)
    - Provider API key configured on the server (for example OPENAI_API_KEY)
"""

import argparse
import json
import os
import signal
import time
from datetime import UTC, datetime
from pathlib import Path

from agentspan.agents import Agent, AgentRuntime, tool
from settings import settings

DEFAULT_WORKFLOW_FILE = Path("/tmp/agentspan_worker_restart.execution_id")
DEFAULT_WORKER_INFO_FILE = Path("/tmp/agentspan_worker_restart.worker.json")
DEFAULT_ATTEMPT_FILE = Path("/tmp/agentspan_worker_restart.attempts.json")


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def save_text(path: Path, value: str) -> None:
    path.write_text(value + "\n", encoding="utf-8")


def load_text(path: Path) -> str:
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"File is empty: {path}")
    return value


def record_attempt(status: str) -> dict:
    data = load_json(DEFAULT_ATTEMPT_FILE, {"attempts": []})
    attempts = data["attempts"]
    if status == "running":
        attempt = {
            "attempt": len(attempts) + 1,
            "status": "running",
            "started_at": now_iso(),
        }
        attempts.append(attempt)
        save_json(DEFAULT_ATTEMPT_FILE, data)
        return attempt

    if not attempts:
        raise RuntimeError("No attempts recorded yet.")

    attempts[-1]["status"] = status
    attempts[-1]["finished_at"] = now_iso()
    save_json(DEFAULT_ATTEMPT_FILE, data)
    return attempts[-1]


@tool(timeout_seconds=60)
def simulate_release_validation(change_id: str) -> dict:
    """Run a release validation step for a production change."""
    attempt = record_attempt("running")
    attempt_number = attempt["attempt"]
    print(f"[worker] starting attempt {attempt_number} for {change_id}", flush=True)
    time.sleep(5)
    record_attempt("completed")
    print(f"[worker] completed attempt {attempt_number} for {change_id}", flush=True)
    return {
        "change_id": change_id,
        "attempt": attempt_number,
        "status": "validated",
    }


agent = Agent(
    name="worker_restart_recovery",
    model=settings.llm_model,
    tools=[simulate_release_validation],
    instructions=(
        "You are a release validation assistant. When asked to validate a change, "
        "you must call simulate_release_validation exactly once before answering."
    ),
)

WORKFLOW_NAME = agent.name


def print_status(prefix: str, status: object) -> None:
    attempt_state = load_json(DEFAULT_ATTEMPT_FILE, {"attempts": []})
    attempts = attempt_state.get("attempts", [])
    attempt_summary = ",".join(f"{item['attempt']}:{item['status']}" for item in attempts) or "none"
    print(f"{prefix} status={status.status} complete={status.is_complete} attempts={attempt_summary}")


def deploy_agent() -> None:
    with AgentRuntime() as runtime:
        results = runtime.deploy(agent)
        for info in results:
            print(f"Deployed: {info.agent_name} -> {info.registered_name}")


def serve_workers(worker_info_file: Path) -> None:
    try:
        os.setsid()
    except OSError:
        pass

    save_json(
        worker_info_file,
        {
            "pid": os.getpid(),
            "pgid": os.getpgid(0),
            "started_at": now_iso(),
            "workflow_name": WORKFLOW_NAME,
        },
    )
    print(f"Worker PID: {os.getpid()}")
    print(f"Worker PGID: {os.getpgid(0)}")
    print(f"Saved worker info to: {worker_info_file}")

    with AgentRuntime() as runtime:
        print("Worker service is running. Use kill-worker to send SIGKILL to this process group.")
        runtime.serve(agent)


def kill_worker(worker_info_file: Path) -> None:
    info = load_json(worker_info_file, {})
    pgid = int(info["pgid"])
    print(f"Sending SIGKILL to worker process group {pgid}")
    os.killpg(pgid, signal.SIGKILL)


def start_workflow(workflow_file: Path, timeout_seconds: int) -> None:
    save_json(DEFAULT_ATTEMPT_FILE, {"attempts": []})

    with AgentRuntime() as runtime:
        handle = runtime.start(WORKFLOW_NAME, "Validate change CHG-901 for production release.")
        save_text(workflow_file, handle.execution_id)

        print(f"Workflow ID: {handle.execution_id}")
        print(f"Saved workflow ID to: {workflow_file}")
        print(f"Attempt state file: {DEFAULT_ATTEMPT_FILE}")
        print("Polling workflow status...")

        for second in range(timeout_seconds + 1):
            status = runtime.get_status(handle.execution_id)
            print_status(f"  [{second:02d}s]", status)
            if status.is_complete:
                print("\nFinal output:")
                print(status.output)
                return
            time.sleep(1)

        print("\nTimed out waiting for completion.")


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Show a workflow survive worker-service outage and finish after restart."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("deploy", help="Deploy the agent definition to the server.")

    serve = sub.add_parser("serve", help="Run the worker service in a long-lived process.")
    serve.add_argument(
        "--worker-info-file",
        type=Path,
        default=DEFAULT_WORKER_INFO_FILE,
        help="Path to store worker PID/PGID info for kill-worker.",
    )

    start = sub.add_parser(
        "start",
        help="Start the workflow by name and poll until completion.",
    )
    start.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_WORKFLOW_FILE,
        help="Path to store execution_id.",
    )
    start.add_argument(
        "--timeout-seconds",
        type=int,
        default=180,
        help="How long to watch before giving up.",
    )

    kill = sub.add_parser("kill-worker", help="SIGKILL the saved worker process group.")
    kill.add_argument(
        "--worker-info-file",
        type=Path,
        default=DEFAULT_WORKER_INFO_FILE,
        help="Path containing worker PID/PGID info.",
    )

    status = sub.add_parser("status", help="Poll workflow status and show attempt history.")
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
        default=60,
        help="How long to poll before stopping.",
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.command == "deploy":
        deploy_agent()
    elif args.command == "serve":
        serve_workers(args.worker_info_file)
    elif args.command == "start":
        start_workflow(args.file, args.timeout_seconds)
    elif args.command == "kill-worker":
        kill_worker(args.worker_info_file)
    elif args.command == "status":
        execution_id = args.execution_id or load_text(args.file)
        show_status(execution_id, args.timeout_seconds)
