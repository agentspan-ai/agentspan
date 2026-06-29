# Copyright (c) 2026 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Cron-based scheduling for deployed agents.

A :class:`Schedule` attaches a cron trigger to an agent at deploy time.
One agent can carry multiple schedules; each is identified by a short
name unique within that agent. The SDK auto-prefixes the wire name as
``{agent.name}-{name}`` to satisfy Conductor's org-wide uniqueness.

See ``docs/design/scheduling.md`` for the full design.
"""

from __future__ import annotations

from conductor.ai.agents.schedule import api as schedules
from conductor.ai.agents.schedule.errors import (
    InvalidCronExpression,
    ScheduleError,
    ScheduleNameConflict,
    ScheduleNotFound,
)
from conductor.ai.agents.schedule.schedule import Schedule, ScheduleInfo

__all__ = [
    "Schedule",
    "ScheduleInfo",
    "ScheduleError",
    "ScheduleNameConflict",
    "ScheduleNotFound",
    "InvalidCronExpression",
    "schedules",
]
