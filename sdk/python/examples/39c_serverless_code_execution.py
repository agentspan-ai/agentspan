# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Serverless code execution — run code via a remote HTTP API.

The ``ServerlessCodeExecutor`` sends code to an HTTP endpoint and returns
the result.  Use this to offload execution to a hosted sandbox, AWS Lambda,
Google Cloud Functions, or any service that accepts a JSON payload:

    POST /execute
    {"code": "print('hello')", "language": "python", "timeout": 30}

    Response:
    {"output": "hello\n", "error": "", "exit_code": 0}

This example starts a tiny local HTTP server to simulate the remote service,
then runs an agent that executes code through it.

Requirements:
    - Conductor server with LLM support
    - export AGENTSPAN_SERVER_URL=http://localhost:8080/api
"""

import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from agentspan.agents import Agent, AgentRuntime, CodeExecutionConfig
from agentspan.agents.code_executor import ServerlessCodeExecutor
from settings import settings


# ── Tiny mock execution server ────────────────────────────────────────


class _ExecuteHandler(BaseHTTPRequestHandler):
    """Handles POST /execute by running code in a subprocess."""

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        code = body.get("code", "")
        timeout = body.get("timeout", 10)
        try:
            proc = subprocess.run(
                ["python3", "-c", code],
                capture_output=True, text=True, timeout=timeout,
            )
            resp = {"output": proc.stdout, "error": proc.stderr, "exit_code": proc.returncode}
        except subprocess.TimeoutExpired:
            resp = {"output": "", "error": "Timed out", "exit_code": 1}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(resp).encode())

    def log_message(self, format, *args):
        pass  # suppress request logs


def _start_mock_server(port: int = 9753) -> HTTPServer:
    server = HTTPServer(("127.0.0.1", port), _ExecuteHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


# ── Agent setup ───────────────────────────────────────────────────────

mock_server = _start_mock_server(port=9753)

serverless_coder = Agent(
    name="serverless_coder",
    model=settings.llm_model,
    code_execution=CodeExecutionConfig(
        executor=ServerlessCodeExecutor(
            endpoint="http://127.0.0.1:9753/execute",
            language="python",
            timeout=15,
        ),
    ),
    instructions=(
        "You write Python code that runs on a remote execution service. "
        "Use the execute_code tool to run code remotely."
    ),
)


if __name__ == "__main__":
    # ── Run ───────────────────────────────────────────────────────────────


    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.39c_serverless_code_execution
        runtime.deploy(serverless_coder)
        runtime.serve(serverless_coder)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # print("--- Serverless Code Execution ---")
        # result = runtime.run(
        #     serverless_coder,
        #     "Calculate 2**100 and print the result.",
        # )
        # result.print_result()


        # mock_server.shutdown()

