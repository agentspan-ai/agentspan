#!/usr/bin/env python3
"""Claude Code agent — uses Claude's built-in tools (Read, Glob, Grep)."""

from agentspan.agents import Agent, AgentRuntime

agent = Agent(
    name="code_explorer",
    model="claude-code/sonnet",
    instructions="You explore codebases and answer questions about them.",
    tools=["Read", "Glob", "Grep"],
    max_turns=5,
)

if __name__ == "__main__":
    with AgentRuntime() as rt:
        result = rt.run(agent, "What Python files are in the current directory?")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # rt.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.quickstart.05_claude_code
        #
        # 2. In a separate long-lived worker process:
        # rt.serve(agent)
