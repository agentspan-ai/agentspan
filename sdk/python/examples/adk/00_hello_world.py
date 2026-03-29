# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Minimal Google ADK greeting agent — for debugging the native runner.

The simplest possible ADK agent: no tools, no structured output, one turn.
Used to verify the ADK native shim works end-to-end before testing more
complex examples.

Requirements:
    - pip install google-adk
    - GOOGLE_API_KEY or GEMINI_API_KEY environment variable
    - AGENTSPAN_LLM_MODEL=google_gemini/gemini-2.0-flash (for AgentSpan runs)
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api (for AgentSpan runs)
"""

from google.adk.agents import Agent

from agentspan.agents import AgentRuntime

from settings import settings

agent = Agent(
    name="greeter",
    model=settings.llm_model,
    instruction="You are a friendly greeter. Reply with a warm hello and one fun fact.",
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.adk.00_hello_world
        runtime.deploy(agent)
        runtime.serve(agent)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(agent, "Say hello!")
        # result.print_result()
