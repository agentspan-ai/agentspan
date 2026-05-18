# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Run Monitoring Agent — trigger the monitoring agent deployed by 63d.

Demonstrates:
    - Running a deployed agent by workflow name from a separate process
    - The deploy/serve/run separation in practice

Requirements:
    - Conductor server running
    - 63d_serve_from_package.py running in another terminal
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api in .env or environment
"""

from agentspan.agents import AgentRuntime


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run("monitoring", "Is everything healthy? Run a full check.")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(...)
        # CLI alternative:
        # agentspan deploy --package examples.63e_run_monitoring
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(...)
