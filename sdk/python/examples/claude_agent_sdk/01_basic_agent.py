#!/usr/bin/env python3
"""Basic Claude Code agent using the Agent(model='claude-code') API.

Prerequisites:
    pip install claude-code-sdk  # or: uv add claude-code-sdk
    export ANTHROPIC_API_KEY=sk-...

Usage:
    # Start the agentspan server first, then:
    uv run python examples/claude_agent_sdk/01_basic_agent.py
"""

from agentspan.agents import Agent, AgentRuntime

reviewer = Agent(
    name="file_lister",
    model="claude-code/sonnet",
    instructions="You are a helpful assistant that explores codebases.",
    tools=["Read", "Glob", "Grep"],
    max_turns=5,
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            reviewer,
            prompt="Use Glob to find all .py files in the examples/claude_agent_sdk/ directory.",
        )
        result.print_result()
        print("\n--- Metadata ---")
        print(f"Workflow ID: {result.execution_id}")
        print(f"Status: {result.status}")
        if result.token_usage:
            print(f"Token usage: {result.token_usage}")

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(reviewer)
        # CLI alternative:
        # agentspan deploy --package examples.claude_agent_sdk.01_basic_agent
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(reviewer)
