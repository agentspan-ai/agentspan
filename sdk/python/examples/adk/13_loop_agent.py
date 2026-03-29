#!/usr/bin/env python3

# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Loop Agent — LoopAgent repeats sub-agents for iterative refinement.

Mirrors the pattern from Google ADK samples (story_teller, image-scoring).
The loop runs up to max_iterations times, allowing iterative improvement.
"""

from google.adk.agents import Agent, LoopAgent, SequentialAgent

from agentspan.agents import AgentRuntime

from settings import settings


def main():
    # Writer drafts content
    writer = Agent(
        name="draft_writer",
        model=settings.llm_model,
        instruction=(
            "You are a writer. Write or revise a short haiku (3 lines: 5-7-5 syllables) "
            "about the given topic. If there is feedback from a previous critique in the conversation, "
            "incorporate it. Output only the haiku, nothing else."
        ),
    )

    # Critic reviews and provides feedback
    critic = Agent(
        name="critic",
        model=settings.llm_model,
        instruction=(
            "You are a poetry critic. Review the haiku from the writer. "
            "Check: (1) Does it follow 5-7-5 syllable structure? "
            "(2) Is the imagery vivid? (3) Is there a seasonal or nature element? "
            "Provide 1-2 sentences of constructive feedback for improvement."
        ),
    )

    # Each iteration: write → critique
    iteration = SequentialAgent(
        name="write_critique_cycle",
        sub_agents=[writer, critic],
    )

    # Loop the write-critique cycle 3 times
    refinement_loop = LoopAgent(
        name="refinement_loop",
        sub_agents=[iteration],
        max_iterations=3,
    )

    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.adk.13_loop_agent
        runtime.deploy(refinement_loop)
        runtime.serve(refinement_loop)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(refinement_loop, "Write a haiku about autumn leaves")
        # print(f"Status: {result.status}")
        # print(f"Output: {result.output}")



if __name__ == "__main__":
    main()
