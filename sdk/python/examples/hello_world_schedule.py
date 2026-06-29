"""Hello-world scheduling demo.

Schedules a "Hello, world!" workflow every 2 seconds via the agentspan SDK,
waits, then prints the execution history.

The "agent" here is a Conductor workflow with a single INLINE task that
emits ``{"greeting": "Hello, world!", "timestamp": ...}``. Using a workflow
instead of a real LLM Agent keeps the demo deterministic and free — the
scheduling pipeline is identical either way.

NOTE: Targets OSS Conductor at port 8089. The agentspan-runtime on port
6767 doesn't (yet) include the scheduler module — see
``docs/design/plans/2026-05-27-agent-scheduling.md`` open dependency #1.

Run::

    uv run python examples/hello_world_schedule.py
"""

from __future__ import annotations

import time
import uuid

import requests
from conductor.client.configuration.configuration import Configuration
from conductor.client.orkes_clients import OrkesClients

from conductor.ai.agents.schedule import Schedule
from conductor.ai.agents.schedule.client import ScheduleClient

CONDUCTOR_API = "http://localhost:6767/api"


def register_hello_world_workflow(name: str) -> None:
    """Register a no-LLM workflow that emits a hello-world greeting."""
    workflow_def = {
        "name": name,
        "version": 1,
        "description": "Hello-world demo for agent scheduling",
        "ownerEmail": "demo@agentspan.test",
        "schemaVersion": 2,
        "timeoutSeconds": 30,
        "timeoutPolicy": "TIME_OUT_WF",
        "tasks": [
            {
                "name": "say_hello",
                "taskReferenceName": "say_hello_ref",
                "type": "INLINE",
                "inputParameters": {
                    "evaluatorType": "javascript",
                    "expression": (
                        "function e(){return {greeting:'Hello, world!',"
                        "firedAt:new Date().toISOString()};} e();"
                    ),
                },
            }
        ],
        "outputParameters": {
            "greeting": "${say_hello_ref.output.result.greeting}",
            "firedAt": "${say_hello_ref.output.result.firedAt}",
        },
    }
    r = requests.post(f"{CONDUCTOR_API}/metadata/workflow", json=workflow_def, timeout=10)
    r.raise_for_status()
    print(f"✓ Registered workflow '{name}'")


def fetch_executions(agent: str, limit: int = 20) -> list[dict]:
    """Query Conductor for recent executions of the given workflow.

    /workflow/search returns summaries without ``output``; fetch each
    workflow by id for the full record.
    """
    r = requests.get(
        f"{CONDUCTOR_API}/workflow/search",
        params={"query": f"workflowType='{agent}'", "sort": "startTime:DESC", "size": limit},
        timeout=10,
    )
    r.raise_for_status()
    summaries = r.json().get("results", [])

    out = []
    for s in summaries:
        wf_id = s.get("workflowId")
        if not wf_id:
            continue
        try:
            full = requests.get(f"{CONDUCTOR_API}/workflow/{wf_id}", timeout=5).json()
            out.append(
                {
                    "workflowId": wf_id,
                    "status": full.get("status"),
                    "startTime": s.get("startTime"),
                    "output": full.get("output", {}),
                }
            )
        except Exception:
            out.append(s)
    return out


def main() -> None:
    import os
    cleanup = os.environ.get("CLEANUP", "1") != "0"
    agent_name = f"hello_world_{uuid.uuid4().hex[:6]}"

    # 1. Register the workflow that the schedule will fire.
    register_hello_world_workflow(agent_name)

    # 2. Build the agentspan ScheduleClient against the scheduler-enabled
    #    Conductor instance.
    clients = OrkesClients(configuration=Configuration(base_url="http://localhost:6767"))
    sched_client = ScheduleClient(
        clients.get_scheduler_client(), clients.get_workflow_client()
    )

    # 3. Declarative deploy: one schedule, fires every 2 seconds.
    #    Quartz 6-field cron: 'sec min hour day month day-of-week'.
    sched_client.reconcile(
        agent_name,
        [Schedule(name="every-2s", cron="0/2 * * * * ?", description="demo cadence")],
    )
    print(f"✓ Scheduled '{agent_name}-every-2s' every 2 seconds")

    # 4. Wait for the scheduler to fire it a few times.
    wait_seconds = 12
    print(f"⏳ Waiting {wait_seconds}s for the scheduler to fire executions...")
    time.sleep(wait_seconds)

    # 5. Show what fired.
    execs = fetch_executions(agent_name, limit=10)
    print(f"\n📋 Executions ({len(execs)}):")
    print("-" * 78)
    print(f"{'#':>3}  {'startTime':<24}  {'status':<10}  output")
    print("-" * 78)
    for i, e in enumerate(execs, 1):
        ts_raw = e.get("startTime", "")
        if isinstance(ts_raw, (int, float)) and ts_raw:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts_raw / 1000))
        else:
            ts = str(ts_raw)[:23] if ts_raw else "?"
        status = e.get("status", "?")
        out = e.get("output", {})
        if not isinstance(out, dict):
            out = {}
        greeting = out.get("greeting", "")
        fired = out.get("firedAt", "")
        print(f"{i:>3}  {ts:<24}  {status:<10}  {greeting!r} @ {fired}")
    print("-" * 78)

    # 6. Cleanup unless CLEANUP=0.
    if cleanup:
        sched_client.reconcile(agent_name, [])
        requests.delete(f"{CONDUCTOR_API}/metadata/workflow/{agent_name}/1", timeout=5)
        print(f"\n✓ Cleaned up schedule and workflow '{agent_name}'")
    else:
        print(f"\n⏸  Skipping cleanup. Schedule and workflow '{agent_name}' remain active.")
        print("    Re-run with CLEANUP=1 (default) or delete manually via the UI.")


if __name__ == "__main__":
    main()
