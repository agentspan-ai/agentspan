# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""OpenAI Agents SDK migration — sandbox agent (Docker).

This is examples/sandbox/basic.py from the openai-agents SDK
with exactly ONE line changed.

Before (runs directly against OpenAI):
    from agents import Runner

After (runs on Agentspan — durable, observable, scalable):
    from agentspan import Runner

The diff:
    -from agents import Runner
    +from agentspan import Runner

Sandbox agents run code in an isolated Docker environment. The model can
inspect a workspace (files, directories) using a shell tool. With AgentspanRunner:
  - Every shell command the model executes is recorded in Agentspan
  - The full sandbox session is visible in the Agentspan UI
  - If the process crashes, the Agentspan execution history is preserved

Architecture:
    SandboxAgent — openai-agents sandbox agent (file inspection via shell)
    Docker        — isolated container with the workspace files
    AgentspanRunner — routes execution through Agentspan instead of OpenAI directly

Requirements:
    - uv add openai-agents
    - Docker running locally (docker ps should work)
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o

Usage:
    python 97_openai_runner_sandbox.py
    python 97_openai_runner_sandbox.py --question "List all files in the workspace."
    python 97_openai_runner_sandbox.py --model gpt-4o-mini
"""

from __future__ import annotations

import argparse
import asyncio

try:
    from agents import ModelSettings
    from agents.run import RunConfig
    from agents.sandbox import Manifest, SandboxAgent, SandboxRunConfig
    from agents.sandbox.config import DEFAULT_PYTHON_SANDBOX_IMAGE
    from agents.sandbox.entries import File
except ImportError:
    raise SystemExit(
        "openai-agents not installed.\n"
        "Install it with: uv add openai-agents"
    )

try:
    from docker import from_env as docker_from_env
    from agents.sandbox.sandboxes.docker import DockerSandboxClient, DockerSandboxClientOptions
except ImportError:
    raise SystemExit(
        "Docker SDK not installed or Docker is not running.\n"
        "Install it with: pip install docker\n"
        "Then make sure Docker is running: docker ps"
    )

# ── Only this line changes ──────────────────────────────────────────────────
# from agents import Runner          # ← original (runs directly on OpenAI)
from agentspan import Runner         # ← agentspan (runs on Agentspan)
# ───────────────────────────────────────────────────────────────────────────

DEFAULT_QUESTION = "Summarize this project in 2 sentences."
DEFAULT_MODEL = "gpt-4o"


def _build_manifest() -> Manifest:
    """Build a small demo workspace for the sandbox agent to inspect."""
    return Manifest(
        entries={
            "README.md": File(
                content=(
                    b"# Demo Project\n\n"
                    b"A tiny demo project for the Agentspan sandbox runner example.\n"
                    b"The model can inspect files through the shell tool.\n"
                )
            ),
            "src/app.py": File(
                content=b'def greet(name: str) -> str:\n    return f"Hello, {name}!"\n'
            ),
            "docs/notes.md": File(
                content=(
                    b"# Notes\n\n"
                    b"- Example is intentionally minimal.\n"
                    b"- Model should inspect files before answering.\n"
                )
            ),
        }
    )


def _build_agent(model: str, manifest: Manifest) -> SandboxAgent:
    """Build the sandbox agent with shell access to the workspace."""
    # WorkspaceShellCapability gives the model a shell tool to inspect files.
    # Import here to avoid failure if the sandbox extras aren't installed.
    try:
        from agents.sandbox.capabilities.workspace_shell import WorkspaceShellCapability
    except ImportError:
        # Older openai-agents versions may have a different import path
        try:
            from agents.sandbox import WorkspaceShellCapability  # type: ignore
        except ImportError:
            raise SystemExit(
                "WorkspaceShellCapability not found. "
                "Ensure openai-agents[docker] is installed."
            )

    return SandboxAgent(
        name="Sandbox Assistant",
        model=model,
        instructions=(
            "Answer questions about the sandbox workspace. "
            "Inspect the project files before answering. "
            "Keep responses concise."
        ),
        default_manifest=manifest,
        capabilities=[WorkspaceShellCapability()],
        model_settings=ModelSettings(tool_choice="required"),
    )


async def main(model: str, question: str) -> None:
    manifest = _build_manifest()
    agent = _build_agent(model, manifest)

    # Create Docker sandbox client and provision a container
    docker_client = DockerSandboxClient(docker_from_env())
    sandbox = await docker_client.create(
        manifest=manifest,
        options=DockerSandboxClientOptions(image=DEFAULT_PYTHON_SANDBOX_IMAGE),
    )

    await sandbox.start()
    print(f"Sandbox started. Workspace files: {await sandbox.ls('.')}\n")

    try:
        async with sandbox:
            # Run the agent — AgentspanRunner.run_streamed() is a drop-in for Runner.run_streamed()
            stream = await Runner.run_streamed(
                agent,
                question,
                run_config=RunConfig(
                    sandbox=SandboxRunConfig(session=sandbox),
                    workflow_name="Agentspan Docker sandbox example",
                ),
            )

            print("assistant> ", end="", flush=True)
            async for event in stream:
                if event.type in ("thinking", "message") and event.content:
                    print(event.content, end="", flush=True)
                elif event.type == "tool_call":
                    print(f"\n[tool] {event.tool_name}({event.args})")
                    print("tool> ", end="", flush=True)
                elif event.type == "tool_result":
                    print(event.result)
                    print("assistant> ", end="", flush=True)
                elif event.type == "done":
                    break

            result = await stream.get_result()
            print(f"\n\nExecution ID: {result.execution_id}")
            print("(View full run in the Agentspan UI)")
    finally:
        await docker_client.delete(sandbox)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agentspan sandbox agent (Docker)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="LLM model to use")
    parser.add_argument("--question", default=DEFAULT_QUESTION, help="Question to ask")
    args = parser.parse_args()
    asyncio.run(main(args.model, args.question))
