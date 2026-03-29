# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Google ADK Agent with Generation Config — temperature and output control.

Demonstrates:
    - Using generate_content_config for model tuning
    - Low temperature for factual/deterministic responses
    - High temperature for creative responses
    - Max output tokens control

Requirements:
    - pip install google-adk
    - Conductor server with Google Gemini LLM integration configured
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=google_gemini/gemini-2.0-flash as environment variable
"""

from google.adk.agents import Agent

from agentspan.agents import AgentRuntime

from settings import settings

# Precise agent — low temperature for factual responses
factual_agent = Agent(
    name="fact_checker",
    model=settings.llm_model,
    instruction=(
        "You are a precise fact-checker. Provide accurate, well-sourced "
        "answers. Be concise and avoid speculation."
    ),
    generate_content_config={
        "temperature": 0.1,
    },
)

# Creative agent — high temperature for creative writing
creative_agent = Agent(
    name="storyteller",
    model=settings.llm_model,
    instruction=(
        "You are an imaginative storyteller. Create vivid, engaging "
        "narratives with rich descriptions and unexpected twists."
    ),
    generate_content_config={
        "temperature": 0.9,
    },
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.adk.05_generation_config
        runtime.deploy(factual_agent)
        runtime.serve(factual_agent)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # print("=== Factual Agent (temp=0.1) ===")
        # result = runtime.run(
        # factual_agent,
        # "What is the speed of light in a vacuum?",
        # )
        # result.print_result()

        # print("\n=== Creative Agent (temp=0.9) ===")
        # result = runtime.run(
        # creative_agent,
        # "Write a two-sentence story about a cat who discovered a hidden library.",
        # )
        # result.print_result()
