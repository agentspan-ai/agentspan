# Copyright (c) 2026 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Bridge between :class:`Schedule` and Conductor's ``SchedulerClient``.

Handles:
- payload mapping (Schedule -> SaveScheduleRequest, WorkflowSchedule -> ScheduleInfo)
- wire-name prefixing (``{agent}-{short_name}``)
- declarative reconciliation on deploy
- typed error translation
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, List, Optional

from conductor.ai.agents.schedule.errors import (
    InvalidCronExpression,
    ScheduleNameConflict,
    ScheduleNotFound,
)
from conductor.ai.agents.schedule.schedule import (
    Schedule,
    ScheduleInfo,
    _prefix,
    _unprefix,
)

logger = logging.getLogger("conductor.ai.agents.schedule")


def _to_save_request(schedule: Schedule, agent_name: str) -> Any:
    """Build a conductor-python ``SaveScheduleRequest`` from a Schedule."""
    from conductor.client.http.models.save_schedule_request import SaveScheduleRequest
    from conductor.client.http.models.start_workflow_request import StartWorkflowRequest

    swr = StartWorkflowRequest(
        name=agent_name,
        input=dict(schedule.input) if schedule.input else {},
    )
    return SaveScheduleRequest(
        name=_prefix(agent_name, schedule.name),
        cron_expression=schedule.cron,
        zone_id=schedule.timezone,
        run_catchup_schedule_instances=schedule.catchup,
        paused=schedule.paused,
        schedule_start_time=schedule.start_at,
        schedule_end_time=schedule.end_at,
        description=schedule.description,
        start_workflow_request=swr,
    )


_DICT_KEY_MAP = {
    "name": ("name",),
    "cron_expression": ("cron_expression", "cronExpression"),
    "zone_id": ("zone_id", "zoneId"),
    "paused": ("paused",),
    "paused_reason": ("paused_reason", "pausedReason"),
    "run_catchup_schedule_instances": (
        "run_catchup_schedule_instances",
        "runCatchupScheduleInstances",
    ),
    "schedule_start_time": ("schedule_start_time", "scheduleStartTime"),
    "schedule_end_time": ("schedule_end_time", "scheduleEndTime"),
    "description": ("description",),
    "next_run_time": ("next_run_time", "nextRunTime"),
    "create_time": ("create_time", "createTime"),
    "updated_time": ("updated_time", "updatedTime"),
    "created_by": ("created_by", "createdBy"),
    "updated_by": ("updated_by", "updatedBy"),
    "start_workflow_request": ("start_workflow_request", "startWorkflowRequest"),
}


def _read(ws: Any, key: str) -> Any:
    """Read a field from either a WorkflowSchedule object (snake_case attrs)
    or a raw camelCase dict — conductor-python returns both shapes depending
    on the endpoint (see ``get_schedule`` vs ``get_all_schedules``)."""
    aliases = _DICT_KEY_MAP.get(key, (key,))
    if isinstance(ws, dict):
        for k in aliases:
            if k in ws:
                return ws[k]
        return None
    for k in aliases:
        if hasattr(ws, k):
            return getattr(ws, k)
    return None


def _from_workflow_schedule(ws: Any, agent_name: Optional[str] = None) -> ScheduleInfo:
    """Convert conductor-python ``WorkflowSchedule`` (or raw dict) -> ``ScheduleInfo``.

    Handles both shapes that conductor-python returns:
    - ``get_all_schedules`` → ``WorkflowSchedule`` objects with snake_case attrs
    - ``get_schedule`` → raw dict with camelCase keys (response_type='object')

    ``agent_name`` is optional; if omitted, it's derived from
    ``startWorkflowRequest.name``.
    """
    swr = _read(ws, "start_workflow_request") or {}
    wire_name = _read(ws, "name") or ""
    swr_name = swr.get("name") if isinstance(swr, dict) else getattr(swr, "name", "")
    swr_input = swr.get("input") if isinstance(swr, dict) else getattr(swr, "input", None)
    agent = agent_name or swr_name or ""

    return ScheduleInfo(
        name=wire_name,
        short_name=_unprefix(agent, wire_name),
        agent=swr_name or "",
        cron=_read(ws, "cron_expression") or "",
        timezone=_read(ws, "zone_id") or "UTC",
        input=dict(swr_input) if swr_input else {},
        paused=bool(_read(ws, "paused")),
        paused_reason=_read(ws, "paused_reason"),
        catchup=bool(_read(ws, "run_catchup_schedule_instances")),
        start_at=_read(ws, "schedule_start_time"),
        end_at=_read(ws, "schedule_end_time"),
        description=_read(ws, "description"),
        next_run=_read(ws, "next_run_time"),
        create_time=_read(ws, "create_time"),
        update_time=_read(ws, "updated_time"),
        created_by=_read(ws, "created_by"),
        updated_by=_read(ws, "updated_by"),
    )


def _check_unique_names(schedules: Iterable[Schedule]) -> None:
    seen: set = set()
    for s in schedules:
        if s.name in seen:
            raise ScheduleNameConflict(
                f"Duplicate schedule name '{s.name}' — names must be unique per agent"
            )
        seen.add(s.name)


def _translate(exc: Exception) -> Exception:
    """Best-effort: map conductor-python HTTP errors to typed schedule errors."""
    status = getattr(exc, "status", None) or getattr(exc, "code", None)
    body = getattr(exc, "body", "") or str(exc)
    if status == 404:
        return ScheduleNotFound(body)
    if status == 400 and "cron" in body.lower():
        return InvalidCronExpression(body)
    return exc


class ScheduleClient:
    """Thin wrapper around Conductor's ``OrkesSchedulerClient``.

    Pause and resume bypass the conductor-python client and issue raw PUT
    requests, because the bundled scheduler API spec is out of date —
    conductor-python sends ``GET /schedules/{name}/pause`` while modern
    Conductor servers (see ``SchedulerResource.java``) expect PUT.
    """

    def __init__(self, scheduler_client: Any, workflow_client: Any) -> None:
        self._sc = scheduler_client
        self._wc = workflow_client

    def _base_url(self) -> str:
        """Resolve the Conductor API base URL from the underlying client config."""
        # OrkesSchedulerClient -> OrkesBaseClient -> api_client.configuration.host
        # host is typically "http://localhost:8089/api"
        cfg = getattr(self._sc, "configuration", None) or getattr(
            getattr(self._sc, "api_client", None), "configuration", None
        )
        if cfg is None:
            raise RuntimeError("Cannot resolve Conductor base URL from scheduler client")
        host = getattr(cfg, "host", None) or getattr(cfg, "base_url", None)
        if not host:
            raise RuntimeError("Conductor configuration has no host/base_url")
        return host.rstrip("/")

    def _http_put(self, path: str, params: Optional[dict] = None) -> None:
        import requests as _req

        url = f"{self._base_url()}{path}"
        r = _req.put(url, params=params or {}, timeout=15)
        if not 200 <= r.status_code < 300:
            exc: Any = RuntimeError(f"PUT {url} -> {r.status_code}: {r.text}")
            exc.status = r.status_code
            exc.body = r.text
            raise _translate(exc)

    # ── individual operations (wire-name keyed) ──────────────────────

    def save(self, schedule: Schedule, agent_name: str) -> None:
        try:
            self._sc.save_schedule(_to_save_request(schedule, agent_name))
        except Exception as exc:  # noqa: BLE001
            raise _translate(exc) from exc

    def get(self, wire_name: str, agent_name: Optional[str] = None) -> ScheduleInfo:
        try:
            ws = self._sc.get_schedule(wire_name)
        except Exception as exc:  # noqa: BLE001
            raise _translate(exc) from exc
        if isinstance(ws, tuple):
            ws = ws[0] if ws else None
        if not ws:
            raise ScheduleNotFound(f"Schedule '{wire_name}' not found")
        # Conductor returns 200 + empty/null body for missing schedules; the
        # client deserializes that to {} or an empty model. Distinguish that
        # from a real schedule by checking for the required ``name`` field.
        if not _read(ws, "name"):
            raise ScheduleNotFound(f"Schedule '{wire_name}' not found")
        return _from_workflow_schedule(ws, agent_name)

    def list_for_agent(self, agent_name: str) -> List[ScheduleInfo]:
        try:
            results = self._sc.get_all_schedules(workflow_name=agent_name) or []
        except Exception as exc:  # noqa: BLE001
            raise _translate(exc) from exc
        return [_from_workflow_schedule(ws, agent_name) for ws in results]

    def pause(self, wire_name: str, reason: Optional[str] = None) -> None:
        # See class docstring: raw PUT bypasses conductor-python's stale GET verb.
        self._http_put(
            f"/scheduler/schedules/{wire_name}/pause",
            params={"reason": reason} if reason else None,
        )

    def resume(self, wire_name: str) -> None:
        self._http_put(f"/scheduler/schedules/{wire_name}/resume")

    def delete(self, wire_name: str) -> None:
        try:
            self._sc.delete_schedule(wire_name)
        except Exception as exc:  # noqa: BLE001
            raise _translate(exc) from exc

    def run_now(self, info: ScheduleInfo) -> str:
        """Fire the agent once with this schedule's stored input. Returns execution id."""
        from conductor.client.http.models.start_workflow_request import StartWorkflowRequest

        req = StartWorkflowRequest(name=info.agent, input=dict(info.input))
        try:
            return self._wc.start_workflow(req)
        except Exception as exc:  # noqa: BLE001
            raise _translate(exc) from exc

    def preview_next(
        self, cron: str, n: int = 5, start_at: Optional[int] = None, end_at: Optional[int] = None
    ) -> List[int]:
        try:
            times = self._sc.get_next_few_schedule_execution_times(
                cron_expression=cron,
                schedule_start_time=start_at,
                schedule_end_time=end_at,
                limit=n,
            )
            return list(times) if times else []
        except Exception as exc:  # noqa: BLE001
            raise _translate(exc) from exc

    # ── declarative reconciliation ──────────────────────────────────

    def reconcile(self, agent_name: str, desired: Optional[List[Schedule]]) -> None:
        """Apply the tri-state semantics from spec §5.1:

        - ``desired is None``: no-op
        - ``desired == []``: delete every schedule whose workflow == agent_name
        - ``desired == [...]``: upsert listed, delete others scoped to this agent
        """
        if desired is None:
            return
        _check_unique_names(desired)
        existing = self.list_for_agent(agent_name)
        existing_wire_by_short = {info.short_name: info.name for info in existing}
        desired_short = {s.name for s in desired}

        for short, wire in existing_wire_by_short.items():
            if short not in desired_short:
                logger.info("Pruning schedule %s for agent %s", wire, agent_name)
                self.delete(wire)

        for s in desired:
            logger.info(
                "Upserting schedule %s for agent %s", _prefix(agent_name, s.name), agent_name
            )
            self.save(s, agent_name)
