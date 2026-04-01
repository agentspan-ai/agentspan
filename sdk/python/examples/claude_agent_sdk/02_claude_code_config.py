#!/usr/bin/env python3
"""Claude Code agent using the ClaudeCode config object for advanced options.

Shows how to use ClaudeCode() with PermissionMode enum instead of the
'claude-code/opus' slash syntax.

Usage:
    uv run python examples/claude_agent_sdk/02_claude_code_config.py
"""

from agentspan.agents import Agent, AgentRuntime, ClaudeCode


def main():
    reviewer = Agent(
        name="code_reviewer",
        model=ClaudeCode("sonnet", permission_mode=ClaudeCode.PermissionMode.ACCEPT_EDITS),
        instructions="You are a code reviewer. Analyze code for quality, security, and best practices.",
        tools=["Read", "Glob", "Grep"],
        max_turns=5,
    )

    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.claude_agent_sdk.02_claude_code_config
        # runtime.deploy(reviewer)
        # runtime.serve(reviewer)

        # Direct run for local development:
        result = runtime.run(
            reviewer,
            prompt="Use Glob to find .py files in examples/claude_agent_sdk/ and Read one of them. Give a brief code review.",
        )
        result.print_result()
        print("\n--- Metadata ---")
        print(f"Workflow ID: {result.execution_id}")
        print(f"Status: {result.status}")
        if result.token_usage:
            print(f"Token usage: {result.token_usage}")



if __name__ == "__main__":
    main()
