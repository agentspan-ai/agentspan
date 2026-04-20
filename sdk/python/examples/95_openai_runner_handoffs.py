# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""OpenAI Agents SDK migration — multi-agent handoffs.

This is examples/agent_patterns/routing.py from the openai-agents SDK
with exactly ONE line changed.

Before (runs directly against OpenAI):
    from agents import Runner

After (runs on Agentspan — durable, observable, scalable):
    from agentspan import Runner

The diff:
    -from agents import Runner
    +from agentspan import Runner

Agent definitions, handoffs list, and the Runner.run() call are unchanged.
Agentspan records every handoff decision in the execution history — you can
replay the full agent-to-agent routing in the Agentspan UI.

Requirements:
    - uv add openai-agents          (from sdk/python/)
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o

Usage (from sdk/python/):
    uv run python examples/95_openai_runner_handoffs.py
"""

import asyncio

try:
    from agents import Agent
except ImportError:
    raise SystemExit(
        "openai-agents not installed.\n"
        "Install it with (from sdk/python/): uv add openai-agents\n"
        "Then run: uv run python examples/95_openai_runner_handoffs.py"
    )

# ── Only this line changes ──────────────────────────────────────────────────
# from agents import Runner          # ← original (runs directly on OpenAI)
from agentspan import Runner         # ← agentspan (runs on Agentspan)
# ───────────────────────────────────────────────────────────────────────────

french_agent = Agent(
    name="french_agent",
    instructions="You only speak French.",
)

spanish_agent = Agent(
    name="spanish_agent",
    instructions="You only speak Spanish.",
)

english_agent = Agent(
    name="english_agent",
    instructions="You only speak English.",
)

triage_agent = Agent(
    name="triage_agent",
    instructions="Handoff to the appropriate agent based on the language of the request.",
    handoffs=[french_agent, spanish_agent, english_agent],
)


async def main():
    result = await Runner.run(
        triage_agent,
        input="Hello, how do I say good evening in French?",
    )
    print(result.final_output)
    # Bonsoir !


if __name__ == "__main__":
    asyncio.run(main())
