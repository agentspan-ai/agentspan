# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Composable Termination Conditions — AND/OR rules for stopping agents.

Demonstrates composable termination conditions using ``&`` (AND) and
``|`` (OR) operators.  Conditions include:

- TextMentionTermination: stop when output contains specific text
- StopMessageTermination: stop on exact match (e.g. "TERMINATE")
- MaxMessageTermination: stop after N messages
- TokenUsageTermination: stop when token budget exceeded

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import (
    Agent,
    AgentRuntime,
    MaxMessageTermination,
    StopMessageTermination,
    TextMentionTermination,
    TokenUsageTermination,
    tool,
)
from settings import settings


# ── Example 1: Simple text mention ───────────────────────────────────

@tool
def search(query: str) -> str:
    """Search for information."""
    return f"Results for '{query}': AI agents are software programs that act autonomously."

agent1 = Agent(
    name="researcher",
    model=settings.llm_model,
    tools=[search],
    instructions="Research the topic and say DONE when you have enough info.",
    termination=TextMentionTermination("DONE"),
)


# ── Example 2: OR — stop on text OR after 20 messages ────────────────

agent2 = Agent(
    name="chatbot",
    model=settings.llm_model,
    instructions="Have a conversation. Say GOODBYE when you're finished.",
    termination=(
        TextMentionTermination("GOODBYE") | MaxMessageTermination(20)
    ),
)


# ── Example 3: AND — stop only when BOTH conditions met ──────────────

# Only terminate when the agent says "FINAL ANSWER" AND we've had
# at least 5 messages (ensuring sufficient deliberation)
agent3 = Agent(
    name="deliberator",
    model=settings.llm_model,
    tools=[search],
    instructions=(
        "Research thoroughly. Only provide your FINAL ANSWER after "
        "using the search tool at least twice."
    ),
    termination=(
        TextMentionTermination("FINAL ANSWER") & MaxMessageTermination(5)
    ),
)


# ── Example 4: Complex composition ───────────────────────────────────

# Stop when: (TERMINATE signal) OR (DONE + at least 10 messages) OR (token budget exceeded)
complex_stop = (
    StopMessageTermination("TERMINATE")
    | (TextMentionTermination("DONE") & MaxMessageTermination(10))
    | TokenUsageTermination(max_total_tokens=50000)
)

agent4 = Agent(
    name="complex_agent",
    model=settings.llm_model,
    tools=[search],
    instructions="Research and provide a comprehensive answer.",
    termination=complex_stop,
)


if __name__ == "__main__":
    # ── Run ─────────────────────────────────────────────────────────────


    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.19_composable_termination
        runtime.deploy(agent1)
        runtime.serve(agent1)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # print("--- Simple text mention termination ---")
        # result = runtime.run(agent1, "What are AI agents?")
        # result.print_result()

