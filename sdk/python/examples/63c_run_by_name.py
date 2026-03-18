# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Run by Name — execute a pre-deployed agent without its definition.

Demonstrates:
    - runtime.run("workflow_name", prompt) — run by name
    - runtime.start("workflow_name", prompt) — fire-and-forget by name
    - runtime.stream("workflow_name", prompt) — stream by name
    - Optional version parameter for workflow versioning

The agent must be deployed (63_deploy.py) and workers must be
running (63b_serve.py) for tool tasks to execute.

Requirements:
    - Conductor server running
    - Agent deployed (run 63_deploy.py first)
    - Workers running (run 63b_serve.py in another terminal)
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
"""

from agentspan.agents import AgentRuntime

with AgentRuntime() as runtime:
    # ── Run by name (synchronous, blocks until complete) ─────────────
    print("Running doc_assistant by name...")
    result = runtime.run("doc_assistant", "How do I reset my password?")
    print(f"Output: {result.output}\n")

    # ── Start by name (fire-and-forget, returns handle) ──────────────
    print("Starting ops_bot by name...")
    handle = runtime.start("ops_bot", "Check the status of the API gateway")
    print(f"Started workflow: {handle.workflow_id}")

    # Wait for it to complete
    status = handle.get_status()
    print(f"Status: {status.status}")
    if status.is_complete:
        print(f"Output: {status.output}\n")

    # ── Stream by name ───────────────────────────────────────────────
    print("Streaming doc_assistant by name...")
    for event in runtime.stream("doc_assistant", "What are the API rate limits?"):
        if event.type == "token":
            print(event.token, end="", flush=True)
        elif event.type == "done":
            print(f"\n\nFinal output: {event.output}")
