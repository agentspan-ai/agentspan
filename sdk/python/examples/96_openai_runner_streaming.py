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

Note on streaming: Agentspan streams execution events rather than tokens.
The event types are:
    "thinking"    — an LLM or tool task started (content = task name)
    "tool_call"   — the LLM called a tool
    "tool_result" — a tool completed
    "done"        — execution complete; output contains the final answer
    "error"       — execution failed

The final answer always arrives in the "done" event's output field.

Requirements:
    - uv add openai-agents          (from sdk/python/)
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o

Usage (from sdk/python/):
    uv run python examples/96_openai_runner_streaming.py
"""

import asyncio

try:
    from agents import Agent
except ImportError:
    raise SystemExit(
        "openai-agents not installed.\n"
        "Install it with (from sdk/python/): uv add openai-agents\n"
        "Then run: uv run python examples/96_openai_runner_streaming.py"
    )

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

    async for event in stream:
        if event.type == "tool_call":
            print(f"\n[tool] {event.tool_name}({event.args})", flush=True)
        elif event.type == "tool_result":
            print(f"[result] {event.result}", flush=True)
        elif event.type == "done":
            output = event.output
            if isinstance(output, dict):
                output = output.get("result", output)
            print(output)
            break

    result = await stream.get_result()
    print("\nExecution ID:", result.execution_id)


if __name__ == "__main__":
    asyncio.run(main())
