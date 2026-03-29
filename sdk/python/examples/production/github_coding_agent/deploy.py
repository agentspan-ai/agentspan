#!/usr/bin/env python3
"""Deploy — push agent definitions to the server.

This is the CI/CD step. It compiles the agent pipeline into a Conductor
workflow and registers all task definitions on the server. No workers
are started.

CLI equivalent:
    agentspan deploy examples.production.github_coding_agent.agents
"""

from agents import pipeline
from agentspan.agents import AgentRuntime

with AgentRuntime() as rt:
    info = rt.deploy(pipeline)
    for d in info:
        print(f"Deployed: {d.name} (workflow: {d.workflow_name})")
