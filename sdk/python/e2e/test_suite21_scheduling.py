"""Suite 21: Agent Scheduling — verify SDK ↔ Conductor scheduler wire layer.

Covers the Python SDK's schedule lifecycle against a live Conductor:
- Schedule reconciliation: deploy [A,B] then [A,C] prunes B, upserts C
- Tri-state semantics: None preserves, [] purges, [...] replaces
- pause/resume/delete lifecycle
- get/list mapping (wire name + short_name + agent)
- preview_next returns N fire times
- run_now returns execution id immediately
- duplicate-name detection raises before any wire call

Targets the scheduler-capable Conductor at ``SCHEDULER_CONDUCTOR_URL``
(default ``http://localhost:8089/api``). Skipped automatically if the
scheduler endpoint isn't available — this is the agentspan-runtime case
where the embedded Conductor lacks the scheduler module.

No LLM calls — the scheduled "agent" is a bare no-op Conductor workflow.
Per CLAUDE.md rule 1: never use an LLM for validation.
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Iterator

import pytest
import requests

from conductor.ai.agents.schedule import (
    Schedule,
    ScheduleNameConflict,
    ScheduleNotFound,
)
from conductor.ai.agents.schedule.client import ScheduleClient

pytestmark = [pytest.mark.e2e]


SCHEDULER_CONDUCTOR_URL = os.environ.get("SCHEDULER_CONDUCTOR_URL", "http://localhost:8089/api")


def _scheduler_available(base_url: str) -> bool:
    try:
        r = requests.get(f"{base_url.rstrip('/')}/scheduler/schedules", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


pytestmark.append(
    pytest.mark.skipif(
        not _scheduler_available(SCHEDULER_CONDUCTOR_URL),
        reason=(
            f"Conductor scheduler not reachable at {SCHEDULER_CONDUCTOR_URL}. "
            "Set SCHEDULER_CONDUCTOR_URL to a scheduler-enabled Conductor (e.g. "
            "OSS Conductor on port 8089) to run this suite."
        ),
    )
)


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def conductor_clients():
    """Conductor clients pointed at the scheduler-capable instance."""
    from conductor.client.configuration.configuration import Configuration
    from conductor.client.orkes_clients import OrkesClients

    # Configuration.base_url drops the /api suffix internally.
    base = SCHEDULER_CONDUCTOR_URL.rstrip("/").removesuffix("/api")
    cfg = Configuration(base_url=base)
    return OrkesClients(configuration=cfg)


@pytest.fixture(scope="module")
def agent_name(conductor_clients) -> Iterator[str]:
    """Register a no-op workflow def to act as the 'agent' and tear it down."""
    name = f"e2e_sched_noop_{uuid.uuid4().hex[:8]}"

    workflow_def = {
        "name": name,
        "version": 1,
        "description": "Scheduling e2e no-op workflow",
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

    base = SCHEDULER_CONDUCTOR_URL.rstrip("/")
    r = requests.post(f"{base}/metadata/workflow", json=workflow_def, timeout=10)
    assert r.status_code in (200, 204), f"Failed to register workflow: {r.status_code} {r.text}"

    yield name

    # Best-effort teardown: drop schedules for this agent, then unregister wf.
    sc = conductor_clients.get_scheduler_client()
    try:
        for s in sc.get_all_schedules(workflow_name=name) or []:
            try:
                sc.delete_schedule(s.name)
            except Exception:
                pass
    except Exception:
        pass
    try:
        requests.delete(f"{base}/metadata/workflow/{name}/1", timeout=5)
    except Exception:
        pass


@pytest.fixture()
def schedule_client(conductor_clients) -> ScheduleClient:
    return ScheduleClient(
        conductor_clients.get_scheduler_client(),
        conductor_clients.get_workflow_client(),
    )


@pytest.fixture(autouse=True)
def clean_schedules(schedule_client: ScheduleClient, agent_name: str):
    """Purge any leftover schedules for this agent before each test."""
    schedule_client.reconcile(agent_name, [])
    yield
    schedule_client.reconcile(agent_name, [])


# ── Tests ───────────────────────────────────────────────────────────────


class TestDeployReconcile:
    def test_creates_schedules(self, schedule_client, agent_name):
        schedule_client.reconcile(
            agent_name,
            [
                Schedule(name="daily", cron="0 0 9 * * ?", input={"k": 1}),
                Schedule(name="weekly", cron="0 0 9 * * MON"),
            ],
        )
        infos = schedule_client.list_for_agent(agent_name)
        by_short = {i.short_name: i for i in infos}
        assert set(by_short) == {"daily", "weekly"}
        assert by_short["daily"].name == f"{agent_name}-daily"
        assert by_short["daily"].cron == "0 0 9 * * ?"
        assert by_short["daily"].input == {"k": 1}
        assert by_short["daily"].agent == agent_name

    def test_upsert_and_prune(self, schedule_client, agent_name):
        schedule_client.reconcile(
            agent_name,
            [
                Schedule(name="a", cron="0 0 1 * * ?"),
                Schedule(name="b", cron="0 0 2 * * ?"),
            ],
        )
        # Redeploy: keep 'a' with new cron, add 'c', drop 'b'.
        schedule_client.reconcile(
            agent_name,
            [
                Schedule(name="a", cron="0 0 9 * * ?"),
                Schedule(name="c", cron="0 0 17 * * ?"),
            ],
        )
        infos = {i.short_name: i for i in schedule_client.list_for_agent(agent_name)}
        assert set(infos) == {"a", "c"}
        assert infos["a"].cron == "0 0 9 * * ?"

    def test_empty_list_purges(self, schedule_client, agent_name):
        schedule_client.reconcile(agent_name, [Schedule(name="x", cron="0 * * * * ?")])
        assert len(schedule_client.list_for_agent(agent_name)) == 1
        schedule_client.reconcile(agent_name, [])
        assert schedule_client.list_for_agent(agent_name) == []

    def test_none_preserves(self, schedule_client, agent_name):
        schedule_client.reconcile(agent_name, [Schedule(name="x", cron="0 * * * * ?")])
        schedule_client.reconcile(agent_name, None)
        infos = schedule_client.list_for_agent(agent_name)
        assert [i.short_name for i in infos] == ["x"]

    def test_duplicate_name_raises_before_io(self, schedule_client, agent_name):
        with pytest.raises(ScheduleNameConflict):
            schedule_client.reconcile(
                agent_name,
                [
                    Schedule(name="dup", cron="0 * * * * ?"),
                    Schedule(name="dup", cron="0 0 9 * * ?"),
                ],
            )
        # And nothing landed on the server.
        assert schedule_client.list_for_agent(agent_name) == []


class TestPauseResume:
    def test_pause_then_resume(self, schedule_client, agent_name):
        schedule_client.reconcile(agent_name, [Schedule(name="p", cron="0 0 9 * * ?")])
        wire = f"{agent_name}-p"

        info = schedule_client.get(wire)
        assert info.paused is False

        schedule_client.pause(wire)
        assert schedule_client.get(wire).paused is True

        schedule_client.resume(wire)
        assert schedule_client.get(wire).paused is False

    def test_paused_on_create_preserves_state(self, schedule_client, agent_name):
        """Spec §10 Q3: paused-on-create still records the schedule cleanly."""
        schedule_client.reconcile(
            agent_name, [Schedule(name="silent", cron="0 0 9 * * ?", paused=True)]
        )
        info = schedule_client.get(f"{agent_name}-silent")
        assert info.paused is True


class TestDelete:
    def test_delete_removes(self, schedule_client, agent_name):
        schedule_client.reconcile(agent_name, [Schedule(name="d", cron="0 * * * * ?")])
        wire = f"{agent_name}-d"
        schedule_client.delete(wire)
        assert schedule_client.list_for_agent(agent_name) == []

    def test_get_after_delete_raises(self, schedule_client, agent_name):
        schedule_client.reconcile(agent_name, [Schedule(name="g", cron="0 * * * * ?")])
        wire = f"{agent_name}-g"
        schedule_client.delete(wire)
        with pytest.raises(ScheduleNotFound):
            schedule_client.get(wire)


class TestPreviewNext:
    def test_returns_requested_count(self, schedule_client):
        times = schedule_client.preview_next("0 0 9 * * ?", n=3)
        assert len(times) == 3
        assert all(isinstance(t, int) for t in times)
        # Strictly increasing.
        assert times == sorted(set(times))


class TestRunNow:
    def test_returns_execution_id_immediately(self, schedule_client, agent_name):
        schedule_client.reconcile(
            agent_name, [Schedule(name="r", cron="0 0 9 * * ?", input={"trigger": "manual"})]
        )
        info = schedule_client.get(f"{agent_name}-r")

        t0 = time.monotonic()
        execution_id = schedule_client.run_now(info)
        elapsed = time.monotonic() - t0

        assert isinstance(execution_id, str) and execution_id
        # Spec §10 Q2: non-blocking — must return well before the noop workflow
        # could possibly complete a full round-trip.
        assert elapsed < 2.0, f"run_now blocked for {elapsed:.2f}s; expected non-blocking"
