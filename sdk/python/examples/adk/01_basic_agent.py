# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Basic Google ADK Agent — simplest possible agent.

Demonstrates:
    - Defining an agent using Google's Agent Development Kit (ADK)
    - Running it on the Conductor agent runtime (auto-detected)
    - The runtime serializes the agent generically and the server
      normalizes the ADK-specific config into a Conductor workflow.

Requirements:
    - pip install google-adk
    - Conductor server with Google Gemini LLM integration configured
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=google_gemini/gemini-2.0-flash in .env or environment
"""

from google.adk.agents import Agent

from agentspan.agents import AgentRuntime

from settings import settings

agent = Agent(
    name="greeter",
    model=settings.llm_model,
    instruction="You are a friendly assistant. Keep your responses concise and helpful.",
)

with AgentRuntime() as runtime:
    result = runtime.run(agent, "Say hello and tell me a fun fact about machine learning.")
    print(f'agent completed with status: {result.status}')
    result.print_result()
