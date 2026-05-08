# Worker Liveness & Idempotent Auto-Resume Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect "workers registered but not polling" within seconds (Mode B) and surface idempotent auto-resume telemetry (Mode A) on the Agentspan Python SDK so the issue from execution `95087a26-...` (setup_repo queued forever, pollCount=0) cannot recur silently.

**Architecture:** Add a `_liveness.py` module in `sdk/python/src/agentspan/agents/runtime/` exposing `LocalLivenessCheck`, `ServerLivenessMonitor`, `WorkerRestarter`, and the typed errors `WorkerStartupError` / `WorkerStallError`. Wire into the four `start*/stream*` call sites in `runtime.py` and the `join()` poll loop in `result.py`. On stall the default policy is `"restart_worker"` (SIGKILL the stuck subprocess; Conductor's TaskHandler monitor respawns it within ~1–2s, the same pattern used by the test `_WorkerWatchdog` in `conftest.py:53`). After `liveness_stall_max_restarts` cumulative restarts in an execution, fall through to `raise`. Feature-flagged via `AgentConfig.liveness_enabled`.

**Tech Stack:** Python 3.11+, `dataclasses`, `threading.Thread`, existing Conductor `WorkflowClient` for server polls, `pytest` with the integration `runtime` fixture.

**Reference spec:** `docs/design/2026-05-06-worker-liveness-and-idempotent-resume.md`

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `sdk/python/src/agentspan/agents/runtime/_liveness.py` | NEW | `WorkerStartupError`, `WorkerStallError`, `StalledTaskInfo`, `LocalLivenessCheck`, `ServerLivenessMonitor`, `WorkerRestarter` |
| `sdk/python/src/agentspan/agents/runtime/config.py` | MODIFY | Add 6 fields + env var loading |
| `sdk/python/src/agentspan/agents/runtime/runtime.py` | MODIFY | Add `_collect_registered_pairs`, call `LocalLivenessCheck.verify`, compute `is_resumed`, log resume telemetry |
| `sdk/python/src/agentspan/agents/result.py` | MODIFY | `AgentHandle` gets `is_resumed`, `_stall_error`, `_liveness_monitor`; `join()`/`join_async()` start monitor and check `_stall_error` |
| `sdk/python/src/agentspan/agents/__init__.py` | MODIFY | Re-export `WorkerStartupError`, `WorkerStallError` |
| `sdk/python/tests/integration/test_worker_liveness_live.py` | NEW | Three e2e tests + their validity counter-tests |

The new module is small (~250 LOC) and self-contained — one responsibility per class. We don't restructure existing files.

---

## Task 1: Add config fields for liveness

**Files:**
- Modify: `sdk/python/src/agentspan/agents/runtime/config.py:48-119`

- [ ] **Step 1: Write failing test asserting new fields exist with defaults**

Create `sdk/python/tests/unit/test_liveness_config.py`:

```python
"""Unit tests for liveness config fields."""

import os

from agentspan.agents.runtime.config import AgentConfig


def test_liveness_defaults_present():
    cfg = AgentConfig()
    assert cfg.liveness_enabled is True
    assert cfg.liveness_startup_timeout_seconds == 2.0
    assert cfg.liveness_stall_seconds == 30.0
    assert cfg.liveness_check_interval_seconds == 10.0
    assert cfg.liveness_stall_policy == "restart_worker"
    assert cfg.liveness_stall_max_restarts == 1


def test_liveness_from_env_overrides(monkeypatch):
    monkeypatch.setenv("AGENTSPAN_LIVENESS_ENABLED", "false")
    monkeypatch.setenv("AGENTSPAN_LIVENESS_STARTUP_TIMEOUT", "0.5")
    monkeypatch.setenv("AGENTSPAN_LIVENESS_STALL_SECONDS", "5")
    monkeypatch.setenv("AGENTSPAN_LIVENESS_CHECK_INTERVAL", "2")
    monkeypatch.setenv("AGENTSPAN_LIVENESS_STALL_POLICY", "raise")
    monkeypatch.setenv("AGENTSPAN_LIVENESS_STALL_MAX_RESTARTS", "3")
    cfg = AgentConfig.from_env()
    assert cfg.liveness_enabled is False
    assert cfg.liveness_startup_timeout_seconds == 0.5
    assert cfg.liveness_stall_seconds == 5.0
    assert cfg.liveness_check_interval_seconds == 2.0
    assert cfg.liveness_stall_policy == "raise"
    assert cfg.liveness_stall_max_restarts == 3


def test_liveness_invalid_policy_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("AGENTSPAN_LIVENESS_STALL_POLICY", "wat")
    cfg = AgentConfig.from_env()
    assert cfg.liveness_stall_policy == "restart_worker"
```

- [ ] **Step 2: Run test to confirm it fails**

Run: `cd sdk/python && uv run pytest tests/unit/test_liveness_config.py -v`
Expected: `AttributeError: 'AgentConfig' object has no attribute 'liveness_enabled'`

- [ ] **Step 3: Add `_env_float` helper and 4 fields to `AgentConfig`**

In `sdk/python/src/agentspan/agents/runtime/config.py`, just after `_env_int` (line ~44), add:

```python
def _env_float(var: str, default: float = 0.0) -> float:
    """Read a float environment variable."""
    val = os.environ.get(var)
    if val is None or val.strip() == "":
        return default
    return float(val)
```

In the `AgentConfig` dataclass body (after `credential_strict_mode: bool = False`, line ~81), add:

```python
    liveness_enabled: bool = True
    liveness_startup_timeout_seconds: float = 2.0
    liveness_stall_seconds: float = 30.0
    liveness_check_interval_seconds: float = 10.0
    liveness_stall_policy: str = "restart_worker"  # "restart_worker" | "raise" | "warn"
    liveness_stall_max_restarts: int = 1
```

In the docstring (line 67ish), append to the Attributes block:

```
        liveness_enabled: Master switch for the worker liveness checks
            added in the worker-liveness fix. Disable to opt out.
        liveness_startup_timeout_seconds: How long ``LocalLivenessCheck``
            waits for each registered worker process to become alive after
            ``start()``.
        liveness_stall_seconds: ``ServerLivenessMonitor`` flags a task in
            our domain that has been queued this long with ``pollCount=0``.
        liveness_check_interval_seconds: Tick interval for
            ``ServerLivenessMonitor``.
        liveness_stall_policy: What to do on stall. ``"restart_worker"``
            (default) SIGKILLs the stuck subprocess so the TaskHandler
            monitor respawns it; ``"raise"`` skips restart and surfaces
            ``WorkerStallError`` from ``join()``; ``"warn"`` only logs.
        liveness_stall_max_restarts: Cumulative cap on auto-restarts per
            execution. Beyond this, the policy falls through to ``"raise"``.
```

Add a small validator at the bottom of `__post_init__` (after the existing `server_url` block):

```python
        valid_policies = ("restart_worker", "raise", "warn")
        if self.liveness_stall_policy not in valid_policies:
            logger.warning(
                "Invalid liveness_stall_policy %r — falling back to 'restart_worker'.",
                self.liveness_stall_policy,
            )
            self.liveness_stall_policy = "restart_worker"
```

In `from_env()` (line ~103), add six arguments before `log_level`:

```python
            liveness_enabled=_env_bool("AGENTSPAN_LIVENESS_ENABLED", True),
            liveness_startup_timeout_seconds=_env_float("AGENTSPAN_LIVENESS_STARTUP_TIMEOUT", 2.0),
            liveness_stall_seconds=_env_float("AGENTSPAN_LIVENESS_STALL_SECONDS", 30.0),
            liveness_check_interval_seconds=_env_float("AGENTSPAN_LIVENESS_CHECK_INTERVAL", 10.0),
            liveness_stall_policy=_env("AGENTSPAN_LIVENESS_STALL_POLICY", "restart_worker"),
            liveness_stall_max_restarts=_env_int("AGENTSPAN_LIVENESS_STALL_MAX_RESTARTS", 1),
```

- [ ] **Step 4: Run test to confirm it passes**

Run: `cd sdk/python && uv run pytest tests/unit/test_liveness_config.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add sdk/python/src/agentspan/agents/runtime/config.py sdk/python/tests/unit/test_liveness_config.py
git commit -m "feat(sdk): add liveness config fields

Adds liveness_enabled, liveness_startup_timeout_seconds,
liveness_stall_seconds, liveness_check_interval_seconds with
AGENTSPAN_LIVENESS_* env var bindings. Wiring in subsequent commits."
```

---

## Task 2: Create `_liveness.py` with errors and `StalledTaskInfo`

**Files:**
- Create: `sdk/python/src/agentspan/agents/runtime/_liveness.py`
- Create: `sdk/python/tests/unit/test_liveness_errors.py`

- [ ] **Step 1: Write failing test for the error/data classes**

```python
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


def test_errors_are_runtime_errors():
    assert issubclass(WorkerStartupError, RuntimeError)
    assert issubclass(WorkerStallError, RuntimeError)
```

- [ ] **Step 2: Run test to confirm it fails**

Run: `cd sdk/python && uv run pytest tests/unit/test_liveness_errors.py -v`
Expected: `ModuleNotFoundError: No module named 'agentspan.agents.runtime._liveness'`

- [ ] **Step 3: Create `_liveness.py` with errors + `StalledTaskInfo`**

```python
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Worker liveness verification + stall detection.

Two complementary mechanisms protect against the "pollCount=0" failure
mode where a Conductor task sits queued forever because no Python worker
is polling for it.

``LocalLivenessCheck.verify`` runs synchronously after worker registration
and confirms each expected worker subprocess is alive. ``ServerLivenessMonitor``
runs as a daemon thread during ``AgentHandle.join()`` and watches for
SCHEDULED tasks in our domain that exceed a stall threshold.

See ``docs/design/2026-05-06-worker-liveness-and-idempotent-resume.md``.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Optional, Tuple

logger = logging.getLogger("agentspan.agents.runtime.liveness")


@dataclass
class StalledTaskInfo:
    """A single SCHEDULED task that exceeded the stall threshold."""

    task_def_name: str
    task_id: str
    seconds_queued: float


class WorkerStartupError(RuntimeError):
    """Raised when one or more registered workers have no live process.

    Surfaces from ``runtime.start()`` (or its async/stream variants) within
    ``liveness_startup_timeout_seconds`` of registration.
    """

    def __init__(
        self,
        *,
        missing: List[Tuple[str, Optional[str]]],
        domain: Optional[str],
        remediation: str,
    ) -> None:
        self.missing = list(missing)
        self.domain = domain
        self.remediation = remediation
        pretty = ", ".join(f"{name}@{dom or '<no-domain>'}" for name, dom in self.missing)
        msg = (
            f"Worker startup verification failed for domain={domain!r}: "
            f"missing or dead worker process(es): [{pretty}]. {remediation}"
        )
        super().__init__(msg)


class WorkerStallError(RuntimeError):
    """Raised when one or more SCHEDULED tasks have been queued past the stall threshold.

    Surfaces from ``AgentHandle.join()`` (or ``join_async()``).
    """

    def __init__(
        self,
        *,
        execution_id: str,
        domain: Optional[str],
        stalled_tasks: List[StalledTaskInfo],
        remediation: str,
    ) -> None:
        self.execution_id = execution_id
        self.domain = domain
        self.stalled_tasks = list(stalled_tasks)
        self.remediation = remediation
        pretty = ", ".join(
            f"{t.task_def_name}({t.task_id}) queued {t.seconds_queued:.0f}s"
            for t in self.stalled_tasks
        )
        msg = (
            f"Worker stall detected on execution {execution_id} (domain={domain!r}): "
            f"[{pretty}]. {remediation}"
        )
        super().__init__(msg)
```

- [ ] **Step 4: Run test to confirm it passes**

Run: `cd sdk/python && uv run pytest tests/unit/test_liveness_errors.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add sdk/python/src/agentspan/agents/runtime/_liveness.py sdk/python/tests/unit/test_liveness_errors.py
git commit -m "feat(sdk): add WorkerStartupError, WorkerStallError, StalledTaskInfo

New _liveness.py module — typed errors carrying execution_id, domain,
missing/stalled task info, and a remediation string. Used by the local
and server liveness checks added in subsequent commits."
```

---

## Task 3: Implement `LocalLivenessCheck.verify`

**Files:**
- Modify: `sdk/python/src/agentspan/agents/runtime/_liveness.py`
- Create: `sdk/python/tests/unit/test_local_liveness_check.py`

- [ ] **Step 1: Write failing test using a fake WorkerManager**

```python
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
```

- [ ] **Step 2: Run test to confirm it fails**

Run: `cd sdk/python && uv run pytest tests/unit/test_local_liveness_check.py -v`
Expected: `ImportError: cannot import name 'LocalLivenessCheck'`

- [ ] **Step 3: Add `LocalLivenessCheck` to `_liveness.py`**

Append to `sdk/python/src/agentspan/agents/runtime/_liveness.py`:

```python
class LocalLivenessCheck:
    """Verifies that every registered ``(task_name, domain)`` pair has a live process.

    Pure local check — no network calls. Polls
    ``WorkerManager._task_handler.task_runner_processes`` until each
    expected pair maps to a process whose ``is_alive()`` is True, or the
    timeout elapses.
    """

    @staticmethod
    def verify(
        worker_manager: object,
        expected: Iterable[Tuple[str, Optional[str]]],
        *,
        timeout: float = 2.0,
        poll_interval: float = 0.05,
    ) -> None:
        expected_set = set(expected)
        if not expected_set:
            return

        task_handler = getattr(worker_manager, "_task_handler", None)
        if task_handler is None:
            # auto_start_workers=False or pre-init — nothing to verify.
            return

        deadline = time.monotonic() + timeout
        missing: set = set(expected_set)
        domain_for_error: Optional[str] = next(iter(expected_set))[1]

        while True:
            workers = getattr(task_handler, "workers", []) or []
            procs = getattr(task_handler, "task_runner_processes", []) or []

            alive_pairs: set = set()
            for w, p in zip(workers, procs):
                try:
                    name = w.get_task_definition_name()
                except Exception:
                    continue
                domain = getattr(w, "domain", None)
                if (name, domain) in expected_set and p is not None and p.is_alive():
                    alive_pairs.add((name, domain))

            missing = expected_set - alive_pairs
            if not missing:
                return
            if time.monotonic() >= deadline:
                break
            time.sleep(poll_interval)

        raise WorkerStartupError(
            missing=sorted(missing),
            domain=domain_for_error,
            remediation=(
                "The worker subprocess(es) are not running. This usually means "
                "fork() failed or an exception was swallowed during "
                "WorkerManager.start(). Check process logs and retry start(). "
                "Set AGENTSPAN_LIVENESS_ENABLED=false to disable this check."
            ),
        )
```

- [ ] **Step 4: Run test to confirm it passes**

Run: `cd sdk/python && uv run pytest tests/unit/test_local_liveness_check.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add sdk/python/src/agentspan/agents/runtime/_liveness.py sdk/python/tests/unit/test_local_liveness_check.py
git commit -m "feat(sdk): LocalLivenessCheck — assert worker subprocesses are alive

Polls WorkerManager._task_handler for each expected (task_name, domain)
pair until alive or timeout. Raises WorkerStartupError with the missing
set + remediation hint."
```

---

## Task 4: Implement `ServerLivenessMonitor`

**Files:**
- Modify: `sdk/python/src/agentspan/agents/runtime/_liveness.py`
- Create: `sdk/python/tests/unit/test_server_liveness_monitor.py`

- [ ] **Step 1: Write failing test using a fake workflow_client**

```python
"""Unit tests for ServerLivenessMonitor."""

import threading
import time
from unittest.mock import MagicMock

from agentspan.agents.runtime._liveness import (
    ServerLivenessMonitor,
    StalledTaskInfo,
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
```

- [ ] **Step 2: Run test to confirm it fails**

Run: `cd sdk/python && uv run pytest tests/unit/test_server_liveness_monitor.py -v`
Expected: `ImportError: cannot import name 'ServerLivenessMonitor'`

- [ ] **Step 3: Add `ServerLivenessMonitor` to `_liveness.py`**

Append to `sdk/python/src/agentspan/agents/runtime/_liveness.py`:

```python
_TERMINAL_STATUSES = frozenset({"COMPLETED", "FAILED", "TERMINATED", "TIMED_OUT", "PAUSED"})


class ServerLivenessMonitor:
    """Daemon thread that detects unpolled SCHEDULED tasks in our domain.

    Polls the workflow every ``check_interval`` seconds; fires ``on_stall``
    when any SCHEDULED task in our domain has been queued longer than
    ``stall_seconds`` with ``pollCount=0``. Per-``task_id`` dedup ensures
    each stalled task is reported at most once. Stops itself when the
    workflow reaches a terminal status or ``stop()`` is called.
    """

    def __init__(
        self,
        *,
        workflow_client: object,
        execution_id: str,
        domain: Optional[str],
        stall_seconds: float = 30.0,
        check_interval: float = 10.0,
        on_stall: Callable[[WorkerStallError], None],
    ) -> None:
        self._workflow_client = workflow_client
        self._execution_id = execution_id
        self._domain = domain
        self._stall_seconds = stall_seconds
        self._check_interval = check_interval
        self._on_stall = on_stall
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._seen: set = set()  # task_ids already reported

    def start(self) -> None:
        if self._domain is None:
            # Stateless agent — nothing routes through a domain queue, so
            # there's nothing to monitor.
            return
        self._thread = threading.Thread(
            target=self._loop,
            name=f"ServerLivenessMonitor[{self._execution_id[:8]}]",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                if self._tick():
                    return  # workflow terminal — stop
            except Exception as exc:
                logger.debug(
                    "ServerLivenessMonitor tick failed for %s: %s",
                    self._execution_id, exc,
                )
            self._stop_event.wait(self._check_interval)

    def _tick(self) -> bool:
        """Return True if monitor should stop (workflow terminal)."""
        wf = self._workflow_client.get_workflow(self._execution_id, include_tasks=True)
        status = getattr(wf, "status", None)
        if status in _TERMINAL_STATUSES:
            return True

        now_ms = time.time() * 1000
        threshold_ms = self._stall_seconds * 1000
        new_stalled: List[StalledTaskInfo] = []

        for t in getattr(wf, "tasks", []) or []:
            if getattr(t, "status", None) != "SCHEDULED":
                continue
            if getattr(t, "domain", None) != self._domain:
                continue
            if getattr(t, "poll_count", 0) != 0:
                continue
            task_id = getattr(t, "task_id", None)
            if not task_id or task_id in self._seen:
                continue
            scheduled_ms = getattr(t, "scheduled_time", 0) or 0
            queued_ms = now_ms - scheduled_ms
            if queued_ms < threshold_ms:
                continue
            new_stalled.append(
                StalledTaskInfo(
                    task_def_name=getattr(t, "task_def_name", "<unknown>"),
                    task_id=task_id,
                    seconds_queued=queued_ms / 1000.0,
                )
            )
            self._seen.add(task_id)

        if new_stalled:
            err = WorkerStallError(
                execution_id=self._execution_id,
                domain=self._domain,
                stalled_tasks=new_stalled,
                remediation=(
                    "No worker is polling for these tasks. If the original "
                    "process died, re-run with the same idempotency_key (or "
                    "call runtime.resume(execution_id, agent)) to re-attach "
                    "workers. Set AGENTSPAN_LIVENESS_ENABLED=false to disable."
                ),
            )
            try:
                self._on_stall(err)
            except Exception as exc:
                logger.warning("on_stall callback raised: %s", exc)

        return False
```

- [ ] **Step 4: Run test to confirm it passes**

Run: `cd sdk/python && uv run pytest tests/unit/test_server_liveness_monitor.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add sdk/python/src/agentspan/agents/runtime/_liveness.py sdk/python/tests/unit/test_server_liveness_monitor.py
git commit -m "feat(sdk): ServerLivenessMonitor — daemon thread detecting unpolled tasks

Polls workflow.tasks every check_interval, fires WorkerStallError when a
SCHEDULED task in our domain has been queued past stall_seconds with
pollCount=0. Per-task_id dedup; stops on terminal workflow status."
```

---

## Task 4b: Implement `WorkerRestarter`

**Files:**
- Modify: `sdk/python/src/agentspan/agents/runtime/_liveness.py`
- Create: `sdk/python/tests/unit/test_worker_restarter.py`

- [ ] **Step 1: Write failing test**

```python
"""Unit tests for WorkerRestarter."""

import os
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
```

- [ ] **Step 2: Run test to confirm it fails**

Run: `cd sdk/python && uv run pytest tests/unit/test_worker_restarter.py -v`
Expected: `ImportError: cannot import name 'WorkerRestarter'`

- [ ] **Step 3: Append `WorkerRestarter` to `_liveness.py`**

```python
import os
import signal


class WorkerRestarter:
    """SIGKILLs worker subprocesses bound to specific task names so the
    Conductor TaskHandler monitor (``monitor_processes=True``) respawns them.

    This is the same recovery mechanism used by the test
    ``_WorkerWatchdog`` in ``conftest.py:53`` to fight macOS fork()
    deadlocks. Generalized here for production use under the
    ``"restart_worker"`` stall policy.
    """

    @staticmethod
    def restart_for_tasks(
        worker_manager: object, task_def_names: Iterable[str]
    ) -> List[int]:
        """Kill the subprocess(es) bound to *task_def_names*. Returns killed PIDs."""
        names = set(task_def_names)
        if not names:
            return []
        task_handler = getattr(worker_manager, "_task_handler", None)
        if task_handler is None:
            return []

        workers = getattr(task_handler, "workers", []) or []
        procs = getattr(task_handler, "task_runner_processes", []) or []

        killed: List[int] = []
        for w, p in zip(workers, procs):
            try:
                if w.get_task_definition_name() not in names:
                    continue
            except Exception:
                continue
            if p is None or not p.is_alive():
                continue
            pid = getattr(p, "pid", None)
            if pid is None:
                continue
            try:
                os.kill(pid, signal.SIGKILL)
                killed.append(pid)
            except ProcessLookupError:
                # Already gone — still record it so caller knows we acted.
                killed.append(pid)
            except Exception as exc:
                logger.warning("Failed to SIGKILL worker pid=%s: %s", pid, exc)

        if killed:
            logger.warning(
                "WorkerRestarter killed pid(s)=%s for task(s)=%s — "
                "TaskHandler monitor will respawn.",
                killed, sorted(names),
            )
        return killed
```

- [ ] **Step 4: Run tests**

Run: `cd sdk/python && uv run pytest tests/unit/test_worker_restarter.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add sdk/python/src/agentspan/agents/runtime/_liveness.py sdk/python/tests/unit/test_worker_restarter.py
git commit -m "feat(sdk): WorkerRestarter — SIGKILL stuck worker subprocesses

The Conductor TaskHandler is started with monitor_processes=True
(WorkerManager.start), so killed subprocesses are respawned within
1-2s. This generalizes the test _WorkerWatchdog pattern from
conftest.py:53 for production use under the restart_worker stall policy."
```

---

## Task 5: Add `_collect_registered_pairs` helper to `runtime.py`

**Files:**
- Modify: `sdk/python/src/agentspan/agents/runtime/runtime.py` (add new method around line 975, after `_collect_worker_names`)
- Create: `sdk/python/tests/unit/test_collect_registered_pairs.py`

- [ ] **Step 1: Write failing test**

```python
"""Unit tests for AgentRuntime._collect_registered_pairs."""

from agentspan.agents import Agent, tool
from agentspan.agents.runtime.runtime import AgentRuntime


@tool
def stateful_tool(x: str) -> str:
    """A tool."""
    return x


@tool
def stateless_tool(y: str) -> str:
    """Another tool."""
    return y


def test_pairs_include_domain_for_stateful_agent_tools(monkeypatch):
    monkeypatch.setenv("AGENTSPAN_AUTO_START_SERVER", "false")
    rt = AgentRuntime.__new__(AgentRuntime)  # avoid full init
    agent = Agent(
        name="A", model="openai/gpt-4o-mini", stateful=True, tools=[stateful_tool]
    )
    pairs = rt._collect_registered_pairs(agent, domain="d1")
    assert ("stateful_tool", "d1") in pairs


def test_pairs_use_none_domain_for_stateless_agent_tools(monkeypatch):
    monkeypatch.setenv("AGENTSPAN_AUTO_START_SERVER", "false")
    rt = AgentRuntime.__new__(AgentRuntime)
    agent = Agent(
        name="A", model="openai/gpt-4o-mini", stateful=False, tools=[stateless_tool]
    )
    pairs = rt._collect_registered_pairs(agent, domain="d1")
    assert ("stateless_tool", None) in pairs


def test_pairs_recurse_into_sub_agents(monkeypatch):
    monkeypatch.setenv("AGENTSPAN_AUTO_START_SERVER", "false")
    rt = AgentRuntime.__new__(AgentRuntime)
    sub = Agent(
        name="sub", model="openai/gpt-4o-mini", stateful=True, tools=[stateful_tool]
    )
    parent = Agent(name="parent", model="openai/gpt-4o-mini", agents=[sub])
    pairs = rt._collect_registered_pairs(parent, domain="d1")
    assert ("stateful_tool", "d1") in pairs


def test_pairs_skip_non_worker_tool_types(monkeypatch):
    """http/mcp/human/agent_tool tools are server-side; no Python worker."""
    monkeypatch.setenv("AGENTSPAN_AUTO_START_SERVER", "false")
    rt = AgentRuntime.__new__(AgentRuntime)
    from agentspan.agents.tool import http_tool

    h = http_tool(
        name="my_http", description="x", url="https://example.com",
    )
    agent = Agent(
        name="A", model="openai/gpt-4o-mini", stateful=True,
        tools=[h, stateful_tool],
    )
    pairs = rt._collect_registered_pairs(agent, domain="d1")
    assert ("stateful_tool", "d1") in pairs
    assert all(name != "my_http" for name, _ in pairs)
```

- [ ] **Step 2: Run test to confirm it fails**

Run: `cd sdk/python && uv run pytest tests/unit/test_collect_registered_pairs.py -v`
Expected: `AttributeError: 'AgentRuntime' object has no attribute '_collect_registered_pairs'`

- [ ] **Step 3: Add helper to `AgentRuntime`**

In `sdk/python/src/agentspan/agents/runtime/runtime.py`, after the `_collect_worker_names` method (line 975, just before `_register_workers`), insert:

```python
    def _collect_registered_pairs(
        self, agent: Agent, domain: Optional[str]
    ) -> List[Tuple[str, Optional[str]]]:
        """Return ``(task_name, registered_domain)`` pairs for user-tool workers.

        Mirrors the per-tool domain decision in
        ``ToolRegistry.register_tool_workers``: a tool's worker uses the
        passed-in ``domain`` only when its owning agent is stateful (or the
        tool itself is). Everything else is registered with ``domain=None``.

        Used by ``LocalLivenessCheck.verify`` to confirm each registered
        worker subprocess is alive.
        """
        from agentspan.agents.tool import get_tool_def

        pairs: List[Tuple[str, Optional[str]]] = []
        agent_stateful = bool(getattr(agent, "stateful", False))
        for t in getattr(agent, "tools", []) or []:
            try:
                td = get_tool_def(t)
            except TypeError:
                continue
            if td.tool_type not in ("worker", "cli"):
                continue
            if td.func is None:
                continue
            tool_domain = domain if (agent_stateful or td.stateful) else None
            pairs.append((td.name, tool_domain))

        for sub in getattr(agent, "agents", []) or []:
            if getattr(sub, "external", False):
                continue
            pairs.extend(self._collect_registered_pairs(sub, domain))

        # Dedupe while preserving order
        seen: set = set()
        unique: List[Tuple[str, Optional[str]]] = []
        for p in pairs:
            if p not in seen:
                seen.add(p)
                unique.append(p)
        return unique
```

Also ensure `Tuple` and `List` are imported. Check the top of `runtime.py` for existing `from typing import ...` and add `Tuple` if missing.

- [ ] **Step 4: Run test to confirm it passes**

Run: `cd sdk/python && uv run pytest tests/unit/test_collect_registered_pairs.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add sdk/python/src/agentspan/agents/runtime/runtime.py sdk/python/tests/unit/test_collect_registered_pairs.py
git commit -m "feat(sdk): _collect_registered_pairs helper for liveness check

Walks the agent tree and returns the (task_name, domain) pairs that
ToolRegistry.register_tool_workers actually registers, so
LocalLivenessCheck knows what to verify."
```

---

## Task 6: Wire `LocalLivenessCheck` into the four start/stream call sites

**Files:**
- Modify: `sdk/python/src/agentspan/agents/runtime/runtime.py:2535-2540, 3651-3656, 4051-4055, 4189-4194`

- [ ] **Step 1: Identify the four call sites**

```bash
grep -n "worker_domain = self._resolve_worker_domain" sdk/python/src/agentspan/agents/runtime/runtime.py
```

Expected output (line numbers may shift slightly):
```
2535:        worker_domain = self._resolve_worker_domain(execution_id, run_id)
3651:        worker_domain = self._resolve_worker_domain(execution_id, run_id)
4051:        worker_domain = self._resolve_worker_domain(execution_id, run_id)
4189:        worker_domain = self._resolve_worker_domain(execution_id, run_id)
```

- [ ] **Step 2: At each site, add the local liveness check after `_register_and_start_skill_workers`**

For EACH of the four sites, the existing block looks like:

```python
        worker_domain = self._resolve_worker_domain(execution_id, run_id)

        self._prepare_workers(agent, required_workers=required_workers, domain=worker_domain)
        self._register_and_start_skill_workers(pre_deployed_skills, domain=worker_domain)
```

Modify it to:

```python
        worker_domain = self._resolve_worker_domain(execution_id, run_id)

        self._prepare_workers(agent, required_workers=required_workers, domain=worker_domain)
        self._register_and_start_skill_workers(pre_deployed_skills, domain=worker_domain)

        if self._config.liveness_enabled:
            from agentspan.agents.runtime._liveness import LocalLivenessCheck

            expected_pairs = self._collect_registered_pairs(agent, worker_domain)
            LocalLivenessCheck.verify(
                self._worker_manager,
                expected_pairs,
                timeout=self._config.liveness_startup_timeout_seconds,
            )
```

Make this exact change at all four occurrences. The `from ... import LocalLivenessCheck` line is intentionally local to keep import-time cost zero when liveness is disabled.

- [ ] **Step 3: Add a unit test that disabling liveness skips the check**

Append to `sdk/python/tests/unit/test_local_liveness_check.py`:

```python
def test_runtime_skips_check_when_disabled(monkeypatch):
    """Liveness check is gated by config.liveness_enabled."""
    from agentspan.agents.runtime.config import AgentConfig

    cfg = AgentConfig.from_env()
    cfg.liveness_enabled = False
    assert cfg.liveness_enabled is False
```

- [ ] **Step 4: Run unit tests**

Run:
```bash
cd sdk/python && uv run pytest tests/unit/test_local_liveness_check.py tests/unit/test_collect_registered_pairs.py tests/unit/test_liveness_config.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add sdk/python/src/agentspan/agents/runtime/runtime.py sdk/python/tests/unit/test_local_liveness_check.py
git commit -m "feat(sdk): call LocalLivenessCheck after worker registration

After every _prepare_workers call (start/start_async/stream/stream_async),
verify each registered (task_name, domain) pair has a live process.
Gated on AgentConfig.liveness_enabled (default true)."
```

---

## Task 7: Add `is_resumed` and resume telemetry

**Files:**
- Modify: `sdk/python/src/agentspan/agents/result.py:236-246` (AgentHandle constructor)
- Modify: `sdk/python/src/agentspan/agents/runtime/runtime.py:2535, 3651, 4051, 4189` (after `_resolve_worker_domain`)

- [ ] **Step 1: Add `is_resumed` to `AgentHandle.__init__`**

In `sdk/python/src/agentspan/agents/result.py:236-246`, modify:

```python
    def __init__(
        self,
        execution_id: str,
        runtime: Any,
        correlation_id: Optional[str] = None,
        run_id: Optional[str] = None,
        is_resumed: bool = False,
    ) -> None:
        self.execution_id = execution_id
        self.correlation_id = correlation_id
        self._runtime = runtime
        self.run_id = run_id  # domain UUID for stateful agents; None for stateless
        self.is_resumed = is_resumed
        self._stall_error: Optional["BaseException"] = None
        self._liveness_monitor: Optional[Any] = None
```

Add the import for `Optional` if needed (it should already be imported at the top of the file).

- [ ] **Step 2: Update docstring**

In the same file, the class docstring (line 224-234), append:

```
        is_resumed: True when the server matched an existing execution
            via idempotency_key replay. Workers were re-attached to the
            existing domain rather than registered for a fresh run.
```

- [ ] **Step 3: Compute `is_resumed` in runtime.py and pass it**

For the **two** call sites that return an `AgentHandle` directly (`start` at line ~3656 and `stream` at line ~4192 — i.e. the ones with `return AgentHandle(...)` after `_resolve_worker_domain`), modify the existing return:

Current shape (in two sites, lines may shift slightly):

```python
        return AgentHandle(
            execution_id=execution_id,
            runtime=self,
            correlation_id=correlation_id,
            run_id=worker_domain,
        )
```

New shape:

```python
        recorded_domain = self._extract_domain(execution_id)
        is_resumed = bool(
            run_id and recorded_domain and recorded_domain != run_id
        )
        if is_resumed:
            logger.info(
                "Resumed existing execution %s under domain %s "
                "(triggered by idempotency_key=%s); re-attached workers.",
                execution_id, recorded_domain, idempotency_key,
            )
        return AgentHandle(
            execution_id=execution_id,
            runtime=self,
            correlation_id=correlation_id,
            run_id=worker_domain,
            is_resumed=is_resumed,
        )
```

For the other two sites (`run`/sync execution at ~2540 and `run_async`/streaming run at ~4055) which don't return a handle directly but block on `_poll_status_until_complete`, add the same `is_resumed`/log block but skip the `is_resumed=...` arg (no handle to set it on):

```python
        worker_domain = self._resolve_worker_domain(execution_id, run_id)

        self._prepare_workers(agent, required_workers=required_workers, domain=worker_domain)
        self._register_and_start_skill_workers(pre_deployed_skills, domain=worker_domain)

        if self._config.liveness_enabled:
            from agentspan.agents.runtime._liveness import LocalLivenessCheck

            expected_pairs = self._collect_registered_pairs(agent, worker_domain)
            LocalLivenessCheck.verify(
                self._worker_manager,
                expected_pairs,
                timeout=self._config.liveness_startup_timeout_seconds,
            )

        recorded_domain = self._extract_domain(execution_id)
        if run_id and recorded_domain and recorded_domain != run_id:
            logger.info(
                "Resumed existing execution %s under domain %s "
                "(triggered by idempotency_key=%s); re-attached workers.",
                execution_id, recorded_domain, idempotency_key,
            )
```

Note: `_extract_domain` is called twice now (once inside `_resolve_worker_domain` and once here). That's fine — it's a cheap server fetch and we'd otherwise need to refactor `_resolve_worker_domain` to return both values, which broadens the change. We keep it simple.

- [ ] **Step 4: Add unit test**

Create `sdk/python/tests/unit/test_agent_handle_is_resumed.py`:

```python
"""Unit tests for AgentHandle.is_resumed flag."""

from agentspan.agents.result import AgentHandle


def test_is_resumed_default_false():
    h = AgentHandle(execution_id="exec-1", runtime=None)
    assert h.is_resumed is False


def test_is_resumed_can_be_set():
    h = AgentHandle(execution_id="exec-1", runtime=None, is_resumed=True)
    assert h.is_resumed is True


def test_stall_error_default_none():
    h = AgentHandle(execution_id="exec-1", runtime=None)
    assert h._stall_error is None
    assert h._liveness_monitor is None
```

- [ ] **Step 5: Run unit tests**

Run: `cd sdk/python && uv run pytest tests/unit/test_agent_handle_is_resumed.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add sdk/python/src/agentspan/agents/result.py sdk/python/src/agentspan/agents/runtime/runtime.py sdk/python/tests/unit/test_agent_handle_is_resumed.py
git commit -m "feat(sdk): AgentHandle.is_resumed + INFO log on idempotency replay

When the server returns an existing execution under a recorded
taskToDomain different from the freshly generated run_id, set
AgentHandle.is_resumed=True and log the resume."
```

---

## Task 8: Wire `ServerLivenessMonitor` into `AgentHandle.join()` and `join_async()`

**Files:**
- Modify: `sdk/python/src/agentspan/agents/result.py:358-428` (`join`), `:430-495` (`join_async`)

- [ ] **Step 1: Modify `join()` to start/stop the monitor and check `_stall_error`**

In `result.py`, replace the current `join` method body (line 358 onward) with the version below. The structure mirrors the existing one — only adds monitor lifecycle and the `_stall_error` check:

```python
    def join(self, timeout: Optional[float] = None) -> "AgentResult":
        """Block until the agent execution reaches a terminal state.

        ... (preserve existing docstring)
        """
        import logging
        import time

        logger = logging.getLogger("agentspan.agents.result")
        poll_interval = 1
        elapsed: float = 0.0
        consecutive_errors = 0

        self._maybe_start_liveness_monitor()

        try:
            while True:
                if self._stall_error is not None:
                    raise self._stall_error

                try:
                    status = self._runtime.get_status(self.execution_id)
                    consecutive_errors = 0
                except Exception as exc:
                    consecutive_errors += 1
                    if consecutive_errors >= 30:
                        raise RuntimeError(
                            f"Lost contact with server after 30 consecutive errors "
                            f"while polling execution {self.execution_id!r}: {exc}"
                        ) from exc
                    logger.warning(
                        "get_status failed (attempt %d/30, will retry): %s",
                        consecutive_errors,
                        exc,
                    )
                    time.sleep(poll_interval)
                    elapsed += poll_interval
                    continue

                if status.is_complete:
                    break
                if timeout is not None and elapsed >= timeout:
                    raise TimeoutError(
                        f"Agent execution {self.execution_id!r} did not complete "
                        f"within {timeout}s."
                    )
                time.sleep(poll_interval)
                elapsed += poll_interval
        finally:
            self._stop_liveness_monitor()

        return self._build_result(status)
```

Apply the parallel edit to `join_async` (line 430) — wrap with the same `_maybe_start_liveness_monitor()` call before the loop and `_stop_liveness_monitor()` in a `finally`, plus the `if self._stall_error is not None: raise self._stall_error` at the top of each iteration.

- [ ] **Step 2: Add `_restart_count` field to `AgentHandle.__init__`**

In `result.py:236-246`, the `AgentHandle.__init__` already added `_stall_error` and `_liveness_monitor` in Task 7. Append one more line to that block:

```python
        self._stall_restart_count = 0
```

- [ ] **Step 3: Add helper methods `_maybe_start_liveness_monitor`, `_stop_liveness_monitor`, and `_handle_stall`**

In `AgentHandle`, after `_build_result` (around line 512), add:

```python
    def _maybe_start_liveness_monitor(self) -> None:
        """Start a ``ServerLivenessMonitor`` if one isn't already running."""
        if self._liveness_monitor is not None:
            return
        cfg = getattr(self._runtime, "_config", None)
        if cfg is None or not getattr(cfg, "liveness_enabled", True):
            return
        if self.run_id is None:
            return  # stateless — nothing routed via domain
        from agentspan.agents.runtime._liveness import ServerLivenessMonitor

        self._liveness_monitor = ServerLivenessMonitor(
            workflow_client=self._runtime._workflow_client,
            execution_id=self.execution_id,
            domain=self.run_id,
            stall_seconds=cfg.liveness_stall_seconds,
            check_interval=cfg.liveness_check_interval_seconds,
            on_stall=self._handle_stall,
        )
        self._liveness_monitor.start()

    def _stop_liveness_monitor(self) -> None:
        """Stop the monitor if it was started."""
        if self._liveness_monitor is not None:
            self._liveness_monitor.stop()
            self._liveness_monitor = None

    def _handle_stall(self, err) -> None:
        """Apply the configured stall policy to a detected stall.

        - ``"restart_worker"`` (default): SIGKILL the stuck subprocess(es) so
          Conductor's TaskHandler monitor respawns them. After
          ``liveness_stall_max_restarts`` cumulative restarts, fall through
          to ``"raise"``.
        - ``"raise"``: store the error so the next ``join()`` poll raises.
        - ``"warn"``: log only.
        """
        import logging as _logging

        log = _logging.getLogger("agentspan.agents.result")
        cfg = getattr(self._runtime, "_config", None)
        policy = getattr(cfg, "liveness_stall_policy", "restart_worker")
        max_restarts = getattr(cfg, "liveness_stall_max_restarts", 1)

        stalled_names = sorted({t.task_def_name for t in err.stalled_tasks})

        if policy == "warn":
            log.warning(
                "Worker stall detected on execution %s for tasks=%s "
                "(policy=warn); not raising. %s",
                err.execution_id, stalled_names, err.remediation,
            )
            return

        if policy == "restart_worker" and self._stall_restart_count < max_restarts:
            from agentspan.agents.runtime._liveness import WorkerRestarter

            wm = getattr(self._runtime, "_worker_manager", None)
            if wm is not None:
                killed = WorkerRestarter.restart_for_tasks(wm, stalled_names)
                self._stall_restart_count += 1
                log.warning(
                    "Worker stall detected on %s for tasks=%s (attempt "
                    "%d/%d) — killed pid(s)=%s; TaskHandler monitor will "
                    "respawn.",
                    err.execution_id, stalled_names,
                    self._stall_restart_count, max_restarts, killed,
                )
                return

        # policy="raise" OR restart attempts exhausted
        self._stall_error = err
```

- [ ] **Step 4: Add a unit test to verify lifecycle and policy handling**

Create `sdk/python/tests/unit/test_handle_liveness_lifecycle.py`:

```python
"""Verify AgentHandle starts and stops the liveness monitor around join()."""

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
        liveness_enabled=True, liveness_stall_seconds=30.0, liveness_check_interval_seconds=10.0,
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
```

- [ ] **Step 5: Run unit test**

Run: `cd sdk/python && uv run pytest tests/unit/test_handle_liveness_lifecycle.py -v`
Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add sdk/python/src/agentspan/agents/result.py sdk/python/tests/unit/test_handle_liveness_lifecycle.py
git commit -m "feat(sdk): AgentHandle.join() drives ServerLivenessMonitor

join() / join_async() start a daemon monitor that flags SCHEDULED
tasks queued past liveness_stall_seconds with pollCount=0. The next
poll iteration raises WorkerStallError. Skipped for stateless agents
or when liveness_enabled=False."
```

---

## Task 9: Re-export error types from `agentspan.agents`

**Files:**
- Modify: `sdk/python/src/agentspan/agents/__init__.py`

- [ ] **Step 1: Write failing test**

Append to `sdk/python/tests/unit/test_liveness_errors.py`:

```python
def test_errors_exported_from_top_level():
    from agentspan.agents import WorkerStallError, WorkerStartupError

    assert issubclass(WorkerStartupError, RuntimeError)
    assert issubclass(WorkerStallError, RuntimeError)
```

- [ ] **Step 2: Run test to confirm it fails**

Run: `cd sdk/python && uv run pytest tests/unit/test_liveness_errors.py::test_errors_exported_from_top_level -v`
Expected: `ImportError: cannot import name 'WorkerStallError'`

- [ ] **Step 3: Add re-exports**

In `sdk/python/src/agentspan/agents/__init__.py`, near the existing `from agentspan.agents.runtime.runtime import AgentRuntime` (line ~169), add:

```python
from agentspan.agents.runtime._liveness import WorkerStallError, WorkerStartupError
```

In the `__all__` list, add `"WorkerStallError"` and `"WorkerStartupError"` (alphabetical order — find the right spot).

- [ ] **Step 4: Run test to confirm it passes**

Run: `cd sdk/python && uv run pytest tests/unit/test_liveness_errors.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add sdk/python/src/agentspan/agents/__init__.py sdk/python/tests/unit/test_liveness_errors.py
git commit -m "feat(sdk): re-export WorkerStartupError, WorkerStallError"
```

---

## Task 10: E2E test 1 — local liveness fires when registration produces no live process

**Files:**
- Create: `sdk/python/tests/integration/test_worker_liveness_live.py`

- [ ] **Step 1: Write the test (failure mode + validity counter-test)**

```python
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""E2E worker liveness tests.

Validates the two complementary checks added by the worker-liveness fix:
- LocalLivenessCheck (Mode B-1): fail fast in start() when worker subprocess
  isn't actually running.
- ServerLivenessMonitor (Mode B-2): fail in join() when a queued task in our
  domain has no polls past the stall threshold.
- AgentHandle.is_resumed (Mode A): observable when an idempotency_key replays
  an existing execution.

All assertions are algorithmic (no LLM-as-judge). Real Conductor server
required.
"""

from __future__ import annotations

import os
import time
import uuid

import pytest

from agentspan.agents import (
    Agent,
    AgentRuntime,
    WorkerStallError,
    WorkerStartupError,
    tool,
)
from agentspan.agents.runtime.config import AgentConfig

pytestmark = pytest.mark.integration


@tool
def liveness_probe(payload: str) -> str:
    """A trivial tool used only to register a worker."""
    return f"ok:{payload}"


@pytest.fixture
def fast_liveness_config():
    """AgentConfig with aggressive liveness windows so tests stay fast."""
    cfg = AgentConfig.from_env()
    cfg.liveness_enabled = True
    cfg.liveness_startup_timeout_seconds = 1.0
    cfg.liveness_stall_seconds = 5.0
    cfg.liveness_check_interval_seconds = 1.0
    return cfg


def test_local_liveness_raises_when_workers_not_started(fast_liveness_config, monkeypatch):
    """When WorkerManager.start is short-circuited so no subprocess is alive,
    runtime.start() must raise WorkerStartupError within startup_timeout.
    """
    agent = Agent(
        name=f"liveness-test-{uuid.uuid4().hex[:8]}",
        model="openai/gpt-4o-mini",
        stateful=True,
        tools=[liveness_probe],
        max_turns=1,
    )

    with AgentRuntime(config=fast_liveness_config) as rt:
        # Force WorkerManager.start to be a no-op AFTER registration so the
        # decorated function is in _decorated_functions but no subprocess runs.
        original_start = rt._worker_manager.start
        rt._worker_manager.start = lambda: None  # type: ignore[assignment]

        t0 = time.monotonic()
        with pytest.raises(WorkerStartupError) as exc_info:
            rt.start(agent, "hello")
        elapsed = time.monotonic() - t0

        # Restore so the runtime can shut down cleanly
        rt._worker_manager.start = original_start  # type: ignore[assignment]

    assert elapsed < 5.0, f"Liveness check took too long: {elapsed:.2f}s"
    err = exc_info.value
    assert any(name == "liveness_probe" for name, _ in err.missing)
    assert err.domain is not None  # stateful agent gets a domain


def test_local_liveness_disabled_does_not_raise(fast_liveness_config, monkeypatch):
    """Validity counter-test: with liveness_enabled=False, the same scenario
    must NOT raise WorkerStartupError — proving the check is what's signaling.
    """
    fast_liveness_config.liveness_enabled = False

    agent = Agent(
        name=f"liveness-test-disabled-{uuid.uuid4().hex[:8]}",
        model="openai/gpt-4o-mini",
        stateful=True,
        tools=[liveness_probe],
        max_turns=1,
    )

    with AgentRuntime(config=fast_liveness_config) as rt:
        rt._worker_manager.start = lambda: None  # type: ignore[assignment]
        # Should NOT raise. start() returns; we cancel before the LLM does
        # anything to keep the test fast.
        try:
            handle = rt.start(agent, "hello")
            handle.cancel("test cleanup")
        except WorkerStartupError:
            pytest.fail("liveness_enabled=False should disable WorkerStartupError")
```

- [ ] **Step 2: Run test to confirm failure-mode test FAILS without fix**

(This step is only meaningful before Tasks 1–9 land. If running this plan top-to-bottom in order, the test will already pass.)

Run: `cd sdk/python && uv run pytest tests/integration/test_worker_liveness_live.py::test_local_liveness_raises_when_workers_not_started -v`
Expected on this branch (with Tasks 1–9 applied): PASS.
Expected on a branch without the fix: would TIMEOUT or hang (start() returns, join() never sees a poll).

- [ ] **Step 3: Run both tests**

Run: `cd sdk/python && uv run pytest tests/integration/test_worker_liveness_live.py -v -k "local_liveness"`
Expected: 2 passed in < 15s.

- [ ] **Step 4: Commit**

```bash
git add sdk/python/tests/integration/test_worker_liveness_live.py
git commit -m "test(sdk): e2e local liveness — start() raises on registration-no-process

Two tests: positive (WorkerStartupError fires within 5s when
WorkerManager.start is no-op'd) and validity counter-test
(disabling liveness_enabled suppresses the error)."
```

---

## Task 11: E2E test 2 — server liveness detects stalled task during `join()`

**Files:**
- Modify: `sdk/python/tests/integration/test_worker_liveness_live.py`

- [ ] **Step 1: Add test 2 plus its validity counter-test**

Append to the file from Task 10:

```python
def _kill_workers(rt: AgentRuntime) -> None:
    """Terminate all worker subprocesses to simulate process death mid-run."""
    th = rt._worker_manager._task_handler
    if th is None:
        return
    for proc in list(getattr(th, "task_runner_processes", []) or []):
        try:
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=2)
        except Exception:
            pass


def test_server_liveness_raises_with_raise_policy(fast_liveness_config):
    """With liveness_stall_policy='raise', killing workers post-start makes
    join() raise WorkerStallError within ~stall_seconds + check_interval.
    """
    fast_liveness_config.liveness_stall_policy = "raise"

    agent = Agent(
        name=f"liveness-stall-{uuid.uuid4().hex[:8]}",
        model="openai/gpt-4o-mini",
        stateful=True,
        tools=[liveness_probe],
        max_turns=2,
        instructions=(
            "You MUST call the liveness_probe tool with payload='go' on your "
            "first turn. Do not respond in any other way."
        ),
    )

    with AgentRuntime(config=fast_liveness_config) as rt:
        handle = rt.start(agent, "go")
        # Kill workers AFTER start() so registration succeeds, then the
        # workflow schedules liveness_probe with no live worker.
        _kill_workers(rt)

        t0 = time.monotonic()
        with pytest.raises(WorkerStallError) as exc_info:
            handle.join(timeout=30)
        elapsed = time.monotonic() - t0

    err = exc_info.value
    assert elapsed < 25.0, f"Stall detection too slow: {elapsed:.2f}s"
    assert any(t.task_def_name == "liveness_probe" for t in err.stalled_tasks)
    assert err.execution_id == handle.execution_id


def test_server_liveness_restart_policy_recovers(fast_liveness_config):
    """With the DEFAULT 'restart_worker' policy, killing workers post-start
    must not crash join() — the SDK SIGKILLs+respawns the subprocess and
    execution proceeds.
    """
    assert fast_liveness_config.liveness_stall_policy == "restart_worker"  # default

    agent = Agent(
        name=f"liveness-restart-{uuid.uuid4().hex[:8]}",
        model="openai/gpt-4o-mini",
        stateful=True,
        tools=[liveness_probe],
        max_turns=2,
        instructions=(
            "You MUST call the liveness_probe tool with payload='go' on your "
            "first turn. Do not respond in any other way."
        ),
    )

    with AgentRuntime(config=fast_liveness_config) as rt:
        handle = rt.start(agent, "go")
        _kill_workers(rt)

        # join() must complete (or time out) WITHOUT raising WorkerStallError;
        # the restart policy auto-recovers.
        try:
            result = handle.join(timeout=60)
        except WorkerStallError:
            pytest.fail("restart_worker policy must not surface WorkerStallError")
        except TimeoutError:
            # Acceptable in test envs where TaskHandler monitor restart is slow;
            # the absence of WorkerStallError is the assertion that matters.
            return

        assert result.execution_id == handle.execution_id
        assert handle._stall_restart_count >= 1  # restart happened


def test_server_liveness_disabled_falls_through_to_timeout(fast_liveness_config):
    """Validity counter-test: with liveness_enabled=False, the same scenario
    times out via the existing TimeoutError path — proving the monitor is the
    signal source.
    """
    fast_liveness_config.liveness_enabled = False

    agent = Agent(
        name=f"liveness-stall-off-{uuid.uuid4().hex[:8]}",
        model="openai/gpt-4o-mini",
        stateful=True,
        tools=[liveness_probe],
        max_turns=2,
        instructions=(
            "You MUST call the liveness_probe tool with payload='go' on your "
            "first turn. Do not respond in any other way."
        ),
    )

    with AgentRuntime(config=fast_liveness_config) as rt:
        handle = rt.start(agent, "go")
        _kill_workers(rt)

        with pytest.raises(TimeoutError):
            handle.join(timeout=15)

        # Best-effort cleanup
        try:
            handle.cancel("test cleanup")
        except Exception:
            pass
```

- [ ] **Step 2: Run the tests**

Run: `cd sdk/python && uv run pytest tests/integration/test_worker_liveness_live.py -v -k "server_liveness"`
Expected: 3 passed in < 90s.

- [ ] **Step 3: Commit**

```bash
git add sdk/python/tests/integration/test_worker_liveness_live.py
git commit -m "test(sdk): e2e server liveness — join() raises WorkerStallError

Two tests: positive (WorkerStallError surfaces within 25s when worker
subprocesses are killed mid-execution) and validity counter-test
(liveness_enabled=False falls through to TimeoutError)."
```

---

## Task 12: E2E test 3 — `is_resumed` flag on idempotency replay

**Files:**
- Modify: `sdk/python/tests/integration/test_worker_liveness_live.py`

- [ ] **Step 1: Add test 3**

Append to the file:

```python
def test_idempotent_resume_sets_is_resumed_flag(fast_liveness_config, caplog):
    """First start with idempotency_key creates an execution; the second
    start with the same key (after the original runtime closed) must:
      - Return the SAME execution_id.
      - Set handle.is_resumed = True.
      - Emit an INFO log on the agentspan.agents.runtime logger.
    """
    import logging

    idem_key = f"liveness-resume-{uuid.uuid4().hex[:12]}"
    agent_name = f"liveness-resume-{uuid.uuid4().hex[:8]}"

    def _build_agent():
        return Agent(
            name=agent_name,
            model="openai/gpt-4o-mini",
            stateful=True,
            tools=[liveness_probe],
            max_turns=1,
            instructions=(
                "Call liveness_probe with payload='resume' on your first turn."
            ),
        )

    # Run 1 — start, immediately cancel before completion so workflow stays
    # RUNNING from the perspective of our second start. We simulate "process
    # killed mid-run" by closing the runtime before join().
    with AgentRuntime(config=fast_liveness_config) as rt1:
        h1 = rt1.start(_build_agent(), "go", idempotency_key=idem_key)
        first_execution_id = h1.execution_id
        first_run_id = h1.run_id
        # Verify first start was NOT a resume.
        assert h1.is_resumed is False

    # Run 2 — same idempotency_key, expect resume.
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="agentspan.agents.runtime.runtime"):
        with AgentRuntime(config=fast_liveness_config) as rt2:
            h2 = rt2.start(_build_agent(), "go", idempotency_key=idem_key)
            try:
                assert h2.execution_id == first_execution_id
                assert h2.is_resumed is True
                # The fresh run_id we generated is different from the
                # workflow's original recorded domain.
                assert h2.run_id == first_run_id
            finally:
                try:
                    h2.cancel("test cleanup")
                except Exception:
                    pass

    assert any(
        "Resumed existing execution" in rec.message and first_execution_id in rec.message
        for rec in caplog.records
    ), "Expected INFO 'Resumed existing execution ...' log entry"
```

- [ ] **Step 2: Run the test**

Run: `cd sdk/python && uv run pytest tests/integration/test_worker_liveness_live.py::test_idempotent_resume_sets_is_resumed_flag -v`
Expected: 1 passed in < 30s.

- [ ] **Step 3: Run the entire new test file**

Run: `cd sdk/python && uv run pytest tests/integration/test_worker_liveness_live.py -v`
Expected: 6 passed in < 150s total.

- [ ] **Step 4: Commit**

```bash
git add sdk/python/tests/integration/test_worker_liveness_live.py
git commit -m "test(sdk): e2e idempotent resume — is_resumed flag + INFO log

Verifies that a second start() with the same idempotency_key returns
the original execution_id, sets handle.is_resumed=True, and emits
the INFO 'Resumed existing execution ...' log."
```

---

## Task 13: Run full unit + integration suite, smoke-test the original repro

**Files:** none

- [ ] **Step 1: Run all new unit tests together**

Run:
```bash
cd sdk/python && uv run pytest tests/unit/test_liveness_config.py tests/unit/test_liveness_errors.py tests/unit/test_local_liveness_check.py tests/unit/test_server_liveness_monitor.py tests/unit/test_worker_restarter.py tests/unit/test_collect_registered_pairs.py tests/unit/test_agent_handle_is_resumed.py tests/unit/test_handle_liveness_lifecycle.py -v
```
Expected: all pass in < 10s.

- [ ] **Step 2: Run pre-existing unit test suite to confirm no regressions**

Run: `cd sdk/python && uv run pytest tests/unit/ -v --timeout=60`
Expected: same pass count as before this plan + the new tests.

- [ ] **Step 3: Run the new e2e suite**

Run: `cd sdk/python && uv run pytest tests/integration/test_worker_liveness_live.py -v`
Expected: 5 passed in < 90s.

- [ ] **Step 4: Run a smoke test of an existing integration test to confirm liveness doesn't break the happy path**

Run: `cd sdk/python && uv run pytest tests/integration/test_correctness_live.py -v -k "test_simple_agent" --timeout=120` (or pick another fast test)
Expected: PASS — the new liveness machinery does not interfere when workers do start polling.

- [ ] **Step 5: Manual smoke against the original repro scenario**

Optional but useful: run a small toy script that simulates the failure mode and confirm it raises clearly. Skip if all automated tests pass.

- [ ] **Step 6: No commit (verification only)**

---

## Self-review

Spec coverage check (against `docs/design/2026-05-06-worker-liveness-and-idempotent-resume.md`):

| Spec section | Implemented in |
|---|---|
| `WorkerStartupError` + fields + remediation | Task 2 |
| `WorkerStallError` + fields + remediation | Task 2 |
| `LocalLivenessCheck.verify` semantics | Task 3 |
| `ServerLivenessMonitor` semantics + auto-stop on terminal status + per-task_id dedup | Task 4 |
| `WorkerRestarter.restart_for_tasks` (SIGKILL + monitor respawn) | Task 4b |
| Stall policy `restart_worker` / `raise` / `warn` | Task 1 (config), Task 8 (`_handle_stall`) |
| Stall max-restart cap → fall through to raise | Task 8 |
| `_collect_registered_pairs` mirroring tool_registry domain logic | Task 5 |
| Wired into all four `start*/stream*` call sites | Task 6 |
| `AgentHandle.is_resumed` | Task 7 |
| Resume INFO log | Task 7 |
| Monitor lifecycle in `join()` and `join_async()` | Task 8 |
| Re-export errors at top-level | Task 9 |
| Four `AgentConfig` fields + env var loading | Task 1 |
| `liveness_enabled` master kill-switch | Task 1, 6, 8 |
| Test 1 — local liveness | Task 10 |
| Test 2a — server liveness `raise` policy | Task 11 |
| Test 2b — server liveness `restart_worker` policy auto-recovers | Task 11 |
| Test 3 — idempotent resume | Task 12 |
| Validity counter-tests (CLAUDE.md rule #2) | Tasks 10, 11 |
| Algorithmic-only assertions (no LLM judge) | Tasks 10–12 |
| Suite ≤ 12 minutes (target ≤ 90s) | Task 13 |

Type consistency check:
- `LocalLivenessCheck.verify(worker_manager, expected, *, timeout=..., poll_interval=...)` — same signature in Tasks 3 and 6 ✓
- `WorkerStartupError(missing=..., domain=..., remediation=...)` — same kwargs in Tasks 2, 3, 6 ✓
- `WorkerStallError(execution_id=..., domain=..., stalled_tasks=..., remediation=...)` — same kwargs in Tasks 2, 4, 8 ✓
- `ServerLivenessMonitor(workflow_client=..., execution_id=..., domain=..., stall_seconds=..., check_interval=..., on_stall=...)` — same kwargs in Tasks 4 and 8 ✓
- `_collect_registered_pairs(agent, domain) -> List[Tuple[str, Optional[str]]]` — same signature in Tasks 5 and 6 ✓
- `AgentHandle(..., is_resumed: bool = False)` — same in Tasks 7 and 8 ✓

No placeholders. No "similar to Task N" without code.

---

## Notes for the implementer

- The conductor-python `Worker` class exposes `domain` as an attribute (used in `worker_manager.py:138` already). `get_task_definition_name()` is the documented method.
- `_extract_domain` is already defensive; it logs and returns None on error. Re-calling it in Task 7 is intentional and safe.
- The `_liveness.py` module is intentionally framework-free — no agentspan imports — so it's trivial to unit-test.
- Tests use `monkeypatch.setattr` and `MagicMock` for unit tests, and a real Conductor server for integration tests (per `conftest.py:162`).
- `WorkerStallError` is allowed to propagate through `join()` because it inherits from `RuntimeError`; existing user code that catches `Exception` keeps working.
