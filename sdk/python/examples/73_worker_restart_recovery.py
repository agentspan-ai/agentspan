# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Worker Restart Recovery — kill the worker service and bring it back.

Demonstrates:
    - Deploying an agent separately from running its worker service
    - Starting a workflow by name against a deployed agent
    - Hard-killing the worker service process group while a tool is running
    - Restarting the worker service and watching the same workflow recover

This proves worker-service durability. The workflow remains durable on the
Agentspan/Conductor server even when the worker process handling tool tasks
dies. The retried task runs again after the worker returns.

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

from conductor.client.automator.task_handler import TaskHandler
from conductor.client.configuration.configuration import Configuration
from conductor.client.http.models.task_def import TaskDef
from conductor.client.worker.worker_task import worker_task

from agentspan.agents import Agent, AgentRuntime
from agentspan.agents.runtime.config import AgentConfig
from settings import settings

DEFAULT_WORKFLOW_FILE = Path("/tmp/agentspan_worker_restart.workflow_id")
DEFAULT_WORKER_INFO_FILE = Path("/tmp/agentspan_worker_restart.worker.json")
DEFAULT_ATTEMPT_FILE = Path("/tmp/agentspan_worker_restart.attempts.json")
TASK_NAME = "simulate_release_validation"


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def update_attempt(path: Path, status: str) -> dict:
    data = load_json(path, {"attempts": []})
    attempts = data["attempts"]

    if status == "running":
        attempt = {
            "attempt": len(attempts) + 1,
            "status": "running",
            "started_at": now_iso(),
        }
        attempts.append(attempt)
        save_json(path, data)
        return attempt

    if not attempts:
        raise RuntimeError("No attempts recorded yet.")

    attempts[-1]["status"] = status
    attempts[-1]["finished_at"] = now_iso()
    save_json(path, data)
    return attempts[-1]


task_def = TaskDef(name=TASK_NAME)
task_def.retry_count = 2
task_def.retry_logic = "LINEAR_BACKOFF"
task_def.retry_delay_seconds = 2
task_def.timeout_seconds = 45
task_def.response_timeout_seconds = 30
task_def.timeout_policy = "RETRY"


@worker_task(
    task_definition_name=TASK_NAME,
    task_def=task_def,
    register_task_def=True,
    overwrite_task_def=True,
)
def simulate_release_validation(change_id: str, attempts_file: str) -> dict:
    """Run a release validation step for a production change."""
    path = Path(attempts_file)
    attempt = update_attempt(path, "running")
    attempt_number = attempt["attempt"]
    print(f"[worker] starting attempt {attempt_number} for {change_id}", flush=True)

    for _ in range(20):
        time.sleep(1)

    update_attempt(path, "completed")
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
        "you must call simulate_release_validation exactly once before answering. "
        "Use the attempts_file argument exactly as provided by the user."
    ),
)

WORKFLOW_NAME = agent.name


def save_workflow_id(path: Path, workflow_id: str) -> None:
    path.write_text(workflow_id + "\n", encoding="utf-8")


def load_workflow_id(path: Path) -> str:
    workflow_id = path.read_text(encoding="utf-8").strip()
    if not workflow_id:
        raise ValueError(f"Workflow file is empty: {path}")
    return workflow_id


def print_status(prefix: str, status: object, attempts_file: Path) -> None:
    attempt_state = load_json(attempts_file, {"attempts": []})
    attempts = attempt_state.get("attempts", [])
    attempt_summary = ",".join(
        f"{item['attempt']}:{item['status']}" for item in attempts
    ) or "none"
    print(
        f"{prefix} status={status.status} complete={status.is_complete} "
        f"attempts={attempt_summary}"
    )


def deploy_agent() -> None:
    with AgentRuntime() as runtime:
        results = runtime.deploy(agent)
        for info in results:
            print(f"Deployed: {info.agent_name} -> {info.workflow_name}")


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
            "task_name": TASK_NAME,
        },
    )
    print(f"Worker PID: {os.getpid()}")
    print(f"Worker PGID: {os.getpgid(0)}")
    print(f"Saved worker info to: {worker_info_file}")

    config = Configuration(server_api_url=AgentConfig.from_env().server_url)
    handler = TaskHandler(
        workers=[],
        configuration=config,
        scan_for_annotated_workers=True,
    )
    handler.start_processes()

    print("Worker service is running. Use kill-worker to send SIGKILL to this process group.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        handler.stop_processes()


def kill_worker(worker_info_file: Path) -> None:
    info = load_json(worker_info_file, {})
    pgid = int(info["pgid"])
    print(f"Sending SIGKILL to worker process group {pgid}")
    os.killpg(pgid, signal.SIGKILL)


def start_workflow(workflow_file: Path, attempts_file: Path, timeout_seconds: int) -> None:
    if not attempts_file.exists():
        save_json(attempts_file, {"attempts": []})

    prompt = (
        "Validate change CHG-901 for production release. "
        f"Use attempts_file={attempts_file} when you call the validation tool."
    )

    with AgentRuntime() as runtime:
        handle = runtime.start(WORKFLOW_NAME, prompt)
        save_workflow_id(workflow_file, handle.workflow_id)

        print(f"Workflow ID: {handle.workflow_id}")
        print(f"Saved workflow ID to: {workflow_file}")
        print(f"Attempt state file: {attempts_file}")
        print("Waiting for the worker to start attempt 1...")

        attempt_prompt_shown = False
        for second in range(timeout_seconds + 1):
            status = runtime.get_status(handle.workflow_id)
            print_status(f"  [{second:02d}s]", status, attempts_file)

            attempts = load_json(attempts_file, {"attempts": []}).get("attempts", [])
            if attempts and not attempt_prompt_shown:
                print()
                print("Attempt 1 is now running.")
                print("Hard-kill the worker service from another terminal with:")
                print(f"  python {Path(__file__).name} kill-worker")
                print("Then restart the worker service with:")
                print(f"  python {Path(__file__).name} serve")
                print()
                attempt_prompt_shown = True

            if status.is_complete:
                print("\nFinal output:")
                print(status.output)
                return

            time.sleep(1)

        print("\nTimed out waiting for completion.")


def show_status(workflow_id: str, attempts_file: Path, timeout_seconds: int) -> None:
    with AgentRuntime() as runtime:
        for second in range(timeout_seconds + 1):
            status = runtime.get_status(workflow_id)
            print_status(f"  [{second:02d}s]", status, attempts_file)
            if status.is_complete:
                print("\nFinal output:")
                print(status.output)
                return
            time.sleep(1)

        print("\nTimed out waiting for completion.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Kill the worker service and show the workflow recover after restart."
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
        help="Start the workflow by name and watch for worker recovery.",
    )
    start.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_WORKFLOW_FILE,
        help="Path to store workflow_id.",
    )
    start.add_argument(
        "--attempts-file",
        type=Path,
        default=DEFAULT_ATTEMPT_FILE,
        help="Path to store attempt history written by the worker.",
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
        help="Path containing saved workflow_id.",
    )
    status.add_argument(
        "--attempts-file",
        type=Path,
        default=DEFAULT_ATTEMPT_FILE,
        help="Path containing attempt history.",
    )
    status.add_argument(
        "--timeout-seconds",
        type=int,
        default=120,
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
        start_workflow(args.file, args.attempts_file, args.timeout_seconds)
    elif args.command == "kill-worker":
        kill_worker(args.worker_info_file)
    elif args.command == "status":
        workflow_id = args.workflow_id or load_workflow_id(args.file)
        show_status(workflow_id, args.attempts_file, args.timeout_seconds)
