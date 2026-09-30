"""Notification management for the Claw TUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from autopilot.config import AutopilotConfig


@dataclass
class Notification:
    """A single notification from an agent execution."""

    agent_name: str
    timestamp: str
    summary: str
    priority: str = "normal"  # "urgent", "normal", "info"
    read: bool = False
    execution_id: str = ""


class NotificationManager:
    """Manages notifications for the TUI.

    Stores notifications in memory and tracks read state.
    Uses the AutopilotConfig's last_seen timestamps for persistent
    unread tracking across sessions.
    """

    def __init__(self, config: Optional[AutopilotConfig] = None) -> None:
        self._config = config or AutopilotConfig()
        self._notifications: list[Notification] = []

    def add(self, notification: Notification) -> None:
        """Add a notification to the list."""
        self._notifications.insert(0, notification)  # newest first

    def get_unread(self) -> list[Notification]:
        """Return all unread notifications, newest first."""
        return [n for n in self._notifications if not n.read]

    def get_all(self, limit: int = 20) -> list[Notification]:
        """Return all notifications, newest first, up to the given limit."""
        return self._notifications[:limit]

    def mark_read(self, agent_name: str) -> None:
        """Mark all notifications for a given agent as read."""
        now = datetime.now(timezone.utc).isoformat()
        for n in self._notifications:
            if n.agent_name == agent_name:
                n.read = True
        self._config.last_seen[agent_name] = now

    def mark_all_read(self) -> None:
        """Mark all notifications as read."""
        now = datetime.now(timezone.utc).isoformat()
        for n in self._notifications:
            n.read = True
            self._config.last_seen[n.agent_name] = now

    def unread_count(self) -> int:
        """Return the number of unread notifications."""
        return sum(1 for n in self._notifications if not n.read)
