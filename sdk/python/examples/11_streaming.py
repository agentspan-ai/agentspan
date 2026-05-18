# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Streaming — real-time events.

Demonstrates streaming agent execution events. The runtime.stream() method
yields events as the agent executes, allowing real-time monitoring.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import Agent, AgentRuntime
from settings import settings

agent = Agent(
    name="haiku_writer",
    model=settings.llm_model,
    instructions="You are a haiku poet. Write a single haiku.",
)

if __name__ == "__main__":
    print("Streaming agent execution:")
    print("-" * 40)

    with AgentRuntime() as runtime:
        result = runtime.run(agent, "Write a haiku about Python programming")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.11_streaming
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)

        # Streaming alternative:
        # for event in runtime.stream(agent, "Write a haiku about Python programming"):
        #     if event.type == "done":
        #         print(f"\nResult: {event.output}")
        #         print(f"Workflow: {event.execution_id}")
        #     elif event.type == "waiting":
        #         print("[Waiting...]")
        #     elif event.type == "error":
        #         print(f"[Error: {event.content}]")

