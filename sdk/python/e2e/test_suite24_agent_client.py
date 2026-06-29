"""Suite 24: AgentClient — control-plane run + schedule surface.

Verifies the control-plane :class:`AgentClient` (formerly ``AgentHttpClient``)
exposed via ``runtime.client``:

- ``run`` on an LLM-only agent (no local tools) reaches status COMPLETED.
  Control-plane only: no local tool workers are registered/polled.
- ``schedule(agent, [Schedule(...)])`` deploys + reconciles; the schedule then
  shows up in ``list_for_agent``. A counterfactual ``reconcile([])`` purges it.
- The runtime's schedule surface (``runtime.schedules_client()``) and the
  client's (``runtime.client.schedules``) are the *same* instance.

No LLM is used for validation — assertions are on workflow status / schedule
structure only (per CLAUDE.md rule 1). The scheduled "agent" target is a bare
no-op Conductor workflow so no LLM is invoked for the schedule tests.

Targets the live Agentspan server (``AGENTSPAN_SERVER_URL``). The schedule
tests are skipped automatically if the server's Conductor lacks the scheduler
module.
"""

from __future__ import annotations

import os
import uuid

import pytest
import requests

from conductor.ai.agents import Agent
from conductor.ai.agents.result import Status
from conductor.ai.agents.schedule import Schedule

pytestmark = [pytest.mark.e2e]

MODEL = os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o-mini")
_API = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api").rstrip("/")


def _scheduler_available() -> bool:
    try:
        r = requests.get(f"{_API}/scheduler/schedules", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


_SCHED_SKIP = pytest.mark.skipif(
    not _scheduler_available(),
    reason=f"Conductor scheduler not reachable at {_API}/scheduler/schedules",
)


# ── run: LLM-only agent via the control-plane client ─────────────────────


class TestControlPlaneRun:
    def test_run_llm_only_agent_completes(self, runtime, model):
        """AgentClient.run on a tool-less agent reaches COMPLETED — no workers."""
        agent = Agent(
            name=f"e2e_client_run_{uuid.uuid4().hex[:8]}",
            model=model,
            instructions="You are a calculator. Reply with only the number.",
        )

        result = runtime.client.run(agent, "What is 2 + 2? Reply with only the number.")

        assert result.status == Status.COMPLETED, (
            f"expected COMPLETED, got {result.status} (error={result.error})"
        )
        assert result.execution_id
        # No local tool workers were started for this control-plane run.
        assert runtime._workers_started is False

    def test_start_returns_handle_then_joins(self, runtime, model):
        """AgentClient.start returns a handle that joins to a COMPLETED result."""
        agent = Agent(
            name=f"e2e_client_start_{uuid.uuid4().hex[:8]}",
            model=model,
            instructions="Reply with the single word: ok",
        )

        handle = runtime.client.start(agent, "Say ok")
        assert handle.execution_id
        result = handle.join(timeout=120)
        assert result.status == Status.COMPLETED


# ── schedule: deploy + reconcile via the client's schedule surface ───────


@_SCHED_SKIP
class TestSchedule:
    @pytest.fixture()
    def noop_agent_name(self):
        """Register a no-op Conductor workflow to act as the schedule target."""
        name = f"e2e_client_sched_{uuid.uuid4().hex[:8]}"
        workflow_def = {
            "name": name,
            "version": 1,
            "description": "AgentClient schedule e2e no-op workflow",
            "ownerEmail": "e2e@agentspan.test",
            "schemaVersion": 2,
            "timeoutSeconds": 60,
            "timeoutPolicy": "TIME_OUT_WF",
            "tasks": [
                {
                    "name": "noop_terminate",
                    "taskReferenceName": "noop_terminate_ref",
                    "type": "TERMINATE",
                    "inputParameters": {
                        "terminationStatus": "COMPLETED",
                        "workflowOutput": {"ok": True},
                    },
                }
            ],
        }
        r = requests.post(f"{_API}/metadata/workflow", json=workflow_def, timeout=10)
        assert r.status_code in (200, 204), f"register wf failed: {r.status_code} {r.text}"
        yield name
        # teardown: purge schedules + unregister wf (best-effort)
        try:
            requests.delete(f"{_API}/metadata/workflow/{name}/1", timeout=5)
        except Exception:
            pass

    def test_schedule_then_list_then_purge(self, runtime, noop_agent_name):
        schedules = runtime.client.schedules

        # Clean slate.
        schedules.reconcile(noop_agent_name, [])
        assert schedules.list_for_agent(noop_agent_name) == []

        # Reconcile a single schedule via the client's schedule surface.
        schedules.reconcile(
            noop_agent_name,
            [Schedule(name="daily", cron="0 0 9 * * ?", input={"k": 1})],
        )
        infos = {i.short_name: i for i in schedules.list_for_agent(noop_agent_name)}
        assert set(infos) == {"daily"}
        assert infos["daily"].name == f"{noop_agent_name}-daily"
        assert infos["daily"].cron == "0 0 9 * * ?"

        # Counterfactual: reconcile with an empty list purges it.
        schedules.reconcile(noop_agent_name, [])
        assert schedules.list_for_agent(noop_agent_name) == []


# ── structural consistency: runtime + client share one schedule surface ──


class TestScheduleSurfaceConsistency:
    def test_runtime_and_client_share_schedule_client(self, runtime):
        """runtime.schedules_client() and runtime.client.schedules are identical."""
        from_runtime = runtime.schedules_client()
        from_client = runtime.client.schedules
        assert from_runtime is from_client

    def test_client_is_bound_to_runtime(self, runtime):
        """runtime.client is the runtime's own control-plane client (not a copy)."""
        assert runtime.client is runtime._http
