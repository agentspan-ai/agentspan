# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Code Execution — sandboxed environments for running LLM-generated code.

Demonstrates all four code executor types:

1. LocalCodeExecutor — runs code in a local subprocess (no sandbox)
2. DockerCodeExecutor — runs code inside a Docker container (sandboxed)
3. JupyterCodeExecutor — runs code in a persistent Jupyter kernel
4. ServerlessCodeExecutor — runs code via a remote API

Each executor is attached to an agent as a tool via ``executor.as_tool()``.

Requirements:
    - Conductor server with LLM support
    - Docker (for DockerCodeExecutor example)
    - pip install jupyter_client ipykernel (for JupyterCodeExecutor)
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import Agent, AgentRuntime
from settings import settings
from agentspan.agents.code_executor import (
    DockerCodeExecutor,
    JupyterCodeExecutor,
    LocalCodeExecutor,
)


# ── Example 1: Local code execution ─────────────────────────────────

local_executor = LocalCodeExecutor(language="python", timeout=10)

coder = Agent(
    name="local_coder",
    model=settings.llm_model,
    tools=[local_executor.as_tool()],
    instructions=(
        "You are a Python developer. Write and execute code to solve problems. "
        "Always use the execute_code tool to run your code and show results."
    ),
)

# ── Example 2: Docker-sandboxed execution ────────────────────────────

docker_executor = DockerCodeExecutor(
    image="python:3.12-slim",
    timeout=15,
    network_enabled=False,  # No network access for safety
    memory_limit="256m",
)

sandboxed_coder = Agent(
    name="sandboxed_coder",
    model=settings.llm_model,
    tools=[docker_executor.as_tool(name="run_sandboxed")],
    instructions=(
        "You write Python code that runs in a sandboxed Docker container. "
        "Use the run_sandboxed tool to execute code safely."
    ),
)

# ── Example 3: Jupyter kernel (persistent state) ────────────────────

# jupyter_executor = JupyterCodeExecutor(timeout=30)
# data_scientist = Agent(
#     name="data_scientist",
#     model=settings.llm_model,
#     tools=[jupyter_executor.as_tool(name="run_notebook")],
#     instructions=(
#         "You are a data scientist. Use the run_notebook tool to execute "
#         "Python code. Variables persist between calls, so you can build "
#         "up analysis step by step — just like a Jupyter notebook."
#     ),
# )


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        print("--- Local Code Execution ---")
        result = runtime.run(
            coder,
            "Write a Python function to find the first 10 Fibonacci numbers and print them.",
        )
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(coder)
        # CLI alternative:
        # agentspan deploy --package examples.24_code_execution
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(coder)

