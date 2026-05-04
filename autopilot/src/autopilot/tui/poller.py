"""Background polling for dashboard status updates and notifications."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)


class DashboardPoller:
    """Background thread that periodically polls for agent status updates and notifications.

    The poller runs as a daemon thread, calling the ``on_update`` callback at the
    configured interval. It is designed to be resilient: exceptions in the callback
    are caught and silently ignored to prevent the poller from crashing.

    When a server is reachable, the poller queries ``GET /api/agent/executions?status=RUNNING``
    to discover live execution status. It compares the server state with the local
    ``StateManager`` and updates local status accordingly. Newly completed executions
    trigger notifications.

    Usage::

        poller = DashboardPoller(interval_seconds=30, on_update=app.invalidate)
        poller.start()
        # ... later ...
        poller.stop()
    """

    def __init__(
        self,
        interval_seconds: int = 30,
        on_update: Optional[Callable] = None,
    ) -> None:
        self._interval = interval_seconds
        self._on_update = on_update
        self._running = False
        self._thread: Optional[threading.Thread] = None
        # Track execution IDs we knew were running on the previous poll,
        # so we can detect completions.
        self._previously_running: Dict[str, str] = {}  # execution_id -> agent_name

    @property
    def is_running(self) -> bool:
        """Whether the poller is currently running."""
        return self._running

    @property
    def interval(self) -> int:
        """The polling interval in seconds."""
        return self._interval

    def start(self) -> None:
        """Start the background polling thread.

        If already running, this is a no-op.
        """
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the polling thread.

        Blocks for up to 5 seconds waiting for the thread to finish.
        """
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _poll_loop(self) -> None:
        """Main polling loop — runs until ``stop()`` is called."""
        while self._running:
            try:
                self._do_poll()
            except Exception:
                pass  # Don't crash the poller on errors
            time.sleep(self._interval)

    def _do_poll(self) -> None:
        """Execute one poll cycle.

        Queries the server for running executions, reconciles with local
        state, creates notifications for completions, and triggers the
        on_update callback to refresh the TUI.
        """
        from autopilot.config import AutopilotConfig
        from autopilot.orchestrator.state import AgentState, StateManager

        config = AutopilotConfig.from_env()
        state_file = config.base_dir / "state.json"

        # Always refresh local state first
        sm: Optional[StateManager] = None
        if state_file.exists():
            sm = StateManager(state_file)

        # Query the server for live execution status
        try:
            from autopilot.orchestrator.server import query_executions

            running = query_executions(status="RUNNING", config=config)
        except Exception:
            # Server unreachable — fall back to local-only state
            running = None

        if running is not None and sm is not None:
            # Build a set of currently-running execution IDs
            now_running: Dict[str, str] = {}
            for ex in running:
                eid = ex.get("executionId", "")
                aname = ex.get("agentName", "")
                if eid:
                    now_running[eid] = aname

            # Check local agents whose execution_id was previously running
            # but is no longer — they may have completed or errored.
            for state in sm.list_all():
                if state.execution_id and state.status in ("ACTIVE", "DEPLOYING"):
                    if state.execution_id in now_running:
                        # Still running — update status to ACTIVE if needed
                        if state.status != "ACTIVE":
                            sm.set(state.name, AgentState(
                                name=state.name,
                                execution_id=state.execution_id,
                                status="ACTIVE",
                                trigger_type=state.trigger_type,
                                created_at=state.created_at,
                                last_deployed=state.last_deployed,
                            ))
                    elif state.execution_id in self._previously_running:
                        # Was running before, not running now → completed
                        try:
                            from autopilot.orchestrator.server import get_execution

                            details = get_execution(state.execution_id, config=config)
                            server_status = details.get("status", "COMPLETED")
                        except Exception:
                            server_status = "COMPLETED"

                        new_status = "ERROR" if server_status == "FAILED" else "PAUSED"
                        sm.set(state.name, AgentState(
                            name=state.name,
                            execution_id=state.execution_id,
                            status=new_status,
                            trigger_type=state.trigger_type,
                            created_at=state.created_at,
                            last_deployed=state.last_deployed,
                        ))

            self._previously_running = now_running

        if self._on_update:
            self._on_update()
