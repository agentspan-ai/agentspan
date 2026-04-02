#!/usr/bin/env python3
"""CLI error output — verify the agent sees stdout/stderr on non-zero exit.

Runs an agent that deliberately triggers a failing CLI command and then
asks the agent to report what it saw.  The test passes when the agent's
final output contains the stderr text produced by the failed command.

Requirements:
  - Conductor server with LLM support
  - AGENTSPAN_SERVER_URL  (e.g. http://localhost:6767/api)
  - AGENTSPAN_LLM_MODEL   (e.g. openai/gpt-4o-mini)
"""

from agentspan.agents import Agent, AgentRuntime

MODEL = "openai/gpt-4o-mini"

agent = Agent(
    name="cli_error_tester",
    model=MODEL,
    instructions=(
        "You have a run_command tool. "
        "Run the exact command the user asks you to run, then report "
        "the full stdout and stderr you received from the tool result."
    ),
    cli_commands=True,
    cli_allowed_commands=["ls"],
)

prompt = (
    "Run: ls /nonexistent_path_that_does_not_exist\n"
    "Then tell me the exact stderr you got back."
)

if __name__ == "__main__":
    with AgentRuntime() as rt:
        result = rt.run(agent, prompt)
        result.print_result()
        output = result.output or ""

        # Verify the agent saw the error output
        assert "No such file or directory" in output or "nonexistent" in output, (
            f"Agent did not surface CLI error output. Got: {output!r}"
        )
        print("\nPASS: agent correctly reported CLI error output")

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # rt.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.74_cli_error_output
        #
        # 2. In a separate long-lived worker process:
        # rt.serve(agent)
