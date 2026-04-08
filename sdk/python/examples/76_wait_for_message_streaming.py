# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Wait for Message (Streaming) — send messages to a running agent and stream its responses.

Demonstrates:
    - wait_for_message_tool with streaming: push messages in and see the agent react
    - Using handle.stream() to observe WAITING → processing → WAITING cycles
    - runtime.send_message() to push payloads into the Workflow Message Queue

The agent starts, immediately waits for a message, processes whatever it
receives (by calling wait_for_message again), then waits again.  The caller
drives the conversation by sending messages and reading streamed events.

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
def respond(answer: str) -> str:
    """Send your answer back to the caller."""
    return "ok"


receive_message = wait_for_message_tool(
    name="wait_for_message",
    description=(
        "Wait for the next instruction from the caller. "
        "The message payload contains a 'task' field with the request."
    ),
)

agent = Agent(
    name="reactive_agent",
    model=settings.llm_model,
    tools=[receive_message, respond],
    max_turns=10000,
    stateful=True,
    instructions=(
        "You are a reactive agent. Repeat this cycle indefinitely without stopping: "
        "1. Call wait_for_message to receive your next instruction. "
        "2. Think through the task in the 'task' field and formulate a complete answer. "
        "3. Call respond() with your full answer. "
        "4. Go back to step 1 immediately — never stop."
    ),
)

TASKS = [
    "List three benefits of microservices architecture",
    "Suggest a name for a new AI productivity app",
    "Write a one-line Python function that reverses a string",
]

with AgentRuntime() as runtime:
    handle = runtime.start(agent, "Begin. Wait for your first instruction.")
    print(f"Agent started: {handle.execution_id}\n")

    # Push messages from a background thread while we stream events on the main thread
    # Wait long enough between sends for the agent to finish processing each message
    def sender():
        for task in TASKS:
            time.sleep(8)
            print(f"\n  [caller] sending -> {task!r}")
            runtime.send_message(handle.execution_id, {"task": task})
        # Give the agent time to finish the last task then cancel
        time.sleep(15)
        runtime.cancel(handle.execution_id, reason="example complete")

    threading.Thread(target=sender, daemon=True).start()

    for event in handle.stream():
        if event.type == EventType.THINKING:
            print(f"  [thinking] {event.content}")

        elif event.type == EventType.TOOL_CALL and event.tool_name == "respond":
            args = event.args or {}
            print(f"  [answer] {args.get('answer', '')}")

        elif event.type == EventType.WAITING:
            print(f"  [waiting] {event.content}")

        elif event.type == EventType.ERROR:
            print(f"  [error] {event.content}")

        elif event.type == EventType.DONE:
            print(f"\nAgent finished: {event.output}")
            break
