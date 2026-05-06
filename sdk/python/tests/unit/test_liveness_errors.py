# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for liveness error types and dataclasses."""

from agentspan.agents.runtime._liveness import (
    StalledTaskInfo,
    WorkerStallError,
    WorkerStartupError,
)


def test_worker_startup_error_carries_context():
    err = WorkerStartupError(
        missing=[("setup_repo", "abc123")],
        domain="abc123",
        remediation="Retry start().",
    )
    assert err.missing == [("setup_repo", "abc123")]
    assert err.domain == "abc123"
    assert "Retry start()" in err.remediation
    assert "setup_repo" in str(err)
    assert "abc123" in str(err)


def test_worker_stall_error_carries_context():
    info = StalledTaskInfo(task_def_name="setup_repo", task_id="t-1", seconds_queued=42.0)
    err = WorkerStallError(
        execution_id="exec-1",
        domain="abc123",
        stalled_tasks=[info],
        remediation="Re-run with idempotency_key=foo.",
    )
    assert err.execution_id == "exec-1"
    assert err.stalled_tasks[0].task_def_name == "setup_repo"
    assert "exec-1" in str(err)
    assert "setup_repo" in str(err)
    assert "Re-run" in str(err)
    assert err.domain == "abc123"
    assert "42s" in str(err)


def test_errors_are_runtime_errors():
    assert issubclass(WorkerStartupError, RuntimeError)
    assert issubclass(WorkerStallError, RuntimeError)
