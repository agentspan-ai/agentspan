# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Google ADK Include Contents — control context passed to sub-agents.

When ``include_contents="none"``, a sub-agent starts fresh without
the parent's conversation history.

Requirements:
    - pip install google-adk
    - Conductor server with include_contents support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=google_gemini/gemini-2.0-flash as environment variable
"""

from google.adk.agents import Agent

from agentspan.agents import AgentRuntime

from settings import settings

# Sub-agent with no parent context
independent_summarizer = Agent(
    name="independent_summarizer",
    model=settings.llm_model,
    instruction=(
        "You are a summarizer. Summarize any text given to you concisely."
    ),
    include_contents="none",  # No parent context
)

# Sub-agent that sees parent context (default)
context_aware_helper = Agent(
    name="context_aware_helper",
    model=settings.llm_model,
    instruction=(
        "You are a helpful assistant that builds on prior conversation context."
    ),
)

coordinator = Agent(
    name="coordinator",
    model=settings.llm_model,
    instruction=(
        "You coordinate tasks. Route summarization to independent_summarizer "
        "and general questions to context_aware_helper."
    ),
    sub_agents=[independent_summarizer, context_aware_helper],
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
        coordinator,
        "Please summarize this: 'The quick brown fox jumps over the lazy dog. "
        "This sentence contains every letter of the alphabet and is commonly "
        "used for typography testing.'",
        )
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(coordinator)
        # CLI alternative:
        # agentspan deploy --package examples.adk.29_include_contents
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(coordinator)
