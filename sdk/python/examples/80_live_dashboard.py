# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Live Dashboard — a Feeder agent streams metrics into a Monitor agent in real time.

This example shows how WMQ can be used as a live data channel between two
concurrently running agents.  The Feeder pushes metric samples as fast as it
can; the Monitor consumes them in batches and prints an aggregated dashboard
line after each batch.  Neither agent knows at compile time how many messages
will arrive or when — the LLM reacts to whatever shows up in its queue.

Key WMQ concept — batch_size:
    wait_for_message_tool accepts a batch_size parameter.  Instead of waking
    up for every individual message, the Monitor dequeues up to 10 samples per
    call and processes them together.  This is useful when messages arrive in
    bursts and you want the LLM to reason over a window rather than one item
    at a time.

How it works:
    1. Monitor starts first; its execution_id is shared with the Feeder via a
       file (workers run as separate OS processes, so in-process objects are not
       shared — the filesystem is the coordination channel).
    2. The main script sends batch signals to the Feeder via WMQ.
    3. The Feeder dequeues each signal, generates 5 random metric samples
       (cpu, memory, request-rate, latency, error-rate), and pushes them
       directly into the Monitor's WMQ queue via runtime.send_message().
    4. The Monitor wakes up, pulls up to 10 samples at once, computes
       min/max/avg per metric, and calls display_dashboard with a summary line.
    5. Once all batches are confirmed dispatched and all dashboard summaries
       received, the main script sends a stop signal to the Feeder, which
       forwards it to the Monitor before itself stopping cleanly.

How this differs from 79_agent_message_bus:
    Example 79 has the Researcher forward structured content (research notes)
    to the Writer one item at a time.  Here, the Feeder pushes raw numeric
    samples as fast as possible and the Monitor aggregates them in batches —
    the pattern is closer to a metrics pipeline or log aggregator than a
    content pipeline.

Requirements:
    - Conductor server with WMQ support (conductor.workflow-message-queue.enabled=true)
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=anthropic/claude-sonnet-4-20250514 as environment variable
"""

import json
import math
import random
import shutil
import tempfile
import time
from pathlib import Path

from settings import settings

from agentspan.agents import Agent, AgentRuntime, tool, wait_for_message_tool

# Filesystem IPC between main process and worker processes (separate OS PIDs).
_ipc_dir = Path(tempfile.mkdtemp(prefix="live_dashboard_"))
_BATCH_DIR = _ipc_dir / "batches"    # one file per batch dispatched by Feeder
_DISPLAY_DIR = _ipc_dir / "displays" # one file per display_dashboard call by Monitor
_BATCH_DIR.mkdir()
_DISPLAY_DIR.mkdir()
_MONITOR_ID_FILE = _ipc_dir / "monitor_id.txt"  # written by main, read by Feeder tool


# ---------------------------------------------------------------------------
# Monitor agent
# ---------------------------------------------------------------------------

def build_monitor() -> Agent:
    """Monitor: pulls up to 10 metrics per call and prints aggregated stats."""

    receive_batch = wait_for_message_tool(
        name="receive_metrics",
        description=(
            "Dequeue the next batch of up to 10 metric samples. "
            "Each sample has 'metric', 'host', and 'value' fields. "
            "A stop signal looks like {stop: true}."
        ),
        batch_size=10,
    )

    @tool
    def display_dashboard(summary: str) -> str:
        """Publish an aggregated dashboard line for this batch.

        Writes the summary to a file in _DISPLAY_DIR so the main process can
        read and print it.  The file name encodes arrival order via time_ns.
        """
        ts = time.time_ns()
        (_DISPLAY_DIR / f"{ts}.txt").write_text(summary)
        return "displayed"

    return Agent(
        name="monitor_agent",
        model=settings.llm_model,
        tools=[receive_batch, display_dashboard],
        max_turns=10000,
        stateful=True,
        instructions=(
            "You are a real-time metrics monitor. Repeat indefinitely:\n"
            "1. Call receive_metrics — you will get a batch of 1–10 metric samples.\n"
            "2. If any sample contains 'stop: true' (or the batch itself is a stop signal), "
            "   respond with 'Shutting down.' and call no further tools.\n"
            "3. Otherwise, compute per-metric statistics across the batch:\n"
            "   - Count of samples per metric name\n"
            "   - Min, max, and average value\n"
            "4. Call display_dashboard with a compact one-line summary string like:\n"
            "   'Batch 3 | cpu_pct: n=4 min=12.1 max=87.3 avg=45.2 | mem_mb: n=3 …'\n"
            "5. Return to step 1 immediately."
        ),
    )


# ---------------------------------------------------------------------------
# Feeder agent
# ---------------------------------------------------------------------------

def build_feeder(runtime: AgentRuntime) -> Agent:
    """Feeder: generates metric samples and pushes them into the Monitor's queue."""

    receive_signal = wait_for_message_tool(
        name="receive_signal",
        description="Wait for a control signal from the orchestrator ({batches: N} or {stop: true}).",
    )

    @tool
    def push_metrics_batch(batch_number: int) -> str:
        """Generate and push one batch of metric samples to the Monitor agent.

        Reads the Monitor's execution ID from a shared file and sends 5 metric
        samples directly into its WMQ.  Writes a sentinel file so the main
        process knows the batch was dispatched.
        """
        monitor_id = _MONITOR_ID_FILE.read_text().strip()
        metrics = [
            "cpu_pct",
            "mem_mb",
            "req_rate",
            "latency_ms",
            "error_rate",
        ]
        samples = []
        for _ in range(5):
            metric = random.choice(metrics)
            host = random.choice(["web-01", "web-02", "db-01"])
            value = round(random.uniform(0, 100), 2)
            sample = {"metric": metric, "host": host, "value": value}
            samples.append(sample)
            runtime.send_message(monitor_id, sample)

        (_BATCH_DIR / f"batch_{batch_number}_{time.time_ns()}.done").touch()
        return f"Pushed {len(samples)} samples in batch {batch_number}: {json.dumps(samples)}"

    @tool
    def stop_monitor() -> str:
        """Send the stop signal to the Monitor agent and notify the main process."""
        monitor_id = _MONITOR_ID_FILE.read_text().strip()
        runtime.send_message(monitor_id, {"stop": True})
        return "stop sent"

    return Agent(
        name="feeder_agent",
        model=settings.llm_model,
        tools=[receive_signal, push_metrics_batch, stop_monitor],
        max_turns=10000,
        stateful=True,
        instructions=(
            "You are a metrics Feeder agent. Repeat indefinitely:\n"
            "1. Call receive_signal to get the next instruction.\n"
            "2. If the signal contains 'stop: true', call stop_monitor() then respond "
            "   with 'Stopping.' and call no further tools.\n"
            "3. If the signal contains 'batches: N', call push_metrics_batch N times "
            "   (once per batch, incrementing batch_number from 1 to N).\n"
            "4. Return to step 1 immediately."
        ),
    )


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

TOTAL_BATCHES = 6        # total metric batches to push (5 samples each → 30 metrics)
SAMPLES_PER_BATCH = 5   # push_metrics_batch sends this many samples each call
MONITOR_BATCH_SIZE = 10 # wait_for_message_tool batch_size for Monitor
# How many display_dashboard calls to expect before sending stop:
EXPECTED_DISPLAYS = math.ceil(TOTAL_BATCHES * SAMPLES_PER_BATCH / MONITOR_BATCH_SIZE)

try:
    with AgentRuntime() as runtime:
        # Start Monitor first so its execution_id exists before Feeder needs it.
        monitor_handle = runtime.start(build_monitor(), "Begin. Wait for metric batches.")
        monitor_id = monitor_handle.execution_id
        _MONITOR_ID_FILE.write_text(monitor_id)
        print(f"Monitor  started: {monitor_id}")

        feeder_handle = runtime.start(build_feeder(runtime), "Begin. Wait for orchestrator signals.")
        feeder_id = feeder_handle.execution_id
        print(f"Feeder   started: {feeder_id}\n")

        # Give agents time to reach their first wait_for_message call.
        time.sleep(4)

        print(f"Sending {TOTAL_BATCHES} batch signals to Feeder (5 metrics each = "
              f"{TOTAL_BATCHES * 5} total samples, Monitor reads ≤10 per call)...\n")

        # Send batch signals two at a time to let the Feeder bundle them.
        runtime.send_message(feeder_id, {"batches": TOTAL_BATCHES // 2})
        runtime.send_message(feeder_id, {"batches": TOTAL_BATCHES - TOTAL_BATCHES // 2})

        # Wait until all batches have been dispatched via push_metrics_batch.
        print("Waiting for all batches to be dispatched...")
        while len(list(_BATCH_DIR.iterdir())) < TOTAL_BATCHES:
            time.sleep(0.1)
        print(f"  All {TOTAL_BATCHES} batches dispatched ({TOTAL_BATCHES * SAMPLES_PER_BATCH} samples in Monitor's queue).\n")

        # Tail _DISPLAY_DIR: print summaries as they arrive, wait until all done.
        # Without this barrier, AgentRuntime.__exit__ kills the display_dashboard
        # worker while Monitor's LLM is still pulling batches from the queue.
        print(f"Live dashboard (Monitor processes ≤{MONITOR_BATCH_SIZE} samples per batch):\n")
        seen: set[str] = set()
        batch_index = 0
        while len(seen) < EXPECTED_DISPLAYS:
            for p in sorted(_DISPLAY_DIR.iterdir()):
                if p.name not in seen and p.suffix == ".txt":
                    batch_index += 1
                    print(f"  [dashboard batch {batch_index}] {p.read_text()}")
                    seen.add(p.name)
            time.sleep(0.05)

        print(f"\nAll {EXPECTED_DISPLAYS} batch reports received. Sending stop signal...\n")
        runtime.send_message(feeder_id, {"stop": True})

        # Wait for both agents to reach terminal state before the runtime exits.
        feeder_handle.join(timeout=30)
        monitor_handle.join(timeout=30)

        print("Done.")
finally:
    shutil.rmtree(_ipc_dir, ignore_errors=True)
