#!/usr/bin/env python3
"""Swarm: Claude Code builds a React app, OpenAI reviews it, iterate until approved.

Architecture:
    build_review_swarm (orchestrator, anthropic/claude-sonnet-4-5, SWARM strategy)
        ├── builder  (claude-code/sonnet — Write, Edit, Bash, Read)
        └── reviewer (openai/gpt-4o — text-only code review)

    builder ──HANDOFF_TO_REVIEWER──> reviewer
    reviewer ──HANDOFF_TO_BUILDER──> builder  (if issues found)
    reviewer ──APPROVED──> done

Demonstrates:
    - Mixed-model multi-agent: Claude Code for building, OpenAI for reviewing
    - SWARM orchestration with handoffs between different agent types
    - Claude Code agent as a sub-agent in a multi-agent workflow

Usage:
    uv run python examples/claude_agent_sdk/05_build_and_review.py
"""

from agentspan.agents import Agent, AgentRuntime, Strategy
from agentspan.agents.handoff import OnTextMention

PROJECT_DIR = "/tmp/hello-react"

builder = Agent(
    name="builder",
    model="claude-code/sonnet",
    instructions=(
        f"You are a frontend developer. Write code in {PROJECT_DIR}/.\n"
        "Do NOT ask for confirmation — create and edit files directly.\n\n"
        "When you finish building or fixing, say HANDOFF_TO_REVIEWER followed by "
        "a summary of what you did and include the full contents of App.tsx."
    ),
    tools=["Write", "Edit", "Bash", "Read", "Glob"],
    max_turns=15,
)

reviewer = Agent(
    name="reviewer",
    model="openai/gpt-4o",
    instructions=(
        "You are a senior code reviewer. You receive code from the builder.\n"
        "Check for:\n"
        "- TypeScript correctness\n"
        "- Accessibility (aria labels, semantic HTML)\n"
        "- Clean code (no unused imports, proper naming)\n"
        "- React best practices\n\n"
        "If there are issues, say HANDOFF_TO_BUILDER followed by the list of issues to fix.\n"
        "If everything looks good, say APPROVED followed by a brief summary."
    ),
)

build_review_swarm = Agent(
    name="build_review_swarm",
    model="anthropic/claude-sonnet-4-5",
    instructions=(
        "You orchestrate a build-and-review cycle.\n"
        "1. First, delegate to builder to create the app.\n"
        "2. When builder finishes, delegate to reviewer.\n"
        "3. If reviewer finds issues, send back to builder.\n"
        "4. Repeat until reviewer says APPROVED.\n"
        "5. When approved, output the final summary."
    ),
    agents=[builder, reviewer],
    strategy=Strategy.SWARM,
    handoffs=[
        OnTextMention(text="HANDOFF_TO_REVIEWER", target="reviewer"),
        OnTextMention(text="HANDOFF_TO_BUILDER", target="builder"),
    ],
    max_turns=200,
    timeout_seconds=600,
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.claude_agent_sdk.05_build_and_review
        # runtime.deploy(build_review_swarm)
        # runtime.serve(build_review_swarm)

        # Direct run for local development:
        result = runtime.run(
            build_review_swarm,
            prompt=(
                f"Create a React app in {PROJECT_DIR}/ using Vite + React + TypeScript.\n"
                f"Run: npm create vite@latest {PROJECT_DIR} -- --template react-ts\n"
                f"Then edit {PROJECT_DIR}/src/App.tsx to show a Hello World page with:\n"
                "- A centered heading saying 'Hello, World!'\n"
                "- A subtitle with a welcome message\n"
                "- A counter button that increments on click\n"
                "- Clean, accessible HTML with proper aria labels\n\n"
                "Start by delegating to builder."
            ),
            timeout=600000,
        )
        result.print_result()
        print(f"\n{'=' * 60}")
        print(f"Status: {result.status}")
        print(f"Workflow ID: {result.execution_id}")
        print(f"{'=' * 60}")

        # Show final file
        try:
            with open(f"{PROJECT_DIR}/src/App.tsx") as f:
                print(f"\nFinal App.tsx:\n{f.read()}")
        except FileNotFoundError:
            print("\n(App.tsx not found)")
