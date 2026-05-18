# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Run by Name — execute a pre-deployed agent via ``runtime.run()``.

Demonstrates:
    - ``runtime.run("workflow_name", prompt)`` by deployed name
    - The default ``run()`` happy path for executing an already-registered agent
    - A short commented production reminder for deploy + serve separation

Requirements:
    - Conductor server running
    - Agent deployed (run 63_deploy.py first)
    - Workers running (run 63b_serve.py in another terminal)
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api in .env or environment
"""

from agentspan.agents import AgentRuntime


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run("doc_assistant", "How do I reset my password?")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(...)
        # CLI alternative:
        # agentspan deploy --package examples.63c_run_by_name
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(...)
