# Copyright (c) 2026 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Schedule-specific exceptions."""

from __future__ import annotations

from conductor.ai.agents.exceptions import AgentspanError


class ScheduleError(AgentspanError):
    """Base class for schedule errors."""


class ScheduleNameConflict(ScheduleError):
    """Two schedules in the same agent share a name."""


class ScheduleNotFound(ScheduleError):
    """No schedule matches the given name."""


class InvalidCronExpression(ScheduleError):
    """Server rejected the cron expression as malformed."""
