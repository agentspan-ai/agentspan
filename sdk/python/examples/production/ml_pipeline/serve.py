#!/usr/bin/env python3
"""Serve — start workers for ML pipeline.

CLI equivalent:
    agentspan serve examples.production.ml_pipeline.agents
"""

from agents import ml_pipeline
from agentspan.agents import AgentRuntime

with AgentRuntime() as rt:
    print("Starting workers for ML pipeline...")
    print("Press Ctrl+C to stop.")
    rt.serve(ml_pipeline)
