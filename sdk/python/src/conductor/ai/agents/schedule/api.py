# Copyright (c) 2026 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Module-level lifecycle API for schedules.

Lifecycle calls are keyed by the **wire name** (the prefixed identifier
returned by :func:`list`). The user-supplied short name is only used at
:func:`Schedule` construction time; once the schedule lands on the server,
it's identified by its prefixed wire name.

Each function accepts an optional ``runtime=`` kwarg; if omitted, the
default singleton runtime is used.
"""

from __future__ import annotations

import time
from typing import Any, List, Optional

from conductor.ai.agents.schedule.schedule import Schedule, ScheduleInfo


def _client(runtime: Optional[Any]) -> Any:
    if runtime is not None:
        return runtime.schedules_client()
    from conductor.ai.agents.run import _get_default_runtime

    return _get_default_runtime().schedules_client()


def list(  # noqa: A001 — module-level API mirrors the spec
    agent: str, *, runtime: Optional[Any] = None
) -> List[ScheduleInfo]:
    """List all schedules attached to ``agent`` (workflow name)."""
    return _client(runtime).list_for_agent(agent)


def get(name: str, *, runtime: Optional[Any] = None) -> ScheduleInfo:
    """Fetch a single schedule by its wire name.

    The agent is recovered from the schedule's ``startWorkflowRequest.name``;
    ``short_name`` on the returned :class:`ScheduleInfo` is the user's original.
    """
    return _client(runtime).get(name)


def pause(name: str, reason: Optional[str] = None, *, runtime: Optional[Any] = None) -> None:
    """Pause the schedule. ``reason`` is sent as ``?reason=...`` query param."""
    _client(runtime).pause(name, reason=reason)


def resume(name: str, *, runtime: Optional[Any] = None) -> None:
    _client(runtime).resume(name)


def delete(name: str, *, runtime: Optional[Any] = None) -> None:
    _client(runtime).delete(name)


def run_now(
    name: str,
    *,
    wait: bool = False,
    timeout: float = 600.0,
    poll_interval: float = 1.0,
    runtime: Optional[Any] = None,
) -> Any:
    """Fire the schedule's agent once with the schedule's stored input.

    Returns the workflow execution id immediately (non-blocking by default).
    If ``wait=True``, blocks until the workflow reaches a terminal state and
    returns an :class:`AgentResult` (raises ``TimeoutError`` after ``timeout``
    seconds) — consistent with ``run()``'s completed-workflow result.
    """
    client = _client(runtime)
    info = client.get(name)
    execution_id = client.run_now(info)
    if not wait:
        return execution_id

    rt = runtime
    if rt is None:
        from conductor.ai.agents.run import _get_default_runtime

        rt = _get_default_runtime()
    wc = rt._workflow_client
    deadline = time.monotonic() + timeout
    while True:
        wf = wc.get_workflow_status(workflow_id=execution_id, include_output=True)
        status = getattr(wf, "status", None)
        if status in ("COMPLETED", "FAILED", "TERMINATED", "TIMED_OUT"):
            # Reuse the runtime's completed-workflow → AgentResult extraction
            # (same conversion `run()` uses) rather than returning the raw
            # workflow-status object.
            return rt._build_result_from_workflow(wf, execution_id)
        if time.monotonic() > deadline:
            raise TimeoutError(f"run_now({name!r}) did not finish within {timeout}s")
        time.sleep(poll_interval)


def preview_next(
    cron: str,
    n: int = 5,
    *,
    start_at: Optional[int] = None,
    end_at: Optional[int] = None,
    runtime: Optional[Any] = None,
) -> List[int]:
    """Return the next ``n`` epoch-ms fire times for ``cron``.

    Used by the UI's cron-editor preview.
    """
    return _client(runtime).preview_next(cron, n=n, start_at=start_at, end_at=end_at)


def save(schedule: Schedule, agent: str, *, runtime: Optional[Any] = None) -> None:
    """Upsert a single schedule without going through :func:`deploy`.

    Useful for ad-hoc creation from the UI / scripts. Most users should
    prefer the declarative ``deploy(agent, schedules=[...])`` flow.
    """
    _client(runtime).save(schedule, agent)
