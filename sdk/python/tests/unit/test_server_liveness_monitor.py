# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for ServerLivenessMonitor."""

import threading
import time
from unittest.mock import MagicMock

from agentspan.agents.runtime._liveness import (
    ServerLivenessMonitor,
    WorkerStallError,
)


class _FakeTask:
    def __init__(self, name, status, domain, scheduled_ms, poll_count, task_id="t-1"):
        self.task_def_name = name
        self.status = status
        self.domain = domain
        self.scheduled_time = scheduled_ms
        self.poll_count = poll_count
        self.task_id = task_id


class _FakeWorkflow:
    def __init__(self, status, tasks):
        self.status = status
        self.tasks = tasks


def _client(workflows):
    """Each call to get_workflow returns the next workflow in the list."""
    state = {"i": 0}

    def get_workflow(execution_id, include_tasks=True):
        idx = min(state["i"], len(workflows) - 1)
        state["i"] += 1
        return workflows[idx]

    c = MagicMock()
    c.get_workflow.side_effect = get_workflow
    return c


def test_monitor_fires_on_stalled_task():
    long_ago = int((time.time() - 60) * 1000)
    wf = _FakeWorkflow(
        "RUNNING",
        [_FakeTask("setup_repo", "SCHEDULED", "d1", long_ago, 0, "task-abc")],
    )
    client = _client([wf])
    fired = threading.Event()
    captured: list = []

    def on_stall(err):
        captured.append(err)
        fired.set()

    monitor = ServerLivenessMonitor(
        workflow_client=client,
        execution_id="exec-1",
        domain="d1",
        stall_seconds=10.0,
        check_interval=0.05,
        on_stall=on_stall,
    )
    monitor.start()
    assert fired.wait(timeout=2.0)
    monitor.stop()

    err = captured[0]
    assert isinstance(err, WorkerStallError)
    assert err.execution_id == "exec-1"
    assert err.stalled_tasks[0].task_def_name == "setup_repo"
    assert err.stalled_tasks[0].task_id == "task-abc"
    assert err.stalled_tasks[0].seconds_queued >= 10.0


def test_monitor_ignores_tasks_in_other_domains():
    long_ago = int((time.time() - 60) * 1000)
    wf = _FakeWorkflow(
        "RUNNING",
        [_FakeTask("setup_repo", "SCHEDULED", "OTHER_DOMAIN", long_ago, 0)],
    )
    client = _client([wf, wf])
    fired = threading.Event()

    monitor = ServerLivenessMonitor(
        workflow_client=client,
        execution_id="exec-1",
        domain="d1",
        stall_seconds=10.0,
        check_interval=0.05,
        on_stall=lambda e: fired.set(),
    )
    monitor.start()
    time.sleep(0.3)
    monitor.stop()
    assert not fired.is_set()


def test_monitor_ignores_tasks_with_polls():
    long_ago = int((time.time() - 60) * 1000)
    wf = _FakeWorkflow(
        "RUNNING",
        [_FakeTask("setup_repo", "SCHEDULED", "d1", long_ago, 5)],  # pollCount > 0
    )
    client = _client([wf, wf])
    fired = threading.Event()

    monitor = ServerLivenessMonitor(
        workflow_client=client,
        execution_id="exec-1",
        domain="d1",
        stall_seconds=10.0,
        check_interval=0.05,
        on_stall=lambda e: fired.set(),
    )
    monitor.start()
    time.sleep(0.3)
    monitor.stop()
    assert not fired.is_set()


def test_monitor_stops_on_terminal_workflow_status():
    wf = _FakeWorkflow("COMPLETED", [])
    client = _client([wf])

    monitor = ServerLivenessMonitor(
        workflow_client=client,
        execution_id="exec-1",
        domain="d1",
        stall_seconds=10.0,
        check_interval=0.05,
        on_stall=lambda e: None,
    )
    monitor.start()
    time.sleep(0.3)
    assert not monitor.is_running()


def test_monitor_dedupes_same_task_id():
    """Same task_id must only fire on_stall ONCE, even across many ticks."""
    long_ago = int((time.time() - 60) * 1000)
    wf = _FakeWorkflow(
        "RUNNING",
        [_FakeTask("setup_repo", "SCHEDULED", "d1", long_ago, 0, task_id="task-X")],
    )
    client = _client([wf, wf, wf, wf])
    call_count = {"n": 0}

    def on_stall(err):
        call_count["n"] += 1

    monitor = ServerLivenessMonitor(
        workflow_client=client,
        execution_id="exec-1",
        domain="d1",
        stall_seconds=10.0,
        check_interval=0.05,
        on_stall=on_stall,
    )
    monitor.start()
    time.sleep(0.4)
    monitor.stop()
    assert call_count["n"] == 1


def test_monitor_fires_again_for_new_task_id():
    """A NEW stalled task_id (not previously reported) must fire on_stall."""
    long_ago = int((time.time() - 60) * 1000)
    wf1 = _FakeWorkflow(
        "RUNNING",
        [_FakeTask("setup_repo", "SCHEDULED", "d1", long_ago, 0, task_id="task-A")],
    )
    wf2 = _FakeWorkflow(
        "RUNNING",
        [_FakeTask("setup_repo", "SCHEDULED", "d1", long_ago, 0, task_id="task-B")],
    )
    client = _client([wf1, wf2, wf2])
    seen_ids: list = []

    def on_stall(err):
        seen_ids.extend(t.task_id for t in err.stalled_tasks)

    monitor = ServerLivenessMonitor(
        workflow_client=client,
        execution_id="exec-1",
        domain="d1",
        stall_seconds=10.0,
        check_interval=0.05,
        on_stall=on_stall,
    )
    monitor.start()
    time.sleep(0.4)
    monitor.stop()
    assert "task-A" in seen_ids and "task-B" in seen_ids


def test_monitor_no_op_when_domain_is_none():
    """Stateless agent (domain=None) — monitor exits immediately."""
    monitor = ServerLivenessMonitor(
        workflow_client=MagicMock(),
        execution_id="exec-1",
        domain=None,
        stall_seconds=10.0,
        check_interval=0.05,
        on_stall=lambda e: None,
    )
    monitor.start()
    time.sleep(0.2)
    assert not monitor.is_running()
