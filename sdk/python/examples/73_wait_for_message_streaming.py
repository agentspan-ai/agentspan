# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Wait for Message (Streaming) — send messages to a running agent and stream its responses.

Demonstrates:
    - wait_for_message_tool with streaming: push messages in and see the agent react
    - Using handle.stream() to observe WAITING → processing → WAITING cycles
    - runtime.send_message() to push payloads into the Workflow Message Queue

The agent starts, immediately waits for a message, processes whatever it
receives, then waits again.  The caller drives the conversation by sending
messages and reading streamed events between each one.

Requirements:
    - Conductor server with WMQ support (conductor.workflow-message-queue.enabled=true)
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

import threading
import time

from agentspan.agents import Agent, AgentRuntime, EventType, wait_for_message_tool, tool
from settings import settings


@tool
def report_result(summary: str) -> str:
    """Report the result of a completed task back to the caller."""
    return f"Reported: {summary}"


receive_message = wait_for_message_tool(
    name="wait_for_message",
    description=(
        "Wait for the next instruction from the caller. "
        "The message payload contains a 'task' field describing what to do."
    ),
)

agent = Agent(
    name="reactive_agent",
    model=settings.llm_model,
    tools=[receive_message, report_result],
    max_turns=10000,
    instructions=(
        "You are a reactive agent. Loop forever: "
        "1. Call wait_for_message to receive your next instruction. "
        "2. Perform the task described in the 'task' field. "
        "3. Call report_result with a one-sentence summary of what you did. "
        "4. Return to step 1."
    ),
)

TASKS = [
    "List three benefits of microservices architecture",
    "Suggest a name for a new AI productivity app",
    "Write a one-line Python function that reverses a string",
]

with AgentRuntime() as runtime:
    handle = runtime.start(agent, "Begin. Wait for your first instruction.")
    print(f"Agent started: {handle.workflow_id}\n")

    # Push messages from a background thread while we stream events on the main thread
    def sender():
        for task in TASKS:
            time.sleep(3)
            print(f"\n  [caller] sending -> {task!r}")
            runtime.send_message(handle.workflow_id, {"task": task})
        # Give the agent time to finish the last task then cancel
        time.sleep(10)
        runtime.cancel(handle.workflow_id, reason="example complete")

    threading.Thread(target=sender, daemon=True).start()

    for event in handle.stream():
        if event.type == EventType.THINKING:
            print(f"  [thinking] {event.content}")

        elif event.type == EventType.TOOL_CALL:
            print(f"  [tool_call] {event.tool_name}({event.args})")

        elif event.type == EventType.TOOL_RESULT:
            print(f"  [tool_result] {event.tool_name} -> {event.result}")

        elif event.type == EventType.WAITING:
            print(f"  [waiting] {event.content}")

        elif event.type == EventType.ERROR:
            print(f"  [error] {event.content}")

        elif event.type == EventType.DONE:
            print(f"\nAgent finished: {event.output}")
            break
