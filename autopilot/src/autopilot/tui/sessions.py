"""Session management — persistent session tracking in ~/.agentspan/autopilot/sessions.json."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class Session:
    """A single orchestrator session backed by one workflow execution."""

    execution_id: str
    created_at: str
    last_active: str
    status: str = "RUNNING"  # RUNNING, DISCONNECTED, COMPLETED


class SessionManager:
    """Manages session persistence in a JSON file.

    Default path: ``~/.agentspan/autopilot/sessions.json``
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._data: dict = {"current": "", "sessions": []}
        self._load()

    # -- internal ---------------------------------------------------------------

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text())
            except (json.JSONDecodeError, OSError):
                self._data = {"current": "", "sessions": []}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2))

    # -- public API -------------------------------------------------------------

    def create(self, execution_id: str) -> Session:
        """Register a new session and set it as current."""
        now = datetime.now(timezone.utc).isoformat()
        session = Session(execution_id=execution_id, created_at=now, last_active=now)
        self._data["sessions"].append(asdict(session))
        self._data["current"] = execution_id
        self._save()
        return session

    def get_current(self) -> Optional[str]:
        """Return the current session's execution ID, or None."""
        return self._data.get("current") or None

    def set_current(self, execution_id: str) -> None:
        """Set the current session."""
        self._data["current"] = execution_id
        self._save()

    def update_last_active(self, execution_id: str) -> None:
        """Touch the last_active timestamp and set status to RUNNING."""
        for s in self._data["sessions"]:
            if s["execution_id"] == execution_id:
                s["last_active"] = datetime.now(timezone.utc).isoformat()
                s["status"] = "RUNNING"
                break
        self._save()

    def mark_disconnected(self, execution_id: str) -> None:
        """Mark a session as DISCONNECTED (user exited without stopping)."""
        for s in self._data["sessions"]:
            if s["execution_id"] == execution_id:
                s["status"] = "DISCONNECTED"
                break
        self._save()

    def mark_completed(self, execution_id: str) -> None:
        """Mark a session as COMPLETED."""
        for s in self._data["sessions"]:
            if s["execution_id"] == execution_id:
                s["status"] = "COMPLETED"
                break
        self._save()

    def list_sessions(self) -> list[Session]:
        """Return all sessions."""
        return [Session(**s) for s in self._data.get("sessions", [])]

    def get_most_recent(self) -> Optional[Session]:
        """Return the most recently created session, or None."""
        sessions = self._data.get("sessions", [])
        if not sessions:
            return None
        return Session(**sessions[-1])

    def find_by_id(self, execution_id: str) -> Optional[Session]:
        """Find a session by execution ID (full or prefix match)."""
        for s in self._data.get("sessions", []):
            if s["execution_id"] == execution_id:
                return Session(**s)
        # Try prefix match
        for s in self._data.get("sessions", []):
            if s["execution_id"].startswith(execution_id):
                return Session(**s)
        return None
