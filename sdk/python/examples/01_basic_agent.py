# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Basic Agent — 5-line hello world.

Demonstrates the simplest possible agent: a single LLM with no tools.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

from agentspan.agents import Agent, AgentRuntime
from settings import settings

agent = Agent(name="greeter", model=settings.llm_model)

with AgentRuntime() as runtime:
    result = runtime.run(agent, "Say hello and tell me a fun fact about Python programming.")
    print(f'agent completed with status: {result.status}')
    result.print_result()
