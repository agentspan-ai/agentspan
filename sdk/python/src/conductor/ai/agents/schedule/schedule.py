# Copyright (c) 2026 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""User-facing dataclasses: ``Schedule`` (input) and ``ScheduleInfo`` (output).

``Schedule`` is what users construct and pass to ``deploy(..., schedules=[...])``.
``ScheduleInfo`` is what ``schedules.list/get`` returns — it carries the
prefixed wire name plus server-computed fields like ``next_run``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


def _prefix(agent_name: str, short_name: str) -> str:
    return f"{agent_name}-{short_name}"


def _unprefix(agent_name: str, wire_name: str) -> str:
    prefix = f"{agent_name}-"
    return wire_name[len(prefix) :] if wire_name.startswith(prefix) else wire_name


@dataclass(frozen=True)
class Schedule:
    """One cron trigger for an agent.

    Attributes:
        name: Short identifier, unique per agent. Required.
        cron: Cron expression (5- or 6-field; server validates).
        timezone: IANA timezone id; maps to Conductor ``zoneId``.
        input: Workflow input passed when the cron fires.
        catchup: Replay missed fires on resume.
        paused: Start in paused state.
        start_at: Window start (epoch ms or ISO 8601 string).
        end_at: Window end.
        description: Human-readable note.
    """

    name: str
    cron: str
    timezone: str = "UTC"
    input: Dict[str, Any] = field(default_factory=dict)
    catchup: bool = False
    paused: bool = False
    start_at: Optional[int] = None
    end_at: Optional[int] = None
    description: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("Schedule.name is required and must be non-empty")
        if not self.cron or not self.cron.strip():
            raise ValueError("Schedule.cron is required and must be non-empty")
        if self.start_at is not None and self.end_at is not None:
            if self.start_at >= self.end_at:
                raise ValueError("Schedule.start_at must be < end_at")


@dataclass(frozen=True)
class ScheduleInfo:
    """Server view of a schedule, as returned by ``schedules.list/get``."""

    name: str
    """Wire name (prefixed with ``{agent}-``)."""

    short_name: str
    """User-supplied name (the part after the ``{agent}-`` prefix)."""

    agent: str
    """Agent / workflow name this schedule fires."""

    cron: str
    timezone: str
    input: Dict[str, Any]
    paused: bool
    paused_reason: Optional[str]
    catchup: bool
    start_at: Optional[int]
    end_at: Optional[int]
    description: Optional[str]
    next_run: Optional[int]
    create_time: Optional[int]
    update_time: Optional[int]
    created_by: Optional[str]
    updated_by: Optional[str]
