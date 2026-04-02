#!/usr/bin/env python3

# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Sequential Agent Pipeline — SequentialAgent runs sub-agents in fixed order.

Mirrors the pattern from Google ADK samples (story_teller, llm-auditor).
Each agent in the pipeline runs in order, with outputs flowing to the next.
"""

from google.adk.agents import Agent, SequentialAgent

from agentspan.agents import AgentRuntime

from settings import settings


def main():
    # Step 1: Research agent gathers facts
    researcher = Agent(
        name="researcher",
        model=settings.llm_model,
        instruction=(
            "You are a research assistant. Given the user's topic, "
            "provide 3 key facts about it in a numbered list. Be concise."
        ),
    )

    # Step 2: Writer agent takes the research and writes a summary
    writer = Agent(
        name="writer",
        model=settings.llm_model,
        instruction=(
            "You are a skilled writer. Take the research provided in the conversation "
            "and write a single engaging paragraph summarizing the key points. "
            "Keep it under 100 words."
        ),
    )

    # Step 3: Editor agent polishes the summary
    editor = Agent(
        name="editor",
        model=settings.llm_model,
        instruction=(
            "You are an editor. Review the paragraph from the writer and improve it. "
            "Fix any issues with clarity, grammar, or flow. Output only the final polished paragraph."
        ),
    )

    # Pipeline: researcher → writer → editor
    pipeline = SequentialAgent(
        name="content_pipeline",
        sub_agents=[researcher, writer, editor],
    )

    with AgentRuntime() as runtime:
        result = runtime.run(pipeline, "The history of the Internet")
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(pipeline)
        # CLI alternative:
        # agentspan deploy --package examples.adk.11_sequential_agent
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(pipeline)



if __name__ == "__main__":
    main()
