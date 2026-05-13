# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""OpenAI Agents SDK migration — streaming.

This is examples/basic/stream_text.py from the openai-agents SDK
with exactly ONE line changed.

Before (runs directly against OpenAI):
    from agents import Runner

After (runs on Agentspan — durable, observable, scalable):
    from agentspan import Runner

The diff:
    -from agents import Runner
    +from agentspan import Runner

Agentspan's streaming model differs from openai-agents in that it streams
*execution events* (LLM calls, tool calls, results) rather than tokens.
The final response arrives in the "done" event's output field.

Event types:
    "thinking"    — an LLM or tool task has started (content = task name)
    "tool_call"   — the LLM called a tool (tool_name, args)
    "tool_result" — a tool completed (tool_name, result)
    "message"     — an intermediate agent message
    "done"        — execution complete; output contains the final answer
    "error"       — execution failed

Requirements:
    - uv add openai-agents
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o

Usage:
    python 96_openai_runner_streaming.py
"""

import asyncio

from agents import Agent

# ── Only this line changes ──────────────────────────────────────────────────
# from agents import Runner          # ← original (runs directly on OpenAI)
from agentspan import Runner         # ← agentspan (runs on Agentspan)
# ───────────────────────────────────────────────────────────────────────────


async def main():
    agent = Agent(
        name="Joker",
        instructions="You are a helpful assistant.",
    )

    stream = await Runner.run_streamed(agent, input="Please tell me 5 jokes.")

    # Iterate Agentspan AgentEvent objects as they arrive from the server.
    # Agentspan streams execution events — the final answer is in the "done" event.
    async for event in stream:
        if event.type == "thinking" and event.content:
            # Show which task is running (LLM or tool name)
            print(f"[{event.content}] thinking...", flush=True)
        elif event.type == "tool_call":
            print(f"\n[tool] {event.tool_name}({event.args})", flush=True)
        elif event.type == "tool_result":
            print(f"[result] {event.result}", flush=True)
        elif event.type == "message" and event.content:
            print(event.content, end="", flush=True)
        elif event.type == "done":
            # Extract the final output from the done event
            output = event.output
            if isinstance(output, dict):
                output = output.get("result", output)
            print(output)
            break

    # Final result is also available after streaming.
    result = await stream.get_result()
    print("\n\nExecution ID:", result.execution_id)


if __name__ == "__main__":
    asyncio.run(main())
