# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Docker-sandboxed code execution — run LLM-generated code in a container.

The agent writes code and the ``DockerCodeExecutor`` runs it inside an
isolated Docker container.  No network access, limited memory, and the
host filesystem is untouched.

Requirements:
    - Conductor server with LLM support
    - Docker installed and daemon running
    - export AGENTSPAN_SERVER_URL=http://localhost:8080/api
"""

from agentspan.agents import Agent, AgentRuntime, CodeExecutionConfig
from agentspan.agents.code_executor import DockerCodeExecutor
from settings import settings

docker_coder = Agent(
    name="docker_coder",
    model=settings.llm_model,
    code_execution=CodeExecutionConfig(
        executor=DockerCodeExecutor(
            image="python:3.12-slim",
            timeout=30,
            network_enabled=False,
            memory_limit="256m",
        ),
    ),
    instructions=(
        "You write Python code that runs in a sandboxed Docker container. "
        "You have no network access. Write self-contained code."
    ),
)

with AgentRuntime() as runtime:
    print("--- Docker Sandboxed Code Execution ---")
    result = runtime.run(
        docker_coder,
        "Print Python's version and the container's hostname.",
    )
    result.print_result()
