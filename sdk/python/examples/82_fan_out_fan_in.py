# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Fan-out / Fan-in — orchestrator broadcasts tasks to multiple worker agents,
then collects and aggregates all results.

Demonstrates:
    - Fan-out: one Orchestrator agent sending the same task to N Worker agents
      by calling runtime.send_message once per worker, all from a single @tool
    - Fan-in: each Worker sends its result into the Collector agent's WMQ so
      results arrive independently in any order
    - Three roles, five concurrently running workflows:
        Orchestrator — receives questions from main, fans them out
        Worker ×3    — receives a task, produces an answer, pushes to Collector
        Collector    — receives 3×N results, builds side-by-side reports
    - Unique tool names per worker: Conductor routes tasks by definition name,
      so workers sharing a name would race for each other's tasks.  Each worker
      gets tools named submit_answer_<name> / stop_collector_<name>.
    - Filesystem IPC:
        * Workers write sentinels after submit_answer so main counts completions
        * Collector writes reports to files; main thread reads and prints them
        * stop_* sentinels tell main all agents have cleanly shut down
    - No time.sleep() to assume message delivery — all synchronisation via files

Scenario:
    A research Orchestrator fans out each question to three Worker agents
    (alpha, beta, gamma) that produce independent short answers.  The Collector
    aggregates the three answers into a side-by-side comparison report.

Requirements:
    - Conductor server with WMQ support
    - AGENTSPAN_SERVER_URL=http://host.docker.internal:6767/api
    - AGENTSPAN_LLM_MODEL=anthropic/claude-sonnet-4-20250514
"""

import json
import shutil
import tempfile
import time
from pathlib import Path

from settings import settings

from agentspan.agents import Agent, AgentRuntime, tool, wait_for_message_tool

# ---------------------------------------------------------------------------
# Filesystem IPC
# ---------------------------------------------------------------------------

_ipc_dir = Path(tempfile.mkdtemp(prefix="fan_out_fan_in_"))
_ANSWERS_DIR = _ipc_dir / "answers"   # one sentinel per submitted answer
_REPORTS_DIR = _ipc_dir / "reports"  # one JSON file per aggregated report
_ANSWERS_DIR.mkdir()
_REPORTS_DIR.mkdir()

NUM_WORKERS = 3
WORKER_NAMES = ["alpha", "beta", "gamma"]

QUESTIONS = [
    "What are the main trade-offs between microservices and monolithic architectures?",
    "How does a transformer model differ from a recurrent neural network?",
    "What problem does consistent hashing solve in distributed systems?",
]


# ---------------------------------------------------------------------------
# Collector agent — fan-in
# ---------------------------------------------------------------------------

def build_collector() -> Agent:
    receive_result = wait_for_message_tool(
        name="receive_result",
        description=(
            "Wait for the next worker result. "
            "Payload: {question, worker_name, answer} or a stop signal {stop: true}."
        ),
    )

    @tool
    def save_report(question: str, report: str) -> str:
        """Write the aggregated side-by-side report to a file for the main thread to read."""
        safe = question[:40].replace(" ", "_").replace("?", "")
        (_REPORTS_DIR / f"{time.time_ns()}_{safe}.json").write_text(
            json.dumps({"question": question, "report": report})
        )
        return "saved"

    return Agent(
        name="collector_agent",
        model=settings.llm_model,
        tools=[receive_result, save_report],
        max_turns=10000,
        stateful=True,
        instructions=(
            f"You are a Collector agent. You receive individual worker answers and "
            f"aggregate them. There are always {NUM_WORKERS} workers "
            f"({', '.join(WORKER_NAMES)}) answering each question.\n\n"
            "Repeat indefinitely:\n"
            f"1. Call receive_result {NUM_WORKERS} times to collect all answers for "
            "   one question (they share the same 'question' field).\n"
            "2. If any result is a stop signal {stop: true}, respond with 'Stopping.' "
            "   and call no further tools.\n"
            "3. Build a side-by-side comparison: for each worker list their name and "
            "   a one-sentence summary of their answer.\n"
            "4. Call save_report(question, report) with the formatted report string.\n"
            "5. Return to step 1."
        ),
    )


# ---------------------------------------------------------------------------
# Worker agents — unique tool names per worker to avoid Conductor name collision
# ---------------------------------------------------------------------------

def build_worker(worker_name: str, runtime: AgentRuntime, collector_id: str) -> Agent:
    receive_task = wait_for_message_tool(
        name=f"receive_task_{worker_name}",
        description=(
            f"Wait for the next task for worker {worker_name}. "
            "Payload: {question} or a stop signal {stop: true}."
        ),
    )

    # Tool names must be unique across all workers so Conductor routes each
    # task to the correct worker process.
    @tool(name=f"submit_answer_{worker_name}")
    def submit_answer(question: str, answer: str) -> str:
        """Send this worker's answer to the Collector and write a completion sentinel."""
        runtime.send_message(collector_id, {
            "question": question,
            "worker_name": worker_name,
            "answer": answer,
        })
        (_ANSWERS_DIR / f"{worker_name}_{time.time_ns()}.done").touch()
        return "submitted"

    @tool(name=f"stop_collector_{worker_name}")
    def stop_collector() -> str:
        """Forward the stop signal to the Collector and write a shutdown sentinel."""
        runtime.send_message(collector_id, {"stop": True})
        return "stop forwarded"

    return Agent(
        name=f"worker_{worker_name}",
        model=settings.llm_model,
        tools=[receive_task, submit_answer, stop_collector],
        max_turns=10000,
        stateful=True,
        instructions=(
            f"You are Worker {worker_name.upper()}, one of {NUM_WORKERS} parallel analysts. "
            "Repeat indefinitely:\n"
            f"1. Call receive_task_{worker_name} to get the next assignment.\n"
            "2. If the payload contains 'stop: true', call "
            f"   stop_collector_{worker_name}() then respond with 'Stopping.' "
            "   and call no further tools.\n"
            "3. Otherwise write a concise 2–3 sentence answer to the question.\n"
            f"4. Call submit_answer_{worker_name}(question, answer).\n"
            "5. Return to step 1 immediately."
        ),
    )


# ---------------------------------------------------------------------------
# Orchestrator agent
# ---------------------------------------------------------------------------

def build_orchestrator(runtime: AgentRuntime, worker_ids: list) -> Agent:
    receive_question = wait_for_message_tool(
        name="receive_question",
        description="Wait for the next question to fan out, or a stop signal {stop: true}.",
    )

    @tool
    def fan_out(question: str) -> str:
        """Broadcast the question to all worker agents simultaneously."""
        for wid in worker_ids:
            runtime.send_message(wid, {"question": question})
        return f"broadcasted to {len(worker_ids)} workers"

    @tool
    def stop_all_workers() -> str:
        """Send stop signals to all workers and write a shutdown sentinel."""
        for wid in worker_ids:
            runtime.send_message(wid, {"stop": True})
        return "stop sent to all workers"

    return Agent(
        name="orchestrator_agent",
        model=settings.llm_model,
        tools=[receive_question, fan_out, stop_all_workers],
        max_turns=10000,
        stateful=True,
        instructions=(
            "You are an Orchestrator agent. Repeat indefinitely:\n"
            "1. Call receive_question to get the next question or stop signal.\n"
            "2. If the payload contains 'stop: true', call stop_all_workers() then "
            "   respond with 'Stopping.' and call no further tools.\n"
            "3. Otherwise call fan_out(question) to broadcast to all workers.\n"
            "4. Return to step 1 immediately."
        ),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

total_answers = len(QUESTIONS) * NUM_WORKERS

try:
    with AgentRuntime() as runtime:
        # Start Collector first — workers need its ID.
        collector_handle = runtime.start(build_collector(), "Begin. Wait for worker results.")
        collector_id = collector_handle.execution_id
        print(f"Collector    started: {collector_id}")

        # Start Workers — Orchestrator needs their IDs.
        worker_ids: list = []
        worker_handles: list = []
        for name in WORKER_NAMES:
            wh = runtime.start(
                build_worker(name, runtime, collector_id),
                f"Begin. You are worker {name.upper()}. Wait for tasks.",
            )
            worker_ids.append(wh.execution_id)
            worker_handles.append(wh)
            print(f"Worker {name:5s}  started: {wh.execution_id}")

        # Start Orchestrator last.
        orch_handle = runtime.start(
            build_orchestrator(runtime, worker_ids),
            "Begin. Wait for questions to fan out.",
        )
        orchestrator_id = orch_handle.execution_id
        print(f"Orchestrator started: {orchestrator_id}\n")

        # Give all agents time to reach their first wait call.
        time.sleep(5)

        print(f"Fanning out {len(QUESTIONS)} question(s) to {NUM_WORKERS} workers each "
              f"({total_answers} total answers expected)...\n")
        for q in QUESTIONS:
            print(f"  → {q[:70]}")
            runtime.send_message(orchestrator_id, {"question": q})

        # Tail answers as they arrive.
        print(f"\nWaiting for {total_answers} answers and {len(QUESTIONS)} reports...\n")
        seen_answers: set = set()
        seen_reports: set = set()

        while len(seen_reports) < len(QUESTIONS):
            # Print new answer sentinels.
            for p in sorted(_ANSWERS_DIR.iterdir()):
                if p.name not in seen_answers:
                    worker = p.name.split("_")[0]
                    print(f"  [answer received] worker:{worker}")
                    seen_answers.add(p.name)

            # Print new reports as they appear.
            for p in sorted(_REPORTS_DIR.iterdir()):
                if p.name not in seen_reports:
                    data = json.loads(p.read_text())
                    print(f"\n  ── {data['question'][:60]}… ──")
                    print(f"  {data['report']}\n")
                    seen_reports.add(p.name)

            time.sleep(0.1)

        print(f"All {len(QUESTIONS)} reports received. Shutting down...\n")

        # Shutdown: Orchestrator → Workers → Collector (via stop_collector_<name>).
        runtime.send_message(orchestrator_id, {"stop": True})

        # Wait for all agents to reach terminal state before the runtime exits.
        orch_handle.join(timeout=60)
        for wh in worker_handles:
            wh.join(timeout=30)
        collector_handle.join(timeout=30)

        print("Done.")
finally:
    shutil.rmtree(_ipc_dir, ignore_errors=True)
