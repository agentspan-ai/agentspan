#!/usr/bin/env python3
"""Multi-agent — sequential pipeline with two agents."""

from conductor.ai.agents import Agent, AgentRuntime

researcher = Agent(
    name="researcher",
    model="anthropic/claude-sonnet-4-6",
    instructions="Research the topic. Provide 3 key facts.",
)

writer = Agent(
    name="writer",
    model="anthropic/claude-sonnet-4-6",
    instructions="Write a brief summary based on the research provided.",
)

pipeline = researcher >> writer
# Exposed as `agent` so aggregate runners (e.g. quickstart/run_all.py) can pick it up.
agent = pipeline

prompt = "Quantum computing"

if __name__ == "__main__":
    with AgentRuntime() as rt:
        result = rt.run(pipeline, prompt)
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # rt.deploy(pipeline)
        # CLI alternative:
        # agentspan deploy --package examples.quickstart.03_multi_agent
        #
        # 2. In a separate long-lived worker process:
        # rt.serve(pipeline)
