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
import time  # noqa: F401 — used in subsequent tasks
from dataclasses import dataclass, field  # noqa: F401 — field used in subsequent tasks
from typing import List, Optional, Tuple

# isort: split
from typing import Callable, Iterable  # noqa: F401 — used in subsequent tasks

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
