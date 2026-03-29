# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Agent Lifecycle Callbacks — composable handler classes.

Demonstrates using ``CallbackHandler`` subclasses to hook into agent
and model lifecycle events.  Multiple handlers chain per-position in
list order — each one does a single concern (timing, logging, etc.).

Requirements:
    - Conductor server with callback support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

import time

from agentspan.agents import Agent, AgentRuntime, CallbackHandler, tool
from settings import settings


# ── Handler 1: Timing ────────────────────────────────────────────

class TimingHandler(CallbackHandler):
    """Measures wall-clock time for the full agent run."""

    def on_agent_start(self, **kwargs):
        self.t0 = time.time()
        print("  [timing] Agent started")

    def on_agent_end(self, **kwargs):
        elapsed = time.time() - getattr(self, "t0", time.time())
        print(f"  [timing] Agent finished — {elapsed:.2f}s")


# ── Handler 2: Logging ───────────────────────────────────────────

class LoggingHandler(CallbackHandler):
    """Logs model calls and tool invocations."""

    def on_model_start(self, *, messages=None, **kwargs):
        print(f"  [log] Sending {len(messages or [])} messages to LLM")

    def on_model_end(self, *, llm_result=None, **kwargs):
        snippet = (llm_result or "")[:80]
        print(f"  [log] LLM responded: {snippet!r}")

    def on_tool_start(self, **kwargs):
        print("  [log] Tool executing...")

    def on_tool_end(self, **kwargs):
        print("  [log] Tool finished")


# ── Tool ───────────────────────────────────────────────────────────

@tool
def lookup_weather(city: str) -> dict:
    """Get the current weather for a city.

    Args:
        city: Name of the city.

    Returns:
        Dictionary with weather info.
    """
    return {"city": city, "temperature": "22C", "condition": "sunny"}


# ── Agent with chained handlers ──────────────────────────────────

agent = Agent(
    name="lifecycle_agent_53",
    model=settings.llm_model,
    instructions="You are a helpful assistant. Use lookup_weather for weather queries.",
    tools=[lookup_weather],
    callbacks=[TimingHandler(), LoggingHandler()],
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.53_agent_lifecycle_callbacks
        runtime.deploy(agent)
        runtime.serve(agent)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(agent, "What's the weather like in Tokyo?")
        # result.print_result()

