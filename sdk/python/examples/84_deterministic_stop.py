# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Deterministic Stop — exit an agent loop without LLM cooperation.

Demonstrates:
    - handle.stop(): graceful, deterministic loop exit via workflow variable
    - No stop-handling instructions needed in the agent's prompt
    - Execution reaches COMPLETED status with last output preserved
    - Works with both blocking and non-blocking WMQ agents

How it works:
    The server compiles every agent's DoWhile loop with a ``_stop_requested``
    workflow variable in its condition.  When ``handle.stop()`` is called, the
    SDK sets this variable to ``true`` via Conductor's ``updateVariables`` API.
    The loop condition evaluates to ``false`` on the next check, and the loop
    exits.  The LLM cannot override this — it's checked by Conductor, not the
    LLM.

    For blocking WMQ agents, ``stop()`` also sends a ``{"_signal": "stop"}``
    WMQ message to unblock the ``PULL_WORKFLOW_MESSAGES`` task so the current
    iteration can finish.

stop() vs cancel():
    - stop()   → graceful, current iteration finishes, status=COMPLETED
    - cancel() → immediate, workflow killed, status=TERMINATED

The old pattern (still works, but non-deterministic):
    Previously, stopping required LLM cooperation — the agent's instructions
    had to include "if you see {stop: true}, respond with no tool calls".
    The LLM could ignore this.  handle.stop() makes this unnecessary.

Requirements:
    - Agentspan server (with _stop_requested support in compiler)
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

import os
import time

os.environ.setdefault("AGENTSPAN_LOG_LEVEL", "WARNING")

from agentspan.agents import Agent, AgentRuntime, tool, wait_for_message_tool
from settings import settings


@tool
def process_task(task: str) -> str:
    """Process a task and return the result."""
    print(f"  [processing] {task}")
    return f"Completed: {task}"


receive = wait_for_message_tool(
    name="wait_for_task",
    description="Wait for the next task to process.",
)

# Note: NO stop-handling instructions!
# No "if stop: true, respond with no tools" — handle.stop() handles it.
agent = Agent(
    name="stoppable_agent",
    model=settings.llm_model,
    tools=[receive, process_task],
    max_turns=10000,
    stateful=True,
    instructions=(
        "You are a task processor. Loop forever: "
        "1. Call wait_for_task to receive the next task. "
        "2. Call process_task with the task. "
        "3. Go back to step 1."
    ),
)

TASKS = [
    "analyze server logs",
    "generate weekly report",
    "send status summary to team",
]

with AgentRuntime() as runtime:
    handle = runtime.start(agent, "Begin processing tasks.")
    print(f"Agent started: {handle.execution_id}")
    print(f"Domain: {handle.run_id}\n")

    # Wait for agent to reach its first wait_for_task call
    time.sleep(3)

    # Send tasks
    for task in TASKS:
        print(f"  → sending: {task!r}")
        runtime.send_message(handle.execution_id, {"task": task})
        time.sleep(6)

    # Deterministic stop — no instructions, no LLM cooperation needed
    print("\nSending stop signal (deterministic)...")
    handle.stop()

    # Wait for the agent to complete gracefully
    result = handle.join(timeout=30)
    print(f"\nStatus: {result.status}")   # COMPLETED (not TERMINATED)
    print(f"Output: {result.output}")
    print("Done.")
