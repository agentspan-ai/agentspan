# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Agent Discussion — durable round-robin debate compiled to a Conductor DoWhile loop.

Demonstrates a multi-turn discussion between agents with opposing
viewpoints using the ``round_robin`` strategy.  The entire debate runs
server-side as a Conductor DoWhile loop — durable, restartable, and
observable in the Conductor UI.  After the discussion, a summary agent
distills the transcript into a balanced conclusion via the ``>>``
pipeline operator.

Flow (all server-side):
    DoWhile(6 turns):
        turn 0 → optimist
        turn 1 → skeptic
        turn 2 → optimist
        ...
    summarizer produces conclusion

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import Agent, AgentRuntime, Strategy
from settings import settings

# ── Discussion participants ──────────────────────────────────────────

optimist = Agent(
    name="optimist",
    model=settings.llm_model,
    instructions=(
        "You are an optimistic technologist debating a topic. "
        "Argue FOR the topic. Keep your response to 2-3 concise paragraphs. "
        "Acknowledge the other side's points before making your case."
    ),
)

skeptic = Agent(
    name="skeptic",
    model=settings.llm_model,
    instructions=(
        "You are a thoughtful skeptic debating a topic. "
        "Raise concerns and argue AGAINST the topic. "
        "Keep your response to 2-3 concise paragraphs. "
        "Acknowledge the other side's points before making your case."
    ),
)

summarizer = Agent(
    name="summarizer",
    model=settings.llm_model,
    instructions=(
        "You are a neutral moderator. You have just observed a debate "
        "between an optimist and a skeptic. Summarize the key arguments "
        "from both sides and provide a balanced conclusion. "
        "Structure your response with: Key Arguments For, "
        "Key Arguments Against, and Balanced Conclusion."
    ),
)

# ── Round-robin discussion: 6 turns (3 rounds of back-and-forth) ────

discussion = Agent(
    name="discussion",
    model=settings.llm_model,
    agents=[optimist, skeptic],
    strategy=Strategy.ROUND_ROBIN,
    max_turns=6,
)

# Pipe discussion transcript to summarizer
pipeline = discussion >> summarizer


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            pipeline,
            "Should AI agents be allowed to autonomously make financial decisions for individuals?",
        )
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(pipeline)
        # CLI alternative:
        # agentspan deploy --package examples.15_agent_discussion
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(pipeline)

