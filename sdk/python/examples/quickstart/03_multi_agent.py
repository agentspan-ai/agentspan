#!/usr/bin/env python3
"""Multi-agent — sequential pipeline with two agents."""

from agentspan.agents import Agent, AgentRuntime

researcher = Agent(
    name="researcher",
    model="openai/gpt-4o-mini",
    instructions="Research the topic. Provide 3 key facts.",
)

writer = Agent(
    name="writer",
    model="openai/gpt-4o-mini",
    instructions="Write a brief summary based on the research provided.",
)

pipeline = researcher >> writer

if __name__ == "__main__":
    with AgentRuntime() as rt:
        result = rt.run(pipeline, "Quantum computing")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # rt.deploy(pipeline)
        # CLI alternative:
        # agentspan deploy --package examples.quickstart.03_multi_agent
        #
        # 2. In a separate long-lived worker process:
        # rt.serve(pipeline)
