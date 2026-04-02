# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Basic Agent — 5-line hello world.

Demonstrates the simplest possible agent: define an agent, call
``runtime.run()``, and print the result.

Requirements:
    - Agentspan server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api in .env or environment
    - AGENTSPAN_LLM_MODEL set in .env or environment (optional)
"""

from agentspan.agents import Agent, AgentRuntime
from settings import settings

agent = Agent(
    name="greeter",
    model=settings.llm_model,
    instructions="You are a friendly assistant. Keep responses brief.",
)

prompt = "Say hello and tell me a fun fact about Python."


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(agent, prompt)
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.01_basic_agent
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)
