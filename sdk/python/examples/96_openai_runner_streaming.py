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

Note: Agentspan's stream_async() returns an AsyncAgentStream that yields
AgentEvent objects. Event types: "thinking", "tool_call", "tool_result",
"message", "done", "error". Use event.type and event.content.

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
    async for event in stream:
        if event.type in ("thinking", "message") and event.content:
            print(event.content, end="", flush=True)
        elif event.type == "done":
            break

    # Final result is also available after streaming.
    result = await stream.get_result()
    print("\n\nExecution ID:", result.execution_id)


if __name__ == "__main__":
    asyncio.run(main())
