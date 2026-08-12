"""Tests for the DashboardPoller background polling thread."""

from __future__ import annotations

import threading
import time

import pytest

from autopilot.tui.poller import DashboardPoller


class TestPollerStartStop:
    """Verify the poller starts and stops cleanly."""

    def test_poller_starts_and_stops(self):
        poller = DashboardPoller(interval_seconds=1)
        assert not poller.is_running

        poller.start()
        assert poller.is_running
        # Give the thread a moment to actually start
        time.sleep(0.1)
        assert poller._thread is not None
        assert poller._thread.is_alive()

        poller.stop()
        assert not poller.is_running
        assert poller._thread is None

    def test_start_is_idempotent(self):
        poller = DashboardPoller(interval_seconds=1)
        poller.start()
        thread1 = poller._thread
        poller.start()  # should be a no-op
        thread2 = poller._thread
        assert thread1 is thread2
        poller.stop()

    def test_stop_without_start_is_safe(self):
        poller = DashboardPoller(interval_seconds=1)
        # Should not raise
        poller.stop()
        assert not poller.is_running


class TestPollerCallback:
    """Verify the on_update callback is invoked."""

    def test_poller_calls_on_update(self):
        call_count = [0]
        event = threading.Event()

        def on_update():
            call_count[0] += 1
            event.set()

        poller = DashboardPoller(interval_seconds=1, on_update=on_update)
        poller.start()
        # Wait for at least one callback, with a generous timeout
        event.wait(timeout=5)
        poller.stop()

        assert call_count[0] >= 1, f"Expected at least 1 call, got {call_count[0]}"

    def test_poller_calls_multiple_times(self):
        """Verify the callback fires more than once over multiple intervals."""
        call_count = [0]
        enough_calls = threading.Event()

        def on_update():
            call_count[0] += 1
            if call_count[0] >= 2:
                enough_calls.set()

        # Use a very short interval for testing
        poller = DashboardPoller(interval_seconds=1, on_update=on_update)
        poller.start()
        enough_calls.wait(timeout=10)
        poller.stop()

        assert call_count[0] >= 2, f"Expected at least 2 calls, got {call_count[0]}"

    def test_poller_handles_callback_error(self):
        """Verify the poller does not crash when the callback raises."""
        call_count = [0]
        event = threading.Event()

        def on_update_that_raises():
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("intentional test error")
            # Second call should still happen
            event.set()

        poller = DashboardPoller(interval_seconds=1, on_update=on_update_that_raises)
        poller.start()
        event.wait(timeout=10)
        poller.stop()

        # The poller should have recovered and called again after the error
        assert call_count[0] >= 2, (
            f"Expected at least 2 calls (1 error + 1 success), got {call_count[0]}"
        )

    def test_no_callback_does_not_crash(self):
        """Verify the poller works fine with no on_update callback."""
        poller = DashboardPoller(interval_seconds=1, on_update=None)
        poller.start()
        time.sleep(1.5)
        poller.stop()
        # Should reach here without error


class TestPollerProperties:
    """Verify poller property accessors."""

    def test_interval_property(self):
        poller = DashboardPoller(interval_seconds=42)
        assert poller.interval == 42

    def test_default_interval(self):
        poller = DashboardPoller()
        assert poller.interval == 30

    def test_is_running_reflects_state(self):
        poller = DashboardPoller(interval_seconds=1)
        assert not poller.is_running
        poller.start()
        assert poller.is_running
        poller.stop()
        assert not poller.is_running
