# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for WorkerRestarter."""

import signal
from unittest.mock import MagicMock, patch

from agentspan.agents.runtime._liveness import WorkerRestarter


def _wm(workers_and_alive):
    """workers_and_alive: List[(task_name, alive, pid)]"""
    workers, procs = [], []
    for name, alive, pid in workers_and_alive:
        w = MagicMock()
        w.get_task_definition_name.return_value = name
        p = MagicMock()
        p.is_alive.return_value = alive
        p.pid = pid
        workers.append(w)
        procs.append(p)
    th = MagicMock()
    th.workers = workers
    th.task_runner_processes = procs
    wm = MagicMock()
    wm._task_handler = th
    return wm


def test_restart_kills_matching_alive_workers():
    wm = _wm([("setup_repo", True, 111), ("read_file", True, 222)])
    with patch("os.kill") as mock_kill:
        killed = WorkerRestarter.restart_for_tasks(wm, ["setup_repo"])
    assert killed == [111]
    mock_kill.assert_called_once_with(111, signal.SIGKILL)


def test_restart_skips_dead_processes():
    wm = _wm([("setup_repo", False, 111)])
    with patch("os.kill") as mock_kill:
        killed = WorkerRestarter.restart_for_tasks(wm, ["setup_repo"])
    assert killed == []
    mock_kill.assert_not_called()


def test_restart_skips_non_matching_workers():
    wm = _wm([("setup_repo", True, 111), ("read_file", True, 222)])
    with patch("os.kill") as mock_kill:
        killed = WorkerRestarter.restart_for_tasks(wm, ["other_tool"])
    assert killed == []
    mock_kill.assert_not_called()


def test_restart_no_op_if_no_task_handler():
    wm = MagicMock()
    wm._task_handler = None
    killed = WorkerRestarter.restart_for_tasks(wm, ["setup_repo"])
    assert killed == []


def test_restart_handles_already_gone_pid():
    wm = _wm([("setup_repo", True, 111)])
    with patch("os.kill", side_effect=ProcessLookupError):
        killed = WorkerRestarter.restart_for_tasks(wm, ["setup_repo"])
    # The PID was unreachable — still report we attempted it (already gone)
    assert killed == [111]
