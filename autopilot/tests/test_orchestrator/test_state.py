"""Tests for StateManager — all use real files via tmp_path, no mocks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from autopilot.orchestrator.state import AgentState, StateManager, VALID_STATUSES


# ---------------------------------------------------------------------------
# AgentState dataclass
# ---------------------------------------------------------------------------

class TestAgentState:
    def test_valid_creation(self):
        state = AgentState(
            name="test_agent",
            execution_id="exec-123",
            status="ACTIVE",
            trigger_type="daemon",
            created_at="2026-04-12T00:00:00Z",
        )
        assert state.name == "test_agent"
        assert state.execution_id == "exec-123"
        assert state.status == "ACTIVE"
        assert state.trigger_type == "daemon"
        assert state.last_deployed == ""

    def test_with_last_deployed(self):
        state = AgentState(
            name="test",
            execution_id="e1",
            status="ACTIVE",
            trigger_type="cron",
            created_at="2026-04-12T00:00:00Z",
            last_deployed="2026-04-12T01:00:00Z",
        )
        assert state.last_deployed == "2026-04-12T01:00:00Z"

    def test_invalid_status_raises(self):
        with pytest.raises(ValueError, match="Invalid status"):
            AgentState(
                name="bad",
                execution_id="",
                status="RUNNING",  # not a valid status
                trigger_type="daemon",
                created_at="2026-01-01",
            )

    def test_invalid_trigger_type_raises(self):
        with pytest.raises(ValueError, match="Invalid trigger_type"):
            AgentState(
                name="bad",
                execution_id="",
                status="DRAFT",
                trigger_type="event",  # not a valid trigger type
                created_at="2026-01-01",
            )

    def test_all_valid_statuses_accepted(self):
        for status in VALID_STATUSES:
            state = AgentState(
                name="s",
                execution_id="",
                status=status,
                trigger_type="daemon",
                created_at="t",
            )
            assert state.status == status


# ---------------------------------------------------------------------------
# StateManager — basic operations
# ---------------------------------------------------------------------------

class TestStateManagerBasic:
    def test_empty_state_file(self, tmp_path: Path):
        sm = StateManager(tmp_path / "state.json")
        assert sm.list_all() == []

    def test_get_nonexistent_returns_none(self, tmp_path: Path):
        sm = StateManager(tmp_path / "state.json")
        assert sm.get("no_such_agent") is None

    def test_set_and_get(self, tmp_path: Path):
        sm = StateManager(tmp_path / "state.json")
        state = AgentState(
            name="my_agent",
            execution_id="exec-abc",
            status="ACTIVE",
            trigger_type="cron",
            created_at="2026-04-12T00:00:00Z",
        )
        sm.set("my_agent", state)
        retrieved = sm.get("my_agent")

        assert retrieved is not None
        assert retrieved.name == "my_agent"
        assert retrieved.execution_id == "exec-abc"
        assert retrieved.status == "ACTIVE"

    def test_set_name_mismatch_raises(self, tmp_path: Path):
        sm = StateManager(tmp_path / "state.json")
        state = AgentState(
            name="agent_a",
            execution_id="",
            status="DRAFT",
            trigger_type="daemon",
            created_at="t",
        )
        with pytest.raises(ValueError, match="does not match"):
            sm.set("agent_b", state)

    def test_list_all_sorted(self, tmp_path: Path):
        sm = StateManager(tmp_path / "state.json")
        for name in ["charlie", "alpha", "bravo"]:
            sm.set(name, AgentState(
                name=name,
                execution_id="",
                status="DRAFT",
                trigger_type="daemon",
                created_at="t",
            ))

        names = [s.name for s in sm.list_all()]
        assert names == ["alpha", "bravo", "charlie"]

    def test_remove(self, tmp_path: Path):
        sm = StateManager(tmp_path / "state.json")
        sm.set("to_remove", AgentState(
            name="to_remove",
            execution_id="",
            status="DRAFT",
            trigger_type="daemon",
            created_at="t",
        ))
        assert sm.get("to_remove") is not None
        sm.remove("to_remove")
        assert sm.get("to_remove") is None

    def test_remove_nonexistent_is_noop(self, tmp_path: Path):
        sm = StateManager(tmp_path / "state.json")
        sm.remove("ghost")  # should not raise


# ---------------------------------------------------------------------------
# StateManager — persistence
# ---------------------------------------------------------------------------

class TestStateManagerPersistence:
    def test_save_creates_file(self, tmp_path: Path):
        state_file = tmp_path / "state.json"
        sm = StateManager(state_file)
        sm.set("persisted", AgentState(
            name="persisted",
            execution_id="e-99",
            status="ACTIVE",
            trigger_type="cron",
            created_at="2026-04-12T00:00:00Z",
            last_deployed="2026-04-12T01:00:00Z",
        ))
        assert state_file.exists()

        raw = json.loads(state_file.read_text())
        assert "persisted" in raw
        assert raw["persisted"]["execution_id"] == "e-99"

    def test_load_from_existing_file(self, tmp_path: Path):
        state_file = tmp_path / "state.json"
        # Write directly to file
        data = {
            "loaded_agent": {
                "name": "loaded_agent",
                "execution_id": "e-loaded",
                "status": "PAUSED",
                "trigger_type": "webhook",
                "created_at": "2026-01-01",
                "last_deployed": "2026-02-01",
            }
        }
        state_file.write_text(json.dumps(data))

        sm = StateManager(state_file)
        state = sm.get("loaded_agent")

        assert state is not None
        assert state.execution_id == "e-loaded"
        assert state.status == "PAUSED"
        assert state.trigger_type == "webhook"

    def test_roundtrip(self, tmp_path: Path):
        state_file = tmp_path / "state.json"

        sm1 = StateManager(state_file)
        sm1.set("roundtrip", AgentState(
            name="roundtrip",
            execution_id="e-rt",
            status="WAITING",
            trigger_type="daemon",
            created_at="2026-04-12T00:00:00Z",
        ))

        # New manager reads the same file
        sm2 = StateManager(state_file)
        state = sm2.get("roundtrip")

        assert state is not None
        assert state.execution_id == "e-rt"
        assert state.status == "WAITING"

    def test_set_overwrites_existing(self, tmp_path: Path):
        sm = StateManager(tmp_path / "state.json")

        sm.set("overwrite", AgentState(
            name="overwrite",
            execution_id="old-id",
            status="DRAFT",
            trigger_type="daemon",
            created_at="t",
        ))

        sm.set("overwrite", AgentState(
            name="overwrite",
            execution_id="new-id",
            status="ACTIVE",
            trigger_type="daemon",
            created_at="t",
            last_deployed="t2",
        ))

        state = sm.get("overwrite")
        assert state is not None
        assert state.execution_id == "new-id"
        assert state.status == "ACTIVE"

    def test_empty_file_handled(self, tmp_path: Path):
        state_file = tmp_path / "state.json"
        state_file.write_text("")
        sm = StateManager(state_file)
        assert sm.list_all() == []

    def test_creates_parent_dirs(self, tmp_path: Path):
        state_file = tmp_path / "deep" / "nested" / "state.json"
        sm = StateManager(state_file)
        sm.set("deep", AgentState(
            name="deep",
            execution_id="",
            status="DRAFT",
            trigger_type="daemon",
            created_at="t",
        ))
        assert state_file.exists()
