# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""TaskManager — register, run, and inspect long-running background work.

v1 scope: in-process tracking. Background tasks survive foreground-turn
interruption (the parent abort signal is *not* propagated unless the
task is explicitly linked) but do NOT survive a parent process crash.

Design §12 calls for Conductor-backed durability for true crash recovery
of background tasks; that's a follow-on. The TaskManager interface is
shaped so it can swap a Conductor backend in transparently.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger("agentspan.harness.tasks")


@dataclass
class TaskState:
    """Public state of a task. Read via ``TaskManager.get(task_id)``."""

    id: str
    type: str  # "shell" | "agent" | "remote" | "workflow"
    status: str  # "pending" | "running" | "completed" | "failed" | "killed"
    description: str
    start_time: float
    end_time: Optional[float] = None
    output_file: Optional[str] = None
    tool_use_id: Optional[str] = None
    summary: Optional[str] = None
    notified: bool = False
    error: Optional[str] = None


@dataclass
class _Registration:
    state: TaskState
    handle: Optional[asyncio.Task] = None
    abort: asyncio.Event = field(default_factory=asyncio.Event)
    on_complete: List[Callable[[TaskState], None]] = field(default_factory=list)
    kill_callback: Optional[Callable[[], Awaitable[None]]] = None


class TaskManager:
    """Track background tasks for the harness.

    Methods:
      ``register(task_type, description, runner)`` → spawns the runner as
        an asyncio Task and returns its TaskState.
      ``register_external(task_type, description, kill_callback)`` →
        registers a task running outside the harness process (e.g. a
        Conductor SUB_WORKFLOW), exposed for inspection but not awaited.
      ``get(task_id)`` → current TaskState or None.
      ``list()`` → all known tasks.
      ``kill(task_id)`` → request termination; runner observes the abort
        signal and ``kill_callback`` runs if registered.
      ``read_output(task_id, offset)`` → tail the task log.
    """

    def __init__(self) -> None:
        self._tasks: Dict[str, _Registration] = {}
        self._lock = asyncio.Lock()

    # ── Registration ─────────────────────────────────────────────────

    async def register(
        self,
        *,
        task_type: str,
        description: str,
        runner: Callable[[asyncio.Event], Awaitable[Dict[str, Any]]],
        tool_use_id: Optional[str] = None,
        output_file: Optional[str] = None,
    ) -> TaskState:
        """Spawn an asyncio task running ``runner(abort_event)``. The runner's
        return value (a dict) becomes the TaskState ``summary``.

        Exceptions in the runner mark the task ``failed``. ``KeyboardInterrupt``
        and ``CancelledError`` mark it ``killed``.
        """
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        reg = _Registration(
            state=TaskState(
                id=task_id,
                type=task_type,
                status="running",
                description=description,
                start_time=time.time(),
                output_file=output_file,
                tool_use_id=tool_use_id,
            ),
        )

        async def _wrapped() -> None:
            try:
                summary = await runner(reg.abort)
                reg.state.status = "completed"
                reg.state.summary = _summarize(summary)
            except asyncio.CancelledError:
                reg.state.status = "killed"
                raise
            except Exception as exc:  # noqa: BLE001
                logger.exception("task %s failed", task_id)
                reg.state.status = "failed"
                reg.state.error = f"{type(exc).__name__}: {exc}"
            finally:
                reg.state.end_time = time.time()
                # Fire completion callbacks outside the state-update path.
                for cb in list(reg.on_complete):
                    try:
                        cb(reg.state)
                    except Exception:  # noqa: BLE001
                        logger.exception("on_complete callback raised")

        async with self._lock:
            self._tasks[task_id] = reg

        reg.handle = asyncio.create_task(_wrapped(), name=f"harness-task:{task_id}")
        return reg.state

    async def register_external(
        self,
        *,
        task_type: str,
        description: str,
        kill_callback: Optional[Callable[[], Awaitable[None]]] = None,
        output_file: Optional[str] = None,
        tool_use_id: Optional[str] = None,
    ) -> TaskState:
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        reg = _Registration(
            state=TaskState(
                id=task_id,
                type=task_type,
                status="running",
                description=description,
                start_time=time.time(),
                output_file=output_file,
                tool_use_id=tool_use_id,
            ),
            kill_callback=kill_callback,
        )
        async with self._lock:
            self._tasks[task_id] = reg
        return reg.state

    # ── Inspection ───────────────────────────────────────────────────

    def get(self, task_id: str) -> Optional[TaskState]:
        reg = self._tasks.get(task_id)
        return reg.state if reg else None

    def list(self) -> List[TaskState]:
        return [r.state for r in self._tasks.values()]

    def on_complete(self, task_id: str, callback: Callable[[TaskState], None]) -> bool:
        reg = self._tasks.get(task_id)
        if reg is None:
            return False
        if reg.state.status in ("completed", "failed", "killed"):
            try:
                callback(reg.state)
            except Exception:  # noqa: BLE001
                logger.exception("on_complete callback raised")
            return True
        reg.on_complete.append(callback)
        return True

    # ── Termination ──────────────────────────────────────────────────

    async def kill(self, task_id: str) -> bool:
        reg = self._tasks.get(task_id)
        if reg is None:
            return False
        if reg.state.status not in ("running", "pending"):
            return False
        reg.abort.set()
        if reg.kill_callback is not None:
            try:
                await reg.kill_callback()
            except Exception:  # noqa: BLE001
                logger.exception("kill_callback raised for %s", task_id)
        if reg.handle is not None:
            reg.handle.cancel()
            try:
                await reg.handle
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        if reg.state.status == "running":
            reg.state.status = "killed"
            reg.state.end_time = time.time()
        return True

    async def kill_all(self) -> None:
        for tid in list(self._tasks):
            await self.kill(tid)

    # ── Output ───────────────────────────────────────────────────────

    def read_output(self, task_id: str, offset: int = 0, max_bytes: int = 65536) -> Dict[str, Any]:
        """Read a chunk of the task's output log.

        Returns ``{"content": <text>, "next_offset": <int>, "eof": <bool>}``.
        """
        reg = self._tasks.get(task_id)
        if reg is None:
            return {"error": f"unknown task: {task_id}"}
        path = reg.state.output_file
        if not path:
            return {"error": f"task {task_id} has no output file"}
        try:
            size = 0
            try:
                size = __import__("os").path.getsize(path)
            except OSError:
                size = 0
            with open(path, "rb") as fp:
                fp.seek(offset)
                data = fp.read(max_bytes)
            content = data.decode("utf-8", errors="replace")
            return {
                "content": content,
                "next_offset": offset + len(data),
                "eof": offset + len(data) >= size and reg.state.status != "running",
                "task_status": reg.state.status,
            }
        except OSError as exc:
            return {"error": f"read failed: {exc}"}


def _summarize(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value[:500]
    try:
        import json

        return json.dumps(value, default=str)[:500]
    except Exception:  # noqa: BLE001
        return str(value)[:500]
