#!/usr/bin/env python3
"""Claude Code agent that spawns subagents to demonstrate DAG task injection.

The Agent tool in Claude Code creates subagents — each one appears as a
separate task in the workflow execution DAG via SubagentStart/SubagentStop hooks.

Usage:
    CLAUDECODE= uv run python examples/claude_agent_sdk/03_subagent_demo.py
"""

from agentspan.agents import Agent, AgentRuntime, ClaudeCode


def main():
    analyzer = Agent(
        name="codebase_analyzer",
        model=ClaudeCode("sonnet", permission_mode=ClaudeCode.PermissionMode.ACCEPT_EDITS),
        instructions="""\
You are a codebase analyzer. When asked to analyze a directory:

1. Use Glob to find relevant files
2. Use the Agent tool to spawn a subagent that reads and summarizes one file
3. Give a brief overall summary

Keep it concise — max 2-3 tool calls total.""",
        tools=["Read", "Glob", "Grep", "Agent"],
        max_turns=10,
    )

    with AgentRuntime() as runtime:
        result = runtime.run(
            analyzer,
            prompt="Find Python files in examples/claude_agent_sdk/ and use a subagent to review the simplest one. Summarize in 2 sentences.",
        )
        result.print_result()
        print("\n--- Metadata ---")
        print(f"Execution ID: {result.execution_id}")
        print(f"Status: {result.status}")


if __name__ == "__main__":
    main()
