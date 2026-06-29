"""Real-agent scheduling demo.

A genuine ``Agent(...)`` — LLM-backed — deployed via the agentspan SDK and
attached to a cron schedule in one call. Watches the agentspan-runtime fire
the agent on a cadence and shows execution history with the LLM output.

Requires:
  - agentspan-runtime running on port 6767 with the scheduler module
    (see docs/design/plans/2026-05-27-agent-scheduling.md task 6)
  - An OPENAI_API_KEY (or change the model)

Run::

    OPENAI_API_KEY=... uv run python examples/hello_world_agent_schedule.py
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


def fetch_executions(agent_name: str, limit: int = 20) -> list[dict]:
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
    agent_name = f"hello_agent_{uuid.uuid4().hex[:6]}"

    # 1. Define a real LLM agent.
    agent = Agent(
        name=agent_name,
        model=MODEL,
        instructions=(
            "You are a friendly greeter. When asked, reply with exactly: "
            "'Hello, world! It is currently <ISO-8601 UTC timestamp>.' Replace "
            "<ISO-8601 UTC timestamp> with the current UTC time you compute. "
            "Nothing else."
        ),
    )

    # 2. Deploy and attach a 5-second schedule in one call.
    #    (Conductor uses 6-field Quartz cron with optional seconds.)
    with AgentRuntime(server_url=SERVER) as rt:
        rt.deploy(
            agent,
            schedules=[
                Schedule(
                    name="every-5s",
                    cron="0/5 * * * * ?",
                    input={"prompt": "Greet me."},
                    description="real-agent demo cadence",
                )
            ],
        )
        print(f"✓ Deployed agent '{agent_name}'")
        print(f"✓ Scheduled '{agent_name}-every-5s' (every 5 seconds)")

        # 3. Workers must poll for the LLM tasks to execute. serve() registers
        #    and starts them; blocking=False returns immediately.
        rt.serve(agent, blocking=False)

        # 4. Wait for a handful of fires.
        wait_seconds = 20
        print(f"⏳ Waiting {wait_seconds}s for the scheduler to fire executions...")
        time.sleep(wait_seconds)

        # 5. Show execution history.
        execs = fetch_executions(agent_name, limit=10)
        print(f"\n📋 Executions ({len(execs)}):")
        print("-" * 86)
        print(f"{'#':>3}  {'startTime':<24}  {'status':<10}  output")
        print("-" * 86)
        for i, e in enumerate(execs, 1):
            ts = (e.get("startTime") or "?")[:23]
            status = e.get("status", "?")
            out = e.get("output", {}) or {}
            # Agent execution output is typically under "result" or top-level
            # depending on the agent compile shape; print compactly.
            result = out.get("result") or out.get("output") or out
            if isinstance(result, dict):
                # Pull out the LLM message if present
                result = result.get("message") or result.get("content") or result
            text = str(result)
            if len(text) > 60:
                text = text[:57] + "..."
            print(f"{i:>3}  {ts:<24}  {status:<10}  {text}")
        print("-" * 86)

        cleanup = os.environ.get("CLEANUP", "1") != "0"
        if cleanup:
            rt.schedules_client().reconcile(agent_name, [])
            requests.delete(f"{SERVER}/metadata/workflow/{agent_name}/1", timeout=5)
            print(f"\n✓ Cleaned up schedule and workflow '{agent_name}'")
        else:
            print(f"\n⏸  Skipping cleanup. Agent '{agent_name}' still scheduled.")
            print(f"    UI: http://localhost:6767/scheduler/edit/{agent_name}-every-5s")


if __name__ == "__main__":
    main()
