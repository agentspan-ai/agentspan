# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Google ADK Thinking Config — extended reasoning for complex tasks.

Uses ADK's ThinkingConfig to enable extended thinking mode,
allowing the LLM to reason step-by-step before responding.

Requirements:
    - pip install google-adk
    - Conductor server with thinking config support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=google_gemini/gemini-2.0-flash as environment variable
"""

from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from google.genai import types

from agentspan.agents import AgentRuntime

from settings import settings


def calculate(expression: str) -> dict:
    """Evaluate a mathematical expression.

    Args:
        expression: A math expression to evaluate.

    Returns:
        Dictionary with the result.
    """
    try:
        result = eval(expression, {"__builtins__": {}})
        return {"expression": expression, "result": result}
    except Exception as e:
        return {"expression": expression, "error": str(e)}


agent = Agent(
    name="deep_thinker",
    model=settings.llm_model,
    instruction=(
        "You are an analytical assistant. Think carefully through complex "
        "problems step by step. Use the calculate tool for math."
    ),
    tools=[FunctionTool(calculate)],
    generate_content_config=types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_budget=2048),
    ),
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.adk.30_thinking_config
        runtime.deploy(agent)
        runtime.serve(agent)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(
        # agent,
        # "If a train travels 120 km in 2 hours, then speeds up by 50% for "
        # "the next 3 hours, what is the total distance traveled?",
        # )
        # result.print_result()
