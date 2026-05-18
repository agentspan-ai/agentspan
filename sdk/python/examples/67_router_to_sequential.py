# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Router to Sequential — route to a pipeline sub-agent.

Demonstrates a router that selects between a single agent (for quick
answers) and a sequential pipeline (for research tasks requiring
multiple stages).

Architecture:
    team (ROUTER, router=selector)
    ├── quick_answer          (single agent)
    └── research_pipeline     (SEQUENTIAL)
        ├── researcher
        └── writer

The router agent decides which path to take based on the request.
If it picks the pipeline, the researcher runs first and the writer
summarizes the findings.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api in .env or environment
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

from agentspan.agents import Agent, AgentRuntime, Strategy
from settings import settings


# ── Quick answer (single agent) ─────────────────────────────────────

quick_answer = Agent(
    name="quick_answer_67",
    model=settings.llm_model,
    instructions=(
        "You give quick, 1-2 sentence answers to simple questions."
    ),
)

# ── Research pipeline (sequential) ──────────────────────────────────

researcher = Agent(
    name="researcher_67",
    model=settings.llm_model,
    instructions=(
        "You are a researcher. Research the topic and provide 3-5 key "
        "facts with supporting details."
    ),
)

writer = Agent(
    name="writer_67",
    model=settings.llm_model,
    instructions=(
        "You are a writer. Take the research findings and write a clear, "
        "engaging summary. Use headers and bullet points."
    ),
)

research_pipeline = Agent(
    name="research_pipeline_67",
    model=settings.llm_model,
    agents=[researcher, writer],
    strategy=Strategy.SEQUENTIAL,
)

# ── Router agent ────────────────────────────────────────────────────

selector = Agent(
    name="selector_67",
    model=settings.llm_model,
    instructions=(
        "You are a request classifier. Select the right team member:\n"
        "- quick_answer_67: for simple factual questions with short answers\n"
        "- research_pipeline_67: for research tasks requiring analysis and writing"
    ),
)

# ── Team with router ────────────────────────────────────────────────

team = Agent(
    name="team_67",
    model=settings.llm_model,
    agents=[quick_answer, research_pipeline],
    strategy=Strategy.ROUTER,
    router=selector,
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # ── Scenario 1: Research task (routes to pipeline)
        print("=" * 60)
        print("  Scenario 1: Research task (router → sequential pipeline)")
        print("=" * 60)
        result = runtime.run(
            team,
            "Research the current state of quantum computing and write a summary.",
        )
        result.print_result()

        if result.status == "COMPLETED":
            print("[OK] Router → sequential pipeline completed")
        else:
            print(f"[WARN] Unexpected status: {result.status}")

        # ── Scenario 2: Quick question (routes to single agent)
        print("\n" + "=" * 60)
        print("  Scenario 2: Quick question (router → single agent)")
        print("=" * 60)
        result2 = runtime.run(
            team,
            "What is the capital of France?",
        )
        result2.print_result()

        if result2.status == "COMPLETED":
            print("[OK] Router → quick answer completed")
        else:
            print(f"[WARN] Unexpected status: {result2.status}")

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(team)
        # CLI alternative:
        # agentspan deploy --package examples.67_router_to_sequential
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(team)

