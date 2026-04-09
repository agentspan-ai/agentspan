# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Approval Workflow — agent dynamically decides which tasks need human sign-off.

Demonstrates:
    - wait_for_message_tool as a dynamic approval gate driven by LLM reasoning
    - The agent itself decides mid-loop whether a task is risky, rather than
      the workflow being designed with an explicit approval step upfront
    - flag_for_approval blocks until the operator decides, returning "approve"
      or "reject" directly — no second wait_for_message needed for the decision,
      which prevents the agent from pulling the next task while approval is pending
    - Filesystem-based IPC between the main process and worker processes:
      tool workers run as separate OS processes (different PIDs, same filesystem),
      so @tool functions use sentinel files to communicate with the main thread
    - Clean shutdown: the agent responds with no tool calls on the stop signal,
      which lets the DoWhile loop exit naturally (workflow ends COMPLETED)

How this differs from examples 09a–09d (HITL):
    In 09a–09d the approval pause is a WaitTask node baked into the workflow
    definition at compile time — the workflow always pauses at that point
    regardless of the input.  Here, the LLM inspects each incoming task and
    decides dynamically whether it is safe to execute immediately or requires
    human sign-off.  Low-risk tasks flow through without any pause; only
    high-risk ones trigger the blocking flag_for_approval call.  The workflow
    structure is uniform — it is the agent's reasoning that introduces the
    conditional gate.

Scenario:
    An operations agent processes a stream of system commands.  Safe commands
    (status checks, reads) run immediately.  Destructive or sensitive commands
    (deletes, restarts, permission changes) are held pending approval.  All
    tasks are dispatched upfront; the agent processes them sequentially and
    blocks on flag_for_approval until the operator responds.

Requirements:
    - Conductor server with WMQ support (conductor.workflow-message-queue.enabled=true)
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

import json
import shutil
import tempfile
import time
from pathlib import Path

from agentspan.agents import Agent, AgentRuntime, tool, wait_for_message_tool
from settings import settings

# Shared directory for IPC between main process and worker processes.
# Workers run as separate OS processes (different PIDs, same filesystem).
_ipc_dir = Path(tempfile.mkdtemp(prefix="approval_workflow_"))
_APPROVAL_DIR = _ipc_dir / "approvals"
_DONE_DIR = _ipc_dir / "done"
_APPROVAL_DIR.mkdir()
_DONE_DIR.mkdir()


@tool
def execute_task(task: str) -> str:
    """Execute a safe, pre-approved task immediately."""
    print(f"\n  ✓ EXECUTING: {task}\n")
    (_DONE_DIR / f"{time.time_ns()}.done").touch()
    return f"Completed: {task}"


@tool
def flag_for_approval(task: str, reason: str) -> str:
    """Request operator approval and block until a decision is made.

    Writes a request file and polls for a paired decision file written by the
    main process.  Returns "approve" or "reject" directly so the agent can act
    immediately — no second wait_for_message call needed, which prevents the
    agent from pulling the next queued task while approval is still pending.
    """
    req = _APPROVAL_DIR / f"{time.time_ns()}"
    req.with_suffix(".json").write_text(json.dumps({"task": task, "reason": reason}))
    decision_file = req.with_suffix(".decision")
    while not decision_file.exists():
        time.sleep(0.1)
    decision = decision_file.read_text().strip()
    decision_file.unlink()
    return decision


@tool
def log_rejection(task: str) -> str:
    """Log a task that was rejected by the operator."""
    print(f"\n  ✗ REJECTED: {task}\n")
    (_DONE_DIR / f"{time.time_ns()}.done").touch()
    return f"Rejected: {task}"


receive_message = wait_for_message_tool(
    name="wait_for_message",
    description="Dequeue the next task or stop signal ({stop: true}).",
)

agent = Agent(
    name="approval_agent",
    model=settings.llm_model,
    tools=[receive_message, execute_task, flag_for_approval, log_rejection],
    max_turns=10000,
    stateful=True,
    instructions=(
        "You are an operations agent that processes system commands with a safety gate. "
        "Repeat this cycle indefinitely:\n\n"
        "1. Call wait_for_message to receive the next message.\n"
        "2. If the message contains 'stop: true', respond with 'Stopping.' and call no "
        "   further tools.\n"
        "3. Otherwise assess the task:\n"
        "   - SAFE (status checks, reads, listing): call execute_task immediately.\n"
        "   - RISKY (deletes, restarts, permission changes, writes): call flag_for_approval "
        "     with the task and a brief reason. It will block until the operator decides "
        "     and return 'approve' or 'reject'.\n"
        "4. If flag_for_approval returned 'approve', call execute_task. "
        "   If it returned 'reject', call log_rejection.\n"
        "5. Return to step 1 immediately."
    ),
)


TASKS = [
    "List all running services",
    "Delete all logs older than 7 days",
    "Check disk usage on /var",
    "Restart the payment-service pod",
    "Grant admin access to user@example.com",
]

try:
    with AgentRuntime() as runtime:
        handle = runtime.start(agent, "Start processing the task queue.")
        execution_id = handle.execution_id
        time.sleep(4)
        print(f"Agent started: {execution_id}\n")

        print("Dispatching all tasks...\n")
        for task in TASKS:
            print(f"  → {task!r}")
            runtime.send_message(execution_id, {"task": task})

        # Poll for approval requests; write decision files to unblock the tool.
        # Poll for completions to know when to send the stop signal.
        while len(list(_DONE_DIR.iterdir())) < len(TASKS):
            for req in sorted(_APPROVAL_DIR.glob("*.json")):
                data = json.loads(req.read_text())
                req.unlink()
                print(f"\n  ⚠ APPROVAL REQUIRED")
                print(f"    Task:   {data['task']}")
                print(f"    Reason: {data['reason']}\n")
                answer = input("  Approve? [Y/N]: ").strip().upper()
                decision = "approve" if answer == "Y" else "reject"
                req.with_suffix(".decision").write_text(decision)
            time.sleep(0.1)

        # Agent responds with no tool calls on stop — DoWhile exits as COMPLETED.
        runtime.send_message(execution_id, {"stop": True})
        handle.join(timeout=30)
        print("\nDone.")
finally:
    shutil.rmtree(_ipc_dir, ignore_errors=True)
