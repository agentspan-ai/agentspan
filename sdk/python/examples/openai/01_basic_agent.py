# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Basic OpenAI Agent — simplest possible agent with no tools.

Demonstrates:
    - Defining an agent using the OpenAI Agents SDK
    - Running it on the Conductor agent runtime (auto-detected)
    - The runtime serializes the agent generically and the server
      normalizes the OpenAI-specific config into a Conductor workflow.

Requirements:
    - pip install openai-agents
    - Conductor server with OpenAI LLM integration configured
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agents import Agent

from agentspan.agents import AgentRuntime

from settings import settings

agent = Agent(
    name="greeter",
    instructions="You are a friendly assistant. Keep your responses concise and helpful.",
    model=settings.llm_model,
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.openai.01_basic_agent
        runtime.deploy(agent)
        runtime.serve(agent)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(agent, "Say hello and tell me a fun fact about the Python programming language.")
        # result.print_result()
