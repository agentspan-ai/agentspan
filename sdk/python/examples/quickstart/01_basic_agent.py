#!/usr/bin/env python3
"""Basic agent — the simplest possible agentspan example."""

from agentspan.agents import Agent, AgentRuntime

agent = Agent(
    name="greeter",
    model="openai/gpt-4o-mini",
    instructions="You are a friendly assistant. Keep responses brief.",
)

if __name__ == "__main__":
    with AgentRuntime() as rt:
        result = rt.run(agent, "Hello! What can you do?")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # rt.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.quickstart.01_basic_agent
        #
        # 2. In a separate long-lived worker process:
        # rt.serve(agent)
