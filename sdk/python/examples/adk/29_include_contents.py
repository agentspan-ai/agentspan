# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Google ADK Include Contents — control context passed to sub-agents.

When ``include_contents="none"``, a sub-agent starts fresh without
the parent's conversation history.

Requirements:
    - pip install google-adk
    - Conductor server with include_contents support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=google_gemini/gemini-2.0-flash in .env or environment
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

with AgentRuntime() as runtime:
    result = runtime.run(
        coordinator,
        "Please summarize this: 'The quick brown fox jumps over the lazy dog. "
        "This sentence contains every letter of the alphabet and is commonly "
        "used for typography testing.'",
    )
    result.print_result()
