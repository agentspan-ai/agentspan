# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Wait for Message — continuously receive messages via Workflow Message Queue.

Demonstrates:
    - wait_for_message_tool: dequeues messages from the WMQ (Conductor PULL_WORKFLOW_MESSAGES task)
    - Mixing a server-side message tool with a local Python action tool
    - Looping agent that keeps processing messages indefinitely
    - Pushing messages from outside the workflow with runtime.send_message()

The agent loops forever: each iteration waits for a message, reads the
"task" field, executes it, and goes back to listening.

Requirements:
    - Conductor server with WMQ support (conductor.workflow-message-queue.enabled=true)
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

import time

from agentspan.agents import Agent, AgentRuntime, wait_for_message_tool, tool
from settings import settings


@tool
def execute_task(task: str) -> str:
    """Execute a task and return the result."""
    print(f"\n*** EXECUTING: {task} ***\n")
    # Simulate task execution
    return f"Task completed: {task}"


# Server-side tool — dequeues the next message from the WMQ (no worker needed)
receive_message = wait_for_message_tool(
    name="wait_for_message",
    description="Wait until a message is sent to this agent, then return its contents.",
)

agent = Agent(
    name="message_listener",
    model=settings.llm_model,
    tools=[receive_message, execute_task],
    max_turns=10000,
    stateful=True,
    instructions=(
        "You are a task-execution agent that runs forever in a loop. "
        "Repeat this cycle indefinitely: "
        "1. Call wait_for_message to receive the next message. "
        "2. Extract the 'task' field from the message payload. "
        "3. Call execute_task with that task string. "
        "4. Go back to step 1 immediately — never stop."
    ),
)

with AgentRuntime() as runtime:
    handle = runtime.start(agent, "Start listening for messages.")
    print(f"Agent started: {handle.execution_id}")
    print("Sending messages...\n")

    for msg in ["summarize quarterly report", "draft release notes", "check system health"]:
        time.sleep(2)
        print(f"  -> sending: {msg!r}")
        runtime.send_message(handle.execution_id, {"task": msg})

    # Let the agent process all messages before exiting (~5-6s per message)
    time.sleep(30)
    runtime.cancel(handle.execution_id)
    print("\nDone.")
