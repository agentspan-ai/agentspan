#!/usr/bin/env python3
"""Deploy — push ML pipeline definition to the server.

CLI equivalent:
    agentspan deploy examples.production.ml_pipeline.agents
"""

from agents import ml_pipeline
from agentspan.agents import AgentRuntime

with AgentRuntime() as rt:
    info = rt.deploy(ml_pipeline)
    for d in info:
        print(f"Deployed: {d.name} (workflow: {d.workflow_name})")
