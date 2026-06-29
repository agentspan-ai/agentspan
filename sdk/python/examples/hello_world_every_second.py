"""A bare LLM agent (no tools) scheduled to fire every second.

Builds an Agent that just emits "Hello, world!" via the LLM, deploys it,
schedules it on a 1s cadence, lets it run for 15s, and prints the execution
log. Leaves the schedule live unless CLEANUP=1.

Run::

    OPENAI_API_KEY=... uv run python examples/hello_world_every_second.py
"""

from __future__ import annotations

import os
import time
import uuid

import requests

from conductor.ai.agents import Agent, AgentRuntime
from conductor.ai.agents.schedule import Schedule

SERVER = "http://localhost:6767/api"
MODEL = os.environ.get("AGENTSPAN_MODEL", "anthropic/claude-sonnet-4-6")


def fetch_executions(agent_name: str, limit: int = 30) -> list[dict]:
    r = requests.get(
        f"{SERVER}/workflow/search",
        params={
            "query": f"workflowType='{agent_name}'",
            "sort": "startTime:DESC",
            "size": limit,
        },
        timeout=10,
    )
    r.raise_for_status()
    summaries = r.json().get("results", [])
    out = []
    for s in summaries:
        wf_id = s.get("workflowId")
        if not wf_id:
            continue
        full = requests.get(f"{SERVER}/workflow/{wf_id}", timeout=5).json()
        out.append(
            {
                "id": wf_id,
                "status": full.get("status"),
                "startTime": s.get("startTime"),
                "output": full.get("output", {}),
            }
        )
    return out


def main() -> None:
    agent_name = f"hello_every_second_{uuid.uuid4().hex[:6]}"

    # Bare agent: name, model, instructions. No tools.
    agent = Agent(
        name=agent_name,
        model=MODEL,
        instructions=(
            "When asked, respond with exactly the string: Hello, world! "
            "Nothing else."
        ),
    )

    with AgentRuntime(server_url=SERVER) as rt:
        rt.deploy(
            agent,
            schedules=[
                Schedule(
                    name="every-1s",
                    cron="* * * * * ?",          # every second
                    input={"prompt": "Say hi."},
                    description="hello world every second",
                )
            ],
        )
        print(f"✓ Deployed agent '{agent_name}' (no tools)")
        print(f"✓ Scheduled '{agent_name}-every-1s' (every 1 second)")

        # Workers must poll so the LLM tasks execute.
        rt.serve(agent, blocking=False)

        wait_seconds = 15
        print(f"⏳ Waiting {wait_seconds}s for the scheduler to fire executions...")
        time.sleep(wait_seconds)

        execs = fetch_executions(agent_name, limit=25)
        completed = [e for e in execs if e.get("status") == "COMPLETED"]
        running = [e for e in execs if e.get("status") == "RUNNING"]
        print(
            f"\n📋 Executions: {len(execs)} total · {len(completed)} COMPLETED · {len(running)} RUNNING"
        )
        print("-" * 90)
        print(f"{'#':>3}  {'startTime':<24}  {'status':<10}  output")
        print("-" * 90)
        for i, e in enumerate(execs, 1):
            ts = (e.get("startTime") or "?")[:23]
            status = e.get("status", "?")
            out = e.get("output", {})
            if not isinstance(out, dict):
                out = {}
            result = out.get("result") or out.get("output") or out
            if isinstance(result, dict):
                result = result.get("message") or result.get("content") or result
            text = str(result)
            if len(text) > 60:
                text = text[:57] + "..."
            print(f"{i:>3}  {ts:<24}  {status:<10}  {text}")
        print("-" * 90)

        cleanup = os.environ.get("CLEANUP", "0") != "0"
        if cleanup:
            rt.schedules_client().reconcile(agent_name, [])
            requests.delete(f"{SERVER}/metadata/workflow/{agent_name}/1", timeout=5)
            print(f"\n✓ Cleaned up schedule and workflow '{agent_name}'")
        else:
            print(f"\n⏸  Schedule kept active for UI inspection: {agent_name}")
            print(f"    Sidebar → Definitions → Schedules, or")
            print(f"    http://localhost:6767/scheduleDef?workflowName={agent_name}")


if __name__ == "__main__":
    main()
