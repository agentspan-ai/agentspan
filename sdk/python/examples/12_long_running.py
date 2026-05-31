# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Long-Running Agent — fire-and-forget with status checking.

Demonstrates starting an agent asynchronously and checking its status
from any process. The agent runs as a Conductor workflow and can be
monitored from the UI or via the API.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

import time

from agentspan.agents import Agent, AgentRuntime
from settings import settings

agent = Agent(
    name="saas_analyst",
    model=settings.llm_model,
    instructions=(
        "You are a data analyst. Provide a brief analysis "
        "when asked about data topics."
    ),
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(agent, "What are the key metrics to track for a SaaS product?")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.12_long_running
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)

        # Async handle alternative:
        # handle = runtime.start(agent, "What are the key metrics to track for a SaaS product?")
        # print(f"Agent started: {handle.execution_id}")

        # # Poll for completion
        # for i in range(30):
        #     status = handle.get_status()
        #     print(f"  [{i}s] Status: {status.status} | Complete: {status.is_complete}")
        #     if status.is_complete:
        #         print(f"\nResult: {status.output}")
        #         break
        #     time.sleep(1)
        # else:
        #     print("\nAgent still running. Check the Conductor UI:")
        #     print(f"  http://localhost:6767/execution/{handle.execution_id}")

