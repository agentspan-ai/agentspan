"""Tests for session management — persistence, CRUD, roundtrip."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from autopilot.tui.sessions import Session, SessionManager


@pytest.fixture
def sessions_file(tmp_path: Path) -> Path:
    """Return a path for a temporary sessions.json file (does not exist yet)."""
    return tmp_path / "sessions.json"


@pytest.fixture
def sm(sessions_file: Path) -> SessionManager:
    """Return a fresh SessionManager backed by a temp file."""
    return SessionManager(sessions_file)


class TestSessionCreate:
    """Creating sessions registers them and sets current."""

    def test_create_sets_current(self, sm: SessionManager) -> None:
        session = sm.create("exec-001")
        assert sm.get_current() == "exec-001"
        assert session.execution_id == "exec-001"
        assert session.status == "RUNNING"

    def test_create_populates_timestamps(self, sm: SessionManager) -> None:
        session = sm.create("exec-002")
        # Timestamps are ISO format strings
        assert "T" in session.created_at
        assert "T" in session.last_active

    def test_create_multiple_sets_latest_as_current(self, sm: SessionManager) -> None:
        sm.create("exec-001")
        sm.create("exec-002")
        assert sm.get_current() == "exec-002"


class TestGetCurrent:
    """get_current returns the active session ID or None."""

    def test_returns_none_when_empty(self, sm: SessionManager) -> None:
        assert sm.get_current() is None

    def test_returns_none_for_empty_string(self, sessions_file: Path) -> None:
        # Write a file with current set to empty string
        sessions_file.parent.mkdir(parents=True, exist_ok=True)
        sessions_file.write_text(json.dumps({"current": "", "sessions": []}))
        sm = SessionManager(sessions_file)
        assert sm.get_current() is None


class TestSetCurrent:
    """set_current updates the current session pointer."""

    def test_set_current(self, sm: SessionManager) -> None:
        sm.create("exec-001")
        sm.create("exec-002")
        sm.set_current("exec-001")
        assert sm.get_current() == "exec-001"


class TestListSessions:
    """list_sessions returns all registered sessions."""

    def test_empty_initially(self, sm: SessionManager) -> None:
        assert sm.list_sessions() == []

    def test_returns_all_created(self, sm: SessionManager) -> None:
        sm.create("exec-001")
        sm.create("exec-002")
        sm.create("exec-003")
        sessions = sm.list_sessions()
        assert len(sessions) == 3
        ids = [s.execution_id for s in sessions]
        assert ids == ["exec-001", "exec-002", "exec-003"]

    def test_returns_session_objects(self, sm: SessionManager) -> None:
        sm.create("exec-001")
        sessions = sm.list_sessions()
        assert isinstance(sessions[0], Session)
        assert sessions[0].status == "RUNNING"


class TestUpdateLastActive:
    """update_last_active touches the timestamp and sets status to RUNNING."""

    def test_updates_timestamp(self, sm: SessionManager) -> None:
        session = sm.create("exec-001")
        original_ts = session.last_active
        # Ensure time passes so timestamp changes
        time.sleep(0.01)
        sm.update_last_active("exec-001")
        updated = sm.list_sessions()[0]
        assert updated.last_active >= original_ts
        assert updated.status == "RUNNING"

    def test_resets_disconnected_to_running(self, sm: SessionManager) -> None:
        sm.create("exec-001")
        sm.mark_disconnected("exec-001")
        assert sm.list_sessions()[0].status == "DISCONNECTED"
        sm.update_last_active("exec-001")
        assert sm.list_sessions()[0].status == "RUNNING"

    def test_noop_for_unknown_id(self, sm: SessionManager) -> None:
        sm.create("exec-001")
        # Should not raise
        sm.update_last_active("nonexistent")
        assert sm.list_sessions()[0].execution_id == "exec-001"


class TestMarkDisconnected:
    """mark_disconnected sets status to DISCONNECTED."""

    def test_marks_disconnected(self, sm: SessionManager) -> None:
        sm.create("exec-001")
        sm.mark_disconnected("exec-001")
        sessions = sm.list_sessions()
        assert sessions[0].status == "DISCONNECTED"

    def test_noop_for_unknown_id(self, sm: SessionManager) -> None:
        sm.create("exec-001")
        sm.mark_disconnected("nonexistent")
        assert sm.list_sessions()[0].status == "RUNNING"


class TestMarkCompleted:
    """mark_completed sets status to COMPLETED."""

    def test_marks_completed(self, sm: SessionManager) -> None:
        sm.create("exec-001")
        sm.mark_completed("exec-001")
        sessions = sm.list_sessions()
        assert sessions[0].status == "COMPLETED"


class TestGetMostRecent:
    """get_most_recent returns the session with the newest last_active."""

    def test_returns_none_when_empty(self, sm: SessionManager) -> None:
        assert sm.get_most_recent() is None

    def test_returns_last_created(self, sm: SessionManager) -> None:
        sm.create("exec-001")
        sm.create("exec-002")
        sm.create("exec-003")
        recent = sm.get_most_recent()
        assert recent is not None
        assert recent.execution_id == "exec-003"

    def test_returns_most_recently_active(self, sm: SessionManager) -> None:
        """get_most_recent should return the session with the latest last_active,
        not just the last appended session."""
        sm.create("exec-001")
        sm.create("exec-002")
        sm.create("exec-003")
        # Touch exec-001 so it becomes the most recently active
        time.sleep(0.01)
        sm.update_last_active("exec-001")
        recent = sm.get_most_recent()
        assert recent is not None
        assert recent.execution_id == "exec-001"


class TestFindById:
    """find_by_id does exact and prefix matching."""

    def test_exact_match(self, sm: SessionManager) -> None:
        sm.create("e6c2d0cf-11af-455b-8443-7e3f5ea193a8")
        found = sm.find_by_id("e6c2d0cf-11af-455b-8443-7e3f5ea193a8")
        assert found is not None
        assert found.execution_id == "e6c2d0cf-11af-455b-8443-7e3f5ea193a8"

    def test_prefix_match(self, sm: SessionManager) -> None:
        sm.create("e6c2d0cf-11af-455b-8443-7e3f5ea193a8")
        found = sm.find_by_id("e6c2d0cf")
        assert found is not None
        assert found.execution_id == "e6c2d0cf-11af-455b-8443-7e3f5ea193a8"

    def test_returns_none_for_no_match(self, sm: SessionManager) -> None:
        sm.create("exec-001")
        assert sm.find_by_id("nonexistent") is None

    def test_ambiguous_prefix_raises(self, sm: SessionManager) -> None:
        """Ambiguous prefix matching raises ValueError."""
        sm.create("e6c2d0cf-aaaa")
        sm.create("e6c2d0cf-bbbb")
        with pytest.raises(ValueError, match="Ambiguous session ID"):
            sm.find_by_id("e6c2d0cf")

    def test_exact_match_wins_over_ambiguous_prefix(self, sm: SessionManager) -> None:
        """An exact match should return immediately, even if other sessions share the prefix."""
        sm.create("e6c2d0cf")
        sm.create("e6c2d0cf-aaaa")
        sm.create("e6c2d0cf-bbbb")
        found = sm.find_by_id("e6c2d0cf")
        assert found is not None
        assert found.execution_id == "e6c2d0cf"


class TestCleanup:
    """cleanup removes oldest COMPLETED sessions beyond the limit."""

    def test_cleanup_removes_oldest_completed(self, sm: SessionManager) -> None:
        for i in range(5):
            sm.create(f"exec-{i:03d}")
            sm.mark_completed(f"exec-{i:03d}")
        sm.cleanup(max_sessions=3)
        sessions = sm.list_sessions()
        completed_ids = [s.execution_id for s in sessions if s.status == "COMPLETED"]
        assert len(completed_ids) == 3
        # Oldest two (exec-000, exec-001) should have been removed
        assert "exec-000" not in completed_ids
        assert "exec-001" not in completed_ids

    def test_cleanup_preserves_active_sessions(self, sm: SessionManager) -> None:
        for i in range(5):
            sm.create(f"exec-{i:03d}")
        # Complete only some
        sm.mark_completed("exec-000")
        sm.mark_completed("exec-001")
        sm.mark_completed("exec-002")
        sm.cleanup(max_sessions=1)
        sessions = sm.list_sessions()
        # 2 active (RUNNING) + 1 completed (most recent) = 3
        assert len(sessions) == 3
        active = [s for s in sessions if s.status == "RUNNING"]
        assert len(active) == 2

    def test_cleanup_noop_under_limit(self, sm: SessionManager) -> None:
        sm.create("exec-001")
        sm.mark_completed("exec-001")
        sm.cleanup(max_sessions=50)
        assert len(sm.list_sessions()) == 1


class TestPersistenceRoundtrip:
    """Data survives being written to disk and loaded by a new SessionManager."""

    def test_roundtrip(self, sessions_file: Path) -> None:
        # Write data with one manager
        sm1 = SessionManager(sessions_file)
        sm1.create("exec-001")
        sm1.create("exec-002")
        sm1.mark_disconnected("exec-001")
        sm1.set_current("exec-002")

        # Load with a fresh manager instance
        sm2 = SessionManager(sessions_file)
        assert sm2.get_current() == "exec-002"
        sessions = sm2.list_sessions()
        assert len(sessions) == 2
        assert sessions[0].execution_id == "exec-001"
        assert sessions[0].status == "DISCONNECTED"
        assert sessions[1].execution_id == "exec-002"
        assert sessions[1].status == "RUNNING"

    def test_file_created_on_first_save(self, sessions_file: Path) -> None:
        assert not sessions_file.exists()
        sm = SessionManager(sessions_file)
        sm.create("exec-001")
        assert sessions_file.exists()
        data = json.loads(sessions_file.read_text())
        assert data["current"] == "exec-001"
        assert len(data["sessions"]) == 1

    def test_handles_corrupted_file(self, sessions_file: Path) -> None:
        sessions_file.parent.mkdir(parents=True, exist_ok=True)
        sessions_file.write_text("not valid json {{{")
        sm = SessionManager(sessions_file)
        # Should not raise, should have empty state
        assert sm.get_current() is None
        assert sm.list_sessions() == []
        # And should be able to create new sessions
        sm.create("exec-001")
        assert sm.get_current() == "exec-001"

    def test_handles_missing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "nonexistent" / "sessions.json"
        sm = SessionManager(path)
        assert sm.get_current() is None
        # Creating should create the parent dirs
        sm.create("exec-001")
        assert path.exists()


class TestCommandParsing:
    """Verify the new session commands are parsed correctly."""

    def test_sessions_command(self) -> None:
        from autopilot.tui.commands import parse_command

        result = parse_command("/sessions")
        assert result.action == "list_sessions"

    def test_new_command(self) -> None:
        from autopilot.tui.commands import parse_command

        result = parse_command("/new")
        assert result.action == "new_session"

    def test_switch_command(self) -> None:
        from autopilot.tui.commands import parse_command

        result = parse_command("/switch e6c2d0cf-11af")
        assert result.action == "switch_session"
        assert result.message == "e6c2d0cf-11af"

    def test_switch_missing_id(self) -> None:
        from autopilot.tui.commands import parse_command

        result = parse_command("/switch ")
        assert result.output is not None
        assert "Usage" in result.output

    def test_help_includes_session_commands(self) -> None:
        from autopilot.tui.commands import HELP_TEXT

        assert "/sessions" in HELP_TEXT
        assert "/switch" in HELP_TEXT
        assert "/new" in HELP_TEXT
