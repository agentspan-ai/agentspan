# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Shared fixtures for integration tests.

Provides a module-scoped AgentRuntime and a configurable LLM model.

SSE streaming is enabled by default. Disable explicitly with
``AGENTSPAN_STREAMING_ENABLED=false`` if the server does not support SSE.
"""

import os
import signal
import threading
import time

import pytest
import requests

from agentspan.agents import AgentRuntime
from agentspan.agents.runtime.config import AgentConfig

DEFAULT_MODEL = os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o-mini")
_SERVER_URL = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")


def _conductor_base() -> str:
    return _SERVER_URL.rstrip("/").replace("/api", "")


@pytest.fixture(scope="session", autouse=True)
def cleanup_running_workflows():
    """Terminate leftover running workflows before the test session starts."""
    try:
        base = _conductor_base()
        resp = requests.get(
            f"{base}/api/workflow/search",
            params={"query": "status IN (RUNNING)", "size": 200},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        for r in results:
            requests.post(
                f"{base}/api/workflow/{r['workflowId']}/terminate", timeout=5
            )
        if results:
            time.sleep(2)
    except Exception:
        pass


class _WorkerWatchdog:
    """Background thread that kills deadlocked worker processes.

    On macOS, forking from a multi-threaded process randomly deadlocks
    Objective-C runtime locks.  The deadlocked process is "alive" so the
    Conductor monitor never restarts it.  Tasks pile up in the queue with
    pollCount=0.

    This watchdog:
    1. Polls the Conductor task queue every POLL_SEC seconds.
    2. For each task type with ≥1 SCHEDULED task that hasn't been polled
       in STUCK_SEC seconds, looks up the worker process responsible for
       that task type.
    3. SIGKILLs the stuck process; the TaskHandler monitor then spawns a
       fresh replacement.
    """

    POLL_SEC = 5
    STUCK_SEC = 30  # seconds a queue entry can sit with 0 polls before we act

    def __init__(self, runtime: "AgentRuntime") -> None:
        self._runtime = runtime
        self._stop = threading.Event()
        self._seen_since: dict = {}  # task_type → (count, first_seen_ts)
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="WatchdogThread"
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _worker_map(self) -> "dict[str, int]":
        """Return {task_type: pid} for all live worker processes."""
        wm = getattr(self._runtime, "_worker_manager", None)
        if wm is None:
            return {}
        th = getattr(wm, "_task_handler", None)
        if th is None:
            return {}
        workers = getattr(th, "workers", [])
        procs = getattr(th, "task_runner_processes", [])
        result = {}
        for w, p in zip(workers, procs):
            if p is not None and p.is_alive():
                try:
                    task_name = w.get_task_definition_name()
                    pid = getattr(p, "pid", None)
                    if pid:
                        result[task_name] = pid
                except Exception:
                    pass
        return result

    def _queue_counts(self) -> "dict[str, int]":
        """Return {task_type: queue_depth} for non-empty queues."""
        try:
            base = _conductor_base()
            resp = requests.get(
                f"{base}/api/tasks/queue/all", timeout=5
            )
            resp.raise_for_status()
            return {k: v for k, v in resp.json().items() if v > 0}
        except Exception:
            return {}

    def _loop(self) -> None:
        while not self._stop.wait(self.POLL_SEC):
            try:
                self._check()
            except Exception:
                pass

    def _check(self) -> None:
        now = time.monotonic()
        queues = self._queue_counts()
        wmap = self._worker_map()

        for task_type, depth in queues.items():
            if task_type not in wmap:
                continue  # not our worker — skip

            prev = self._seen_since.get(task_type)
            if prev is None:
                self._seen_since[task_type] = (depth, now)
                continue

            prev_depth, first_seen = prev
            if depth > 0 and (now - first_seen) > self.STUCK_SEC:
                # Tasks have been waiting too long — the worker is stuck.
                pid = wmap[task_type]
                try:
                    os.kill(pid, signal.SIGKILL)
                    import logging
                    logging.getLogger("agentspan.test.watchdog").warning(
                        "Killed stuck worker pid=%s for task_type=%s "
                        "(queue_depth=%s, stuck=%.0fs)",
                        pid, task_type, depth, now - first_seen,
                    )
                except ProcessLookupError:
                    pass  # already dead — monitor will restart
                del self._seen_since[task_type]  # reset after kill
            elif depth == 0:
                self._seen_since.pop(task_type, None)  # cleared — reset
            # else: still queued but within grace period — keep watching


@pytest.fixture(scope="module")
def runtime():
    """Module-scoped AgentRuntime with a watchdog that kills deadlocked workers.

    On macOS, fork() from a multi-threaded process can deadlock.  The
    watchdog detects tasks that sit unpolled for >30 s and SIGKILLs the
    responsible worker process so the TaskHandler monitor can restart it.
    """
    config = AgentConfig.from_env()
    with AgentRuntime(config=config) as rt:
        watchdog = _WorkerWatchdog(rt)
        watchdog.start()
        try:
            yield rt
        finally:
            watchdog.stop()


@pytest.fixture
def model():
    """LLM model string, overridable via AGENTSPAN_LLM_MODEL env var."""
    return DEFAULT_MODEL
