# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Include Contents — control context passed to sub-agents.

When ``include_contents="none"``, a sub-agent starts with a clean slate
and does NOT see the parent agent's conversation history. This is useful
for sub-agents that should work independently without being influenced
by prior messages.

Requirements:
    - Conductor server with include_contents support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import Agent, AgentRuntime, tool
from settings import settings


@tool
def summarize_text(text: str) -> dict:
    """Summarize a piece of text.

    Args:
        text: The text to summarize.

    Returns:
        Dictionary with the summary.
    """
    words = text.split()
    return {"summary": " ".join(words[:20]) + "...", "word_count": len(words)}


# This sub-agent won't see the parent's conversation history
independent_summarizer = Agent(
    name="independent_summarizer_49",
    model=settings.llm_model,
    instructions="You are a summarizer. Summarize any text given to you concisely.",
    tools=[summarize_text],
    include_contents="none",  # No parent context
)

# This sub-agent WILL see the parent's conversation history (default)
context_aware_helper = Agent(
    name="context_aware_helper_49",
    model=settings.llm_model,
    instructions="You are a helpful assistant that builds on prior conversation context.",
)

coordinator = Agent(
    name="coordinator_49",
    model=settings.llm_model,
    instructions=(
        "You coordinate tasks. Route summarization requests to "
        "independent_summarizer_49 and general questions to context_aware_helper_49."
    ),
    agents=[independent_summarizer, context_aware_helper],
    strategy="handoff",
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.49_include_contents
        runtime.deploy(coordinator)
        runtime.serve(coordinator)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(
        #     coordinator,
        #     "Please summarize this: 'The quick brown fox jumps over the lazy dog. "
        #     "This sentence contains every letter of the alphabet and is commonly "
        #     "used for typography testing.'",
        # )
        # result.print_result()

