# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Thinking Config — enable extended reasoning for complex tasks.

When ``thinking_budget_tokens`` is set, the agent uses extended thinking
mode, allowing the LLM to reason step-by-step before responding. This
improves performance on complex analytical tasks at the cost of higher
token usage.

Requirements:
    - Conductor server with thinking config support
    - A model that supports extended thinking (e.g., Claude with thinking)
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import Agent, AgentRuntime, tool
from settings import settings


@tool
def calculate(expression: str) -> dict:
    """Evaluate a mathematical expression.

    Args:
        expression: A math expression to evaluate (e.g., '2 + 3 * 4').

    Returns:
        Dictionary with the result.
    """
    try:
        result = eval(expression, {"__builtins__": {}})
        return {"expression": expression, "result": result}
    except Exception as e:
        return {"expression": expression, "error": str(e)}


agent = Agent(
    name="deep_thinker_50",
    model=settings.llm_model,
    instructions=(
        "You are an analytical assistant. Think carefully through complex "
        "problems step by step. Use the calculate tool for math."
    ),
    tools=[calculate],
    thinking_budget_tokens=2048,
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            agent,
            "If a train travels 120 km in 2 hours, then speeds up by 50% for "
            "the next 3 hours, what is the total distance traveled?",
        )
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.50_thinking_config
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)

