# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Streaming — real-time events.

Demonstrates streaming agent execution events. The runtime.stream() method
yields events as the agent executes, allowing real-time monitoring.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

from agentspan.agents import Agent, AgentRuntime
from settings import settings

agent = Agent(
    name="haiku_writer",
    model=settings.llm_model,
    instructions="You are a haiku poet. Write a single haiku.",
)

print("Streaming agent execution:")
print("-" * 40)

with AgentRuntime() as runtime:
    for event in runtime.stream(agent, "Write a haiku about Python programming"):
        if event.type == "done":
            print(f"\nResult: {event.output}")
            print(f"Workflow: {event.workflow_id}")
        elif event.type == "waiting":
            print("[Waiting...]")
        elif event.type == "error":
            print(f"[Error: {event.content}]")
