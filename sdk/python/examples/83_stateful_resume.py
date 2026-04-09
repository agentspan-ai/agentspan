# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Stateful Agent Resume — reconnect to a running workflow after runtime restart.

Demonstrates:
    - Starting a stateful agent with WMQ (wait_for_message_tool)
    - Closing the runtime (workers die, workflow persists on server)
    - Resuming with runtime.resume() — domain automatically extracted from
      the server's taskToDomain mapping, no run_id needed
    - Workers re-register under the original domain, workflow continues

How this works:
    Phase 1: Start the agent, send a task, let it process, then close the
    runtime.  Workers die but the workflow is durable on the server — it
    stays in RUNNING state, waiting for a message that has no worker to
    deliver it.

    Phase 2: Create a fresh AgentRuntime and call resume(execution_id, agent).
    resume() fetches the workflow from the server, reads its taskToDomain
    mapping to discover the domain UUID, and re-registers workers under that
    domain.  The server dispatches stalled tasks to the new workers and the
    agent picks up where it left off.

Why stateful matters:
    Without stateful=True, all workers register in the default Conductor
    domain.  Multiple concurrent instances of the same agent would steal
    each other's tasks.  With stateful=True, each execution gets a unique
    domain UUID — workers are isolated per execution.  resume() must
    register workers under the ORIGINAL domain, which it extracts from
    the server automatically.

Requirements:
    - Conductor server with WMQ support (conductor.workflow-message-queue.enabled=true)
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

import time

from agentspan.agents import Agent, AgentRuntime, tool, wait_for_message_tool
from settings import settings

SESSION_FILE = "/tmp/agentspan_stateful_resume.session"


@tool
def execute_task(task: str) -> str:
    """Execute a task and return the result."""
    print(f"\n  ✓ EXECUTING: {task}\n")
    return f"Task completed: {task}"


receive_message = wait_for_message_tool(
    name="wait_for_message",
    description="Wait until a message is sent to this agent, then return its contents.",
)

agent = Agent(
    name="resumable_agent",
    model=settings.llm_model,
    tools=[receive_message, execute_task],
    max_turns=10000,
    stateful=True,
    instructions=(
        "You are a task-execution agent that runs forever in a loop. "
        "Repeat this cycle indefinitely: "
        "1. Call wait_for_message to receive the next message. "
        "2. If the message contains 'stop: true', respond with 'Stopping.' "
        "   and call no further tools. "
        "3. Otherwise extract the 'task' field and call execute_task with it. "
        "4. Go back to step 1 immediately."
    ),
)


# ── Phase 1: Start, interact, close runtime ─────────────────────────────

print("=" * 60)
print("Phase 1: Start agent, send a task, then close runtime")
print("=" * 60)

with AgentRuntime() as runtime:
    handle = runtime.start(agent, "Start listening for messages.")
    execution_id = handle.execution_id
    print(f"\nAgent started: {execution_id}")
    print(f"Domain (run_id): {handle.run_id}")

    # Save execution_id for Phase 2
    with open(SESSION_FILE, "w") as f:
        f.write(execution_id)
    print(f"Saved execution_id to {SESSION_FILE}")

    # Send a task and let the agent process it
    time.sleep(3)
    print("\nSending task: 'summarize quarterly report'")
    runtime.send_message(execution_id, {"task": "summarize quarterly report"})
    time.sleep(8)

print("\nRuntime closed — workers are dead, workflow persists on server.\n")


# ── Phase 2: Resume with a fresh runtime ─────────────────────────────────

print("=" * 60)
print("Phase 2: Resume with a fresh runtime")
print("=" * 60)

# Load the execution_id (in a real scenario, this could be from a database,
# a file, or passed as a CLI argument)
with open(SESSION_FILE) as f:
    saved_execution_id = f.read().strip()

print(f"\nResuming execution: {saved_execution_id}")

with AgentRuntime() as runtime:
    # resume() fetches the workflow from the server, reads taskToDomain,
    # and re-registers workers under the original domain.
    handle = runtime.resume(saved_execution_id, agent)
    print(f"Resumed! Domain (run_id): {handle.run_id}")

    # Send another task — workers are back and polling under the correct domain
    time.sleep(3)
    print("\nSending task: 'check system health'")
    runtime.send_message(saved_execution_id, {"task": "check system health"})
    time.sleep(8)

    # Clean shutdown
    print("\nSending stop signal...")
    runtime.send_message(saved_execution_id, {"stop": True})
    handle.join(timeout=30)
    print("\nDone — same workflow, same domain, seamless resume.")
