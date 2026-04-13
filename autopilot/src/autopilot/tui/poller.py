"""Background polling for dashboard status updates and notifications."""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional


class DashboardPoller:
    """Background thread that periodically polls for agent status updates and notifications.

    The poller runs as a daemon thread, calling the ``on_update`` callback at the
    configured interval. It is designed to be resilient: exceptions in the callback
    are caught and silently ignored to prevent the poller from crashing.

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

        Refreshes local agent state and triggers the on_update callback.
        When the server-side execution query API is available, this will also call:
            GET /api/agent/executions?status=RUNNING,PAUSED,COMPLETED&since={last_poll}
        """
        # Refresh local state (agent directories + state.json)
        try:
            from autopilot.config import AutopilotConfig
            from autopilot.orchestrator.state import StateManager

            config = AutopilotConfig.from_env()
            state_file = config.autopilot_dir / "state.json"
            if state_file.exists():
                sm = StateManager(state_file)
                # Touch the state to keep it loaded — actual status checks
                # happen via the orchestrator tools when the user asks
                _ = sm.list_all()
        except Exception:
            pass

        if self._on_update:
            self._on_update()
