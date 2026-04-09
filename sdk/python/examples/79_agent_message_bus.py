# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Agent Message Bus — two agents communicating via Workflow Message Queue.

Demonstrates:
    - Agent-to-agent messaging: one running agent sending messages directly
      into another running agent's WMQ via runtime.send_message()
    - A tool that closes over an execution_id to forward results downstream
    - Parallel agent pipelines: researcher → writer running concurrently
    - Filesystem-based IPC: forward_to_writer and stop_pipeline write sentinel
      files so the main thread knows exactly when to send the stop signal —
      no fixed sleeps, no streaming
    - Stop signal propagation: the main script sends one stop to the Researcher,
      which forwards it to the Writer via stop_pipeline() before itself stopping;
      both workflows exit cleanly as COMPLETED (no tool calls on stop = DoWhile
      loop condition goes false naturally)

How this differs from 06_sequential_pipeline:
    The >> operator in example 06 compiles a static DAG upfront — the workflow
    is defined before execution starts and the runtime automatically passes the
    output of agent A as input to agent B.  Here, both agents are independent
    running workflows.  The Researcher decides at runtime when and what to
    forward, and could in theory send to multiple Writers or skip forwarding
    conditionally.  For the basic "A feeds B" pattern example 06 is simpler;
    use this pattern when you need dynamic, conditional, or fan-out routing
    between concurrently running agents.

Scenario:
    A Researcher agent receives topics, produces bullet-point research notes,
    then forwards them to a Writer agent that turns the notes into a polished
    paragraph.  The main script only sends topics to the Researcher — the
    Researcher autonomously drives the Writer.

Requirements:
    - Conductor server with WMQ support (conductor.workflow-message-queue.enabled=true)
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

import shutil
import tempfile
import time
from pathlib import Path

from agentspan.agents import Agent, AgentRuntime, tool, wait_for_message_tool
from settings import settings

# Shared directory for IPC between main process and worker processes.
# Workers run as separate OS processes (different PIDs, same filesystem).
_ipc_dir = Path(tempfile.mkdtemp(prefix="message_bus_"))
_FORWARDED_DIR = _ipc_dir / "forwarded"  # one file per forwarded topic
_FORWARDED_DIR.mkdir()

TOPICS = [
    "the impact of edge computing on cloud infrastructure",
    "why Rust is gaining adoption in systems programming",
    "how vector databases work",
]


def build_researcher(runtime: AgentRuntime, writer_execution_id: str) -> Agent:
    """Build the Researcher agent with a forward tool wired to the Writer's queue."""

    receive_topic = wait_for_message_tool(
        name="wait_for_topic",
        description="Wait for the next research topic or a stop signal ({stop: true}).",
    )

    @tool
    def forward_to_writer(topic: str, notes: str) -> str:
        """Forward research notes to the Writer and signal the main process."""
        print(f"  [researcher → writer] forwarding notes on {topic!r}")
        runtime.send_message(writer_execution_id, {"topic": topic, "notes": notes})
        (_FORWARDED_DIR / f"{time.time_ns()}.done").touch()
        return "forwarded"

    @tool
    def stop_pipeline() -> str:
        """Forward the stop signal to the Writer and signal the main process."""
        runtime.send_message(writer_execution_id, {"stop": True})
        return "done"

    return Agent(
        name="researcher",
        model=settings.llm_model,
        tools=[receive_topic, forward_to_writer, stop_pipeline],
        max_turns=10000,
        stateful=True,
        instructions=(
            "You are a Researcher agent. Repeat indefinitely:\n"
            "1. Call wait_for_topic to receive the next message.\n"
            "2. If the message contains 'stop: true', call stop_pipeline() then respond "
            "   with 'Stopping.' and call no further tools.\n"
            "3. Otherwise, write three concise bullet-point research notes on the topic "
            "   using your own knowledge.\n"
            "4. Call forward_to_writer(topic, notes) with the topic and your bullet points.\n"
            "5. Return to step 1 immediately."
        ),
    )


def build_writer() -> Agent:
    """Build the Writer agent that polishes research notes into paragraphs."""

    receive_notes = wait_for_message_tool(
        name="wait_for_notes",
        description=(
            "Wait for research notes from the Researcher agent. "
            "The payload contains 'topic' and 'notes' fields, or a stop signal ({stop: true})."
        ),
    )

    @tool
    def publish(topic: str, paragraph: str) -> str:
        """Publish the finished paragraph."""
        print(f"\n  [writer] ── {topic} ──")
        print(f"  {paragraph}\n")
        return "published"

    return Agent(
        name="writer",
        model=settings.llm_model,
        tools=[receive_notes, publish],
        max_turns=10000,
        stateful=True,
        instructions=(
            "You are a Writer agent. Repeat indefinitely:\n"
            "1. Call wait_for_notes to receive the next message.\n"
            "2. If the message contains 'stop: true', respond with 'Stopping.' and call "
            "   no further tools.\n"
            "3. Otherwise, turn the notes into a single polished paragraph (3–4 sentences).\n"
            "4. Call publish(topic, paragraph) with the topic and your paragraph.\n"
            "5. Return to step 1 immediately."
        ),
    )


try:
    with AgentRuntime() as runtime:
        # Start the Writer first so its execution_id is available to the Researcher
        writer_handle = runtime.start(build_writer(), "Begin. Wait for research notes.")
        writer_id = writer_handle.execution_id
        print(f"Writer  started: {writer_id}")

        researcher = build_researcher(runtime, writer_id)
        researcher_handle = runtime.start(researcher, "Begin. Wait for your first topic.")
        researcher_id = researcher_handle.execution_id
        print(f"Researcher started: {researcher_id}\n")

        time.sleep(4)
        print("Sending topics to Researcher...\n")
        for topic in TOPICS:
            print(f"  → {topic!r}")
            runtime.send_message(researcher_id, {"topic": topic})

        # Wait until all topics have been forwarded to the Writer
        while len(list(_FORWARDED_DIR.iterdir())) < len(TOPICS):
            time.sleep(0.1)

        # Send stop to Researcher — it calls stop_pipeline() to forward the stop to
        # the Writer, then responds with no further tool calls so both loops exit.
        runtime.send_message(researcher_id, {"stop": True})

        # Wait for both agents to reach terminal state before the runtime exits.
        researcher_handle.join(timeout=30)
        writer_handle.join(timeout=30)

        print("Done.")
finally:
    shutil.rmtree(_ipc_dir, ignore_errors=True)
