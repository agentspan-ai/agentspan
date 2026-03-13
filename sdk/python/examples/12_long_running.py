# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Long-Running Agent — fire-and-forget with status checking.

Demonstrates starting an agent asynchronously and checking its status
from any process. The agent runs as a Conductor workflow and can be
monitored from the UI or via the API.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
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

# Start agent asynchronously (returns immediately)
with AgentRuntime() as runtime:
    handle = runtime.start(agent, "What are the key metrics to track for a SaaS product?")
    print(f"Agent started: {handle.workflow_id}")

    # Poll for completion
    for i in range(30):
        status = handle.get_status()
        print(f"  [{i}s] Status: {status.status} | Complete: {status.is_complete}")
        if status.is_complete:
            print(f"\nResult: {status.output}")
            break
        time.sleep(1)
    else:
        print("\nAgent still running. Check the Conductor UI:")
        print(f"  http://localhost:8080/execution/{handle.workflow_id}")
