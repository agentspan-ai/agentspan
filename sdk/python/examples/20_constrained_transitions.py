# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Constrained Speaker Transitions — control which agents can follow which.

Demonstrates ``allowed_transitions`` which restricts which agent can
speak after which.  Useful for enforcing conversational protocols.

In this example, a code review workflow enforces:
    - developer can only be followed by reviewer
    - reviewer can only be followed by developer or approver
    - approver can only be followed by developer (for revisions)

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import Agent, AgentRuntime, Strategy
from settings import settings

developer = Agent(
    name="developer",
    model=settings.llm_model,
    instructions=(
        "You are a software developer. Write or revise code based on feedback. "
        "Keep responses focused on code changes."
    ),
)

reviewer = Agent(
    name="reviewer",
    model=settings.llm_model,
    instructions=(
        "You are a code reviewer. Review the developer's code for bugs, style, "
        "and best practices. Provide specific, actionable feedback."
    ),
)

approver = Agent(
    name="approver",
    model=settings.llm_model,
    instructions=(
        "You are the tech lead. Review the code and feedback. Either approve "
        "the code or request revisions with specific guidance."
    ),
)

# Constrained transitions enforce a review protocol:
#   developer → reviewer (code must be reviewed)
#   reviewer → developer OR approver (send back for fixes or escalate)
#   approver → developer (request revisions)
code_review = Agent(
    name="code_review",
    model=settings.llm_model,
    agents=[developer, reviewer, approver],
    strategy=Strategy.ROUND_ROBIN,
    max_turns=6,
    allowed_transitions={
        "developer": ["reviewer"],
        "reviewer": ["developer", "approver"],
        "approver": ["developer"],
    },
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            code_review,
            "Write a Python function to validate email addresses using regex.",
        )
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(code_review)
        # CLI alternative:
        # agentspan deploy --package examples.20_constrained_transitions
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(code_review)

