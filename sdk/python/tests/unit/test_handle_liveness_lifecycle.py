# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.
"""Verify AgentHandle starts and stops the liveness monitor around join() and applies stall policy."""

import threading
from unittest.mock import MagicMock

from agentspan.agents.result import AgentHandle


class _FakeStatus:
    is_complete = True
    output = {"x": 1}
    status = "COMPLETED"
    reason = None


def _runtime():
    rt = MagicMock()
    rt._config = MagicMock(
        liveness_enabled=True,
        liveness_stall_seconds=30.0,
        liveness_check_interval_seconds=10.0,
        liveness_stall_policy="restart_worker",
        liveness_stall_max_restarts=1,
    )
    rt._workflow_client = MagicMock()
    rt.get_status.return_value = _FakeStatus()
    rt._extract_token_usage.return_value = None
    rt._normalize_output.return_value = {"x": 1}
    rt._derive_finish_reason.return_value = "stop"
    return rt


def test_monitor_started_and_stopped_around_join(monkeypatch):
    started = threading.Event()
    stopped = threading.Event()

    class _FakeMonitor:
        def __init__(self, **kw):
            pass

        def start(self):
            started.set()

        def stop(self):
            stopped.set()

    import agentspan.agents.runtime._liveness as liv
    monkeypatch.setattr(liv, "ServerLivenessMonitor", _FakeMonitor)

    rt = _runtime()
    h = AgentHandle(execution_id="e", runtime=rt, run_id="d1")
    h.join(timeout=5)
    assert started.is_set()
    assert stopped.is_set()


def test_monitor_skipped_for_stateless_agent():
    rt = _runtime()
    h = AgentHandle(execution_id="e", runtime=rt, run_id=None)  # stateless
    h.join(timeout=5)
    assert h._liveness_monitor is None


def test_monitor_skipped_when_liveness_disabled():
    rt = _runtime()
    rt._config.liveness_enabled = False
    h = AgentHandle(execution_id="e", runtime=rt, run_id="d1")
    h.join(timeout=5)
    assert h._liveness_monitor is None


def _stall_err():
    from agentspan.agents.runtime._liveness import StalledTaskInfo, WorkerStallError

    return WorkerStallError(
        execution_id="e",
        domain="d1",
        stalled_tasks=[StalledTaskInfo("setup_repo", "task-1", 42.0)],
        remediation="x",
    )


def test_handle_stall_policy_restart_worker_calls_restarter(monkeypatch):
    """Default policy: stall triggers WorkerRestarter; _stall_error stays None."""
    called = {"names": None}

    def fake_restart(worker_manager, names):
        called["names"] = sorted(names)
        return [12345]

    import agentspan.agents.runtime._liveness as liv
    monkeypatch.setattr(liv.WorkerRestarter, "restart_for_tasks", staticmethod(fake_restart))

    rt = _runtime()
    rt._config.liveness_stall_policy = "restart_worker"
    rt._config.liveness_stall_max_restarts = 1
    rt._worker_manager = MagicMock()
    h = AgentHandle(execution_id="e", runtime=rt, run_id="d1")
    h._handle_stall(_stall_err())
    assert called["names"] == ["setup_repo"]
    assert h._stall_error is None
    assert h._stall_restart_count == 1


def test_handle_stall_policy_raise_sets_stall_error():
    rt = _runtime()
    rt._config.liveness_stall_policy = "raise"
    h = AgentHandle(execution_id="e", runtime=rt, run_id="d1")
    h._handle_stall(_stall_err())
    assert h._stall_error is not None
    assert h._stall_restart_count == 0


def test_handle_stall_policy_warn_logs_no_raise(caplog):
    import logging
    rt = _runtime()
    rt._config.liveness_stall_policy = "warn"
    h = AgentHandle(execution_id="e", runtime=rt, run_id="d1")
    with caplog.at_level(logging.WARNING, logger="agentspan.agents.result"):
        h._handle_stall(_stall_err())
    assert h._stall_error is None
    assert any("policy=warn" in rec.message for rec in caplog.records)


def test_handle_stall_falls_through_to_raise_after_max_restarts(monkeypatch):
    """After max_restarts cumulative restarts, the next stall raises."""
    import agentspan.agents.runtime._liveness as liv
    monkeypatch.setattr(
        liv.WorkerRestarter, "restart_for_tasks",
        staticmethod(lambda wm, names: [123]),
    )

    rt = _runtime()
    rt._config.liveness_stall_policy = "restart_worker"
    rt._config.liveness_stall_max_restarts = 1
    rt._worker_manager = MagicMock()
    h = AgentHandle(execution_id="e", runtime=rt, run_id="d1")
    h._handle_stall(_stall_err())  # 1st stall — restart
    assert h._stall_error is None
    h._handle_stall(_stall_err())  # 2nd stall — falls through to raise
    assert h._stall_error is not None
    assert h._stall_restart_count == 1
