# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Google ADK Callbacks — lifecycle hooks on agent execution.

Demonstrates:
    - before_model_callback: runs before each LLM call (can log or modify)
    - after_model_callback: runs after each LLM call (can inspect or modify)
    - Callbacks are registered as Conductor worker tasks (same as tools)

Architecture:
    agent with callbacks:
      before_model_callback → logs the request, can add context
      after_model_callback  → inspects the response, can flag issues

Requirements:
    - pip install google-adk
    - Conductor server with callback support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=google_gemini/gemini-2.0-flash as environment variable
"""

import json

from google.adk.agents import LlmAgent

from agentspan.agents import AgentRuntime

from settings import settings


# ── Callback functions ────────────────────────────────────────────
# These run as Conductor workers. They receive context about the
# current agent execution and can return data to influence the flow.

def log_before_model(callback_position: str, agent_name: str) -> dict:
    """Called before each LLM invocation.

    Args:
        callback_position: The callback position (before_model).
        agent_name: Name of the agent being executed.

    Returns:
        Dictionary with logging info. Return empty to continue normally.
    """
    print(f"[CALLBACK] Before model call for agent '{agent_name}'")
    # Return empty dict to continue normally (don't skip the LLM call)
    return {}


def inspect_after_model(callback_position: str, agent_name: str,
                        llm_result: str = "") -> dict:
    """Called after each LLM invocation.

    Args:
        callback_position: The callback position (after_model).
        agent_name: Name of the agent.
        llm_result: The LLM's output text.

    Returns:
        Dictionary with inspection results.
    """
    word_count = len(llm_result.split()) if llm_result else 0
    print(f"[CALLBACK] After model call for '{agent_name}': {word_count} words generated")

    # Flag if response is too long
    if word_count > 500:
        print(f"[CALLBACK] Warning: Response exceeds 500 words ({word_count})")

    # Return empty to keep the original response
    return {}


# ── Agent with callbacks ──────────────────────────────────────────

agent = LlmAgent(
    name="monitored_assistant",
    model=settings.llm_model,
    instruction=(
        "You are a helpful assistant. Answer questions concisely. "
        "Keep responses under 200 words."
    ),
    before_model_callback=log_before_model,
    after_model_callback=inspect_after_model,
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.adk.23_callbacks
        runtime.deploy(agent)
        runtime.serve(agent)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(
        # agent,
        # "Explain the difference between supervised and unsupervised machine learning.",
        # )
        # result.print_result()
