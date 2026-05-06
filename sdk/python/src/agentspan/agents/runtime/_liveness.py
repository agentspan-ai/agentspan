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
import threading  # noqa: F401 — used in subsequent tasks
import time
from dataclasses import dataclass, field  # noqa: F401 — field used in subsequent tasks
from typing import (  # noqa: F401 — Callable unused until next task
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
