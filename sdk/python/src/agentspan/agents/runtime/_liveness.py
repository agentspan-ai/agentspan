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
from dataclasses import dataclass
from typing import (
    Callable,
    Iterable,
    List,
    Optional,
    Tuple,
)

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
