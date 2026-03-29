# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Callbacks — lifecycle hooks before and after LLM calls.

Demonstrates using ``before_model_callback`` and ``after_model_callback``
to intercept and inspect LLM interactions. Callbacks are registered as
Conductor worker tasks and execute server-side.

Requirements:
    - Conductor server with callback support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import Agent, AgentRuntime, tool
from settings import settings


# ── Callback functions ─────────────────────────────────────────────

def log_before_model(messages: list = None, **kwargs) -> dict:
    """Log details before each LLM call.

    Args:
        messages: The messages about to be sent to the LLM.

    Returns:
        Empty dict to continue normally, or a dict with 'response'
        to skip the LLM call.
    """
    msg_count = len(messages) if messages else 0
    print(f"  [before_model] Sending {msg_count} messages to LLM")
    return {}  # Continue to LLM


def inspect_after_model(llm_result: str = None, **kwargs) -> dict:
    """Inspect the LLM response after each call.

    Args:
        llm_result: The LLM's response text.

    Returns:
        Empty dict to keep the response, or a dict with 'response'
        to replace it.
    """
    length = len(llm_result) if llm_result else 0
    print(f"  [after_model] LLM returned {length} characters")
    return {}  # Keep original response


# ── Tool ───────────────────────────────────────────────────────────

@tool
def get_facts(topic: str) -> dict:
    """Get interesting facts about a topic.

    Args:
        topic: The topic to get facts about.

    Returns:
        Dictionary with facts.
    """
    facts = {
        "ai": ["AI was coined in 1956", "GPT-4 has ~1.7T parameters"],
        "space": ["The ISS orbits at 17,500 mph", "Mars has the tallest volcano"],
    }
    for key, vals in facts.items():
        if key in topic.lower():
            return {"topic": topic, "facts": vals}
    return {"topic": topic, "facts": ["No specific facts found."]}


# ── Agent with callbacks ───────────────────────────────────────────

agent = Agent(
    name="monitored_agent_47",
    model=settings.llm_model,
    instructions="You are a helpful assistant. Use get_facts when asked about topics.",
    tools=[get_facts],
    before_model_callback=log_before_model,
    after_model_callback=inspect_after_model,
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.47_callbacks
        runtime.deploy(agent)
        runtime.serve(agent)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(agent, "Tell me interesting facts about AI and space.")
        # result.print_result()

