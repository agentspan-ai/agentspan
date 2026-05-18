# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Token & Cost Tracking — monitor LLM token usage per agent run.

Demonstrates the ``TokenUsage`` field on ``AgentResult`` which provides
aggregated token usage across all LLM calls in an agent execution.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import Agent, AgentRuntime, tool
from settings import settings


@tool
def calculate(expression: str) -> str:
    """Evaluate a mathematical expression."""
    result = eval(expression)  # For demo only — use a safe evaluator in production
    return str(result)


agent = Agent(
    name="math_tutor",
    model=settings.llm_model,
    tools=[calculate],
    instructions=(
        "You are a math tutor. Solve problems step by step, using the calculate "
        "tool for computations. Explain each step clearly."
    ),
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            agent,
            "Calculate the compound interest on $10,000 at 5% annual rate "
            "compounded monthly for 3 years.",
        )
        result.print_result()

        # Token usage is automatically extracted from the workflow
        if result.token_usage:
            print("Token Usage Summary:")
            print(f"  Prompt tokens:     {result.token_usage.prompt_tokens}")
            print(f"  Completion tokens: {result.token_usage.completion_tokens}")
            print(f"  Total tokens:      {result.token_usage.total_tokens}")

            # Estimate cost (example pricing — adjust for your model)
            prompt_cost = result.token_usage.prompt_tokens * 0.0025 / 1000
            completion_cost = result.token_usage.completion_tokens * 0.01 / 1000
            print(f"\n  Estimated cost: ${prompt_cost + completion_cost:.4f}")
        else:
            print("(Token usage not available from workflow)")

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.23_token_tracking
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)

