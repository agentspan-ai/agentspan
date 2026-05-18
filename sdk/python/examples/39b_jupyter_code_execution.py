# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Jupyter kernel code execution — persistent state across calls.

The ``JupyterCodeExecutor`` runs code in a real Jupyter kernel.  Variables,
imports, and definitions persist between executions — just like cells in a
notebook.  Perfect for data-science workflows where analysis is built up
step by step.

Requirements:
    - Conductor server with LLM support
    - pip install jupyter_client ipykernel
    - export AGENTSPAN_SERVER_URL=http://localhost:6767/api
"""

from agentspan.agents import Agent, AgentRuntime, CodeExecutionConfig
from agentspan.agents.code_executor import JupyterCodeExecutor
from settings import settings

jupyter_coder = Agent(
    name="jupyter_coder",
    model=settings.llm_model,
    code_execution=CodeExecutionConfig(
        executor=JupyterCodeExecutor(
            kernel_name="python3",
            timeout=30,
            startup_code="import math",
        ),
    ),
    instructions=(
        "You are a data scientist. Variables persist between code executions, "
        "just like a Jupyter notebook. Build up your analysis step by step — "
        "import libraries once, then reuse them in subsequent calls. "
        "The 'math' module is already imported for you."
    ),
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        print("--- Jupyter Kernel Code Execution ---")
        result = runtime.run(
            jupyter_coder,
            "Compute the first 10 Fibonacci numbers using a loop, store them in a "
            "list called 'fibs', and print them. Then in a second execution, print "
            "the sum of 'fibs' (it should still exist from the first call).",
        )
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(jupyter_coder)
        # CLI alternative:
        # agentspan deploy --package examples.39b_jupyter_code_execution
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(jupyter_coder)

