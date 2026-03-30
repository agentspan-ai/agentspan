# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Run Monitoring Agent — trigger the monitoring agent deployed by 63d.

Demonstrates:
    - Running a deployed agent by workflow name from a separate process
    - The deploy/serve/run separation in practice

Requirements:
    - Conductor server running
    - 63d_serve_from_package.py running in another terminal
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
"""

from agentspan.agents import AgentRuntime


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        print("Running monitoring agent by name...")
        result = runtime.run("monitoring", "Is everything healthy? Run a full check.")
        print(f"Workflow ID: {result.execution_id}")
        print(f"Output: {result.output}")
