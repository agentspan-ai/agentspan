#!/usr/bin/env python3
"""Serve — start workers that execute tools.

This is the runtime step. It registers Python tool functions (CLI tools,
code execution, guardrails, handoff checks, etc.) as Conductor workers
and polls for tasks until interrupted.

Run in a separate terminal or as a systemd/Docker service.

CLI equivalent:
    agentspan serve examples.production.github_coding_agent.agents
"""

from agents import pipeline
from agentspan.agents import AgentRuntime

with AgentRuntime() as rt:
    print("Starting workers for github_coding_agent pipeline...")
    print("Press Ctrl+C to stop.")
    rt.serve(pipeline)  # Blocks until interrupted
