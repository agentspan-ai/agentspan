"""StateManager — persists agent_name -> execution state mappings.

State file lives at ``~/.agentspan/autopilot/state.json`` by default.
"""

from __future__ import annotations

import fcntl
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


# Valid status values for an agent.
VALID_STATUSES = frozenset({
    "DRAFT",
    "DEPLOYING",
    "ACTIVE",
    "PAUSED",
    "WAITING",
    "ERROR",
    "ARCHIVED",
})

# Valid trigger types.
VALID_TRIGGER_TYPES = frozenset({
    "cron",
    "daemon",
    "webhook",
})


@dataclass
class AgentState:
    """Runtime state for a single managed agent.

    Attributes:
        name: Agent name (matches the directory under ``agents/``).
        execution_id: Conductor execution ID (empty string if not deployed).
        status: One of DRAFT, DEPLOYING, ACTIVE, PAUSED, WAITING, ERROR, ARCHIVED.
        trigger_type: One of cron, daemon, webhook.
        created_at: ISO-8601 timestamp of when the agent was first created.
        last_deployed: ISO-8601 timestamp of the most recent deployment (empty if never).
    """

    name: str
    execution_id: str
    status: str
    trigger_type: str
    created_at: str
    last_deployed: str = ""

    def __post_init__(self) -> None:
        if self.status not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status {self.status!r}. Must be one of: {sorted(VALID_STATUSES)}"
            )
        if self.trigger_type not in VALID_TRIGGER_TYPES:
            raise ValueError(
                f"Invalid trigger_type {self.trigger_type!r}. "
                f"Must be one of: {sorted(VALID_TRIGGER_TYPES)}"
            )


class StateManager:
    """Manages the mapping of agent names to their runtime state.

    Persists to a JSON file on disk.  All mutations are auto-saved.

    Args:
        state_file: Path to the JSON state file.
    """

    def __init__(self, state_file: Path) -> None:
        self._state_file = state_file
        self._agents: Dict[str, AgentState] = {}
        self.load()

    # -- Public API ------------------------------------------------------------

    def get(self, agent_name: str) -> Optional[AgentState]:
        """Return the state for *agent_name*, or ``None`` if not tracked."""
        return self._agents.get(agent_name)

    def set(self, agent_name: str, state: AgentState) -> None:
        """Store or replace *state* for *agent_name* and persist."""
        if state.name != agent_name:
            raise ValueError(
                f"AgentState.name ({state.name!r}) does not match "
                f"agent_name ({agent_name!r})"
            )
        self._agents[agent_name] = state
        self.save()

    def list_all(self) -> List[AgentState]:
        """Return all tracked agent states, sorted by name."""
        return sorted(self._agents.values(), key=lambda s: s.name)

    def remove(self, agent_name: str) -> None:
        """Remove an agent from tracking.  No-op if not present."""
        if agent_name in self._agents:
            del self._agents[agent_name]
            self.save()

    # -- Persistence -----------------------------------------------------------

    def save(self) -> None:
        """Write current state to disk as JSON (with exclusive file lock)."""
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        data = {name: asdict(state) for name, state in self._agents.items()}
        with open(self._state_file, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            json.dump(data, f, indent=2)
            f.write("\n")
            fcntl.flock(f, fcntl.LOCK_UN)

    def load(self) -> None:
        """Load state from disk (with shared file lock).  If the file does not exist, start empty."""
        if not self._state_file.exists():
            self._agents = {}
            return

        with open(self._state_file, "r") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            raw_text = f.read().strip()
            fcntl.flock(f, fcntl.LOCK_UN)

        if not raw_text:
            self._agents = {}
            return

        raw = json.loads(raw_text)
        self._agents = {}
        for name, fields in raw.items():
            self._agents[name] = AgentState(**fields)
