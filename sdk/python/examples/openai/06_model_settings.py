# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""OpenAI Agent with Model Settings — temperature, max tokens, and more.

Demonstrates:
    - Configuring ModelSettings for fine-tuned LLM behavior
    - Low temperature for deterministic responses
    - Max tokens limit
    - The server normalizer maps model_settings to AgentConfig temperature/maxTokens.

Requirements:
    - pip install openai-agents
    - Conductor server with OpenAI LLM integration configured
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agents import Agent, ModelSettings

from agentspan.agents import AgentRuntime

from settings import settings

# Creative agent with high temperature
creative_agent = Agent(
    name="creative_writer",
    instructions=(
        "You are a creative writing assistant. Write with vivid imagery "
        "and unexpected metaphors. Be bold and imaginative."
    ),
    model=settings.llm_model,
    model_settings=ModelSettings(
        temperature=0.9,
        max_tokens=500,
    ),
)

# Precise agent with low temperature
precise_agent = Agent(
    name="code_reviewer",
    instructions=(
        "You are a precise code reviewer. Analyze code snippets for bugs, "
        "security issues, and best practices. Be concise and specific."
    ),
    model=settings.llm_model,
    model_settings=ModelSettings(
        temperature=0.1,
        max_tokens=300,
    ),
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.openai.06_model_settings
        runtime.deploy(creative_agent)
        runtime.serve(creative_agent)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # print("=== Creative Agent (temp=0.9) ===")
        # result = runtime.run(
        # creative_agent,
        # "Write a two-sentence story about a robot learning to paint.",
        # )
        # result.print_result()

        # print("\n=== Precise Agent (temp=0.1) ===")
        # result = runtime.run(
        # precise_agent,
        # "Review this Python code: `data = eval(user_input)`",
        # )
        # result.print_result()
