# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Sequential Pipeline — Agent >> Agent >> Agent.

Demonstrates the sequential strategy where agents run in order and the
output of each agent becomes the input of the next.

Also shows the >> operator shorthand.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import Agent, AgentRuntime, Strategy
from settings import settings

# ── Pipeline agents ─────────────────────────────────────────────────

researcher = Agent(
    name="researcher",
    model=settings.llm_model,
    instructions=(
        "You are a researcher. Given a topic, provide key facts and data points. "
        "Be thorough but concise. Output raw research findings."
    ),
)

writer = Agent(
    name="writer",
    model=settings.llm_model,
    instructions=(
        "You are a writer. Take research findings and write a clear, engaging "
        "article. Use headers and bullet points where appropriate."
    ),
)

editor = Agent(
    name="editor",
    model=settings.llm_model,
    instructions=(
        "You are an editor. Review the article for clarity, grammar, and tone. "
        "Make improvements and output the final polished version."
    ),
)

# ── Option 1: Using >> operator ─────────────────────────────────────

pipeline = researcher >> writer >> editor


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.06_sequential_pipeline
        runtime.deploy(pipeline)
        runtime.serve(pipeline)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(pipeline, "The impact of AI agents on software development in 2025")
        # result.print_result()

        # # ── Option 2: Using strategy parameter (equivalent) ────────────────

        # # pipeline = Agent(
        # #     name="content_pipeline",
        # #     model=settings.llm_model,
        # #     agents=[researcher, writer, editor],
        # #     strategy=Strategy.SEQUENTIAL,
        # # )
        # # with AgentRuntime() as runtime:
        # #     result = runtime.run(pipeline, "The impact of AI agents on software development in 2025")

