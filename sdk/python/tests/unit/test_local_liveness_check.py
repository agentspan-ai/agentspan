# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for LocalLivenessCheck.verify."""

import time
from unittest.mock import MagicMock

import pytest

from agentspan.agents.runtime._liveness import (
    LocalLivenessCheck,
    WorkerStartupError,
)


def _fake_worker(name: str, domain, alive: bool):
    w = MagicMock()
    w.get_task_definition_name.return_value = name
    w.domain = domain
    p = MagicMock()
    p.is_alive.return_value = alive
    return w, p


def _fake_manager(pairs):
    """pairs: List[(name, domain, alive)]"""
    workers, procs = [], []
    for name, dom, alive in pairs:
        w, p = _fake_worker(name, dom, alive)
        workers.append(w)
        procs.append(p)
    th = MagicMock()
    th.workers = workers
    th.task_runner_processes = procs
    wm = MagicMock()
    wm._task_handler = th
    return wm


def test_verify_passes_when_all_workers_alive():
    wm = _fake_manager([("setup_repo", "d1", True), ("read_file", "d1", True)])
    LocalLivenessCheck.verify(
        wm, expected=[("setup_repo", "d1"), ("read_file", "d1")], timeout=0.2
    )


def test_verify_raises_when_worker_missing():
    wm = _fake_manager([("read_file", "d1", True)])  # setup_repo missing entirely
    with pytest.raises(WorkerStartupError) as exc_info:
        LocalLivenessCheck.verify(
            wm, expected=[("setup_repo", "d1"), ("read_file", "d1")], timeout=0.2
        )
    err = exc_info.value
    assert ("setup_repo", "d1") in err.missing
    assert ("read_file", "d1") not in err.missing
    assert err.domain == "d1"


def test_verify_raises_when_worker_dead():
    wm = _fake_manager([("setup_repo", "d1", False), ("read_file", "d1", True)])
    with pytest.raises(WorkerStartupError) as exc_info:
        LocalLivenessCheck.verify(
            wm, expected=[("setup_repo", "d1"), ("read_file", "d1")], timeout=0.2
        )
    assert ("setup_repo", "d1") in exc_info.value.missing


def test_verify_polls_until_alive_within_timeout():
    """Worker starts dead, becomes alive after 50ms — should pass."""
    wm = _fake_manager([("setup_repo", "d1", False)])
    proc = wm._task_handler.task_runner_processes[0]

    state = {"calls": 0}

    def is_alive_side_effect():
        state["calls"] += 1
        return state["calls"] > 5  # alive on the 6th call

    proc.is_alive.side_effect = is_alive_side_effect

    start = time.monotonic()
    LocalLivenessCheck.verify(wm, expected=[("setup_repo", "d1")], timeout=1.0, poll_interval=0.02)
    elapsed = time.monotonic() - start
    assert elapsed < 1.0


def test_verify_no_op_for_empty_expected():
    wm = _fake_manager([])
    LocalLivenessCheck.verify(wm, expected=[], timeout=0.1)


def test_verify_handles_missing_task_handler():
    """If WorkerManager has no _task_handler (auto_start_workers=False), skip."""
    wm = MagicMock()
    wm._task_handler = None
    LocalLivenessCheck.verify(wm, expected=[("setup_repo", "d1")], timeout=0.1)
