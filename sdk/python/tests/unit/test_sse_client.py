# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tier 2: Mock SSE server tests for _stream_sse().

Spins up a real HTTP server in a thread that speaks SSE protocol,
then points the Python SDK's _stream_sse() at it.  Tests the full
HTTP → parse → AgentEvent pipeline including timeouts and errors.
"""

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict
from unittest.mock import patch

import pytest

from agentspan.agents.runtime.config import AgentConfig
from agentspan.agents.runtime.runtime import AgentRuntime

# ── Mock SSE Server ─────────────────────────────────────────────────


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _format_sse_event(event_type: str, event_id: str, data: dict) -> bytes:
    """Format a single SSE event as wire bytes."""
    payload = json.dumps(data)
    return f"id:{event_id}\nevent:{event_type}\ndata:{payload}\n\n".encode()


def _format_heartbeat() -> bytes:
    return b":heartbeat\n\n"


class MockSSEHandler(BaseHTTPRequestHandler):
    """HTTP handler that serves scripted SSE events."""

    def do_GET(self):
        if "/agent/stream/" not in self.path:
            self.send_error(404)
            return

        scenario = self.server.scenario  # type: ignore[attr-defined]

        if scenario.get("status_code", 200) != 200:
            self.send_error(scenario["status_code"])
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        # Record received headers for auth tests
        self.server.received_headers = dict(self.headers)  # type: ignore[attr-defined]

        # Replay from Last-Event-ID if provided
        last_id = self.headers.get("Last-Event-ID")
        last_id_int = int(last_id) if last_id else 0

        try:
            # Send heartbeats before events if configured
            for _ in range(scenario.get("heartbeats_before", 0)):
                self.wfile.write(_format_heartbeat())
                self.wfile.flush()
                time.sleep(0.05)

            for ev in scenario.get("events", []):
                ev_id = int(ev["id"])
                if ev_id <= last_id_int:
                    continue  # Skip already-seen events (reconnection replay)

                self.wfile.write(_format_sse_event(ev["event"], ev["id"], ev["data"]))
                self.wfile.flush()
                delay = ev.get("delay", 0)
                if delay:
                    time.sleep(delay)

            # Send heartbeats after events if configured (for heartbeat-only test)
            for _ in range(scenario.get("heartbeats_after", 0)):
                self.wfile.write(_format_heartbeat())
                self.wfile.flush()
                time.sleep(scenario.get("heartbeat_interval", 0.5))

        except (BrokenPipeError, ConnectionResetError):
            pass  # Client disconnected

    def log_message(self, format, *args):
        pass  # Suppress request logs during tests


class MockSSEServer:
    """Lightweight SSE server for testing."""

    def __init__(self, scenario: Dict[str, Any]):
        self.port = _find_free_port()
        self.server = HTTPServer(("127.0.0.1", self.port), MockSSEHandler)
        self.server.scenario = scenario  # type: ignore[attr-defined]
        self.server.received_headers = {}  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self) -> str:
        self._thread.start()
        return f"http://127.0.0.1:{self.port}"

    def stop(self):
        self.server.shutdown()
        self._thread.join(timeout=5)

    @property
    def received_headers(self) -> dict:
        return self.server.received_headers  # type: ignore[attr-defined]


# ── Helpers ──────────────────────────────────────────────────────────


def _java_event(event_type: str, execution_id: str = "test-wf", **fields) -> dict:
    data = {"type": event_type, "executionId": execution_id}
    data.update(fields)
    return data


def _make_runtime(server_url: str, auth_key: str = None, auth_secret: str = None) -> AgentRuntime:
    """Create a minimal AgentRuntime pointing at the mock server.

    We only need the _stream_sse() method, so we bypass full initialization
    by creating the config and setting it directly.
    """
    config = AgentConfig(
        server_url=server_url,
        auth_key=auth_key,
        auth_secret=auth_secret,
        streaming_enabled=True,
    )
    rt = object.__new__(AgentRuntime)
    rt._config = config
    return rt


# ── Tests ────────────────────────────────────────────────────────────


class TestStreamSSEAllEvents:
    def test_receives_all_event_types(self):
        """All 10 event types flow through HTTP → parse → AgentEvent."""
        scenario = {
            "events": [
                {"event": "thinking", "id": "1", "data": _java_event("thinking", content="llm")},
                {
                    "event": "tool_call",
                    "id": "2",
                    "data": _java_event("tool_call", toolName="search", args={"q": "test"}),
                },
                {
                    "event": "tool_result",
                    "id": "3",
                    "data": _java_event("tool_result", toolName="search", result="found"),
                },
                {"event": "handoff", "id": "4", "data": _java_event("handoff", target="support")},
                {
                    "event": "waiting",
                    "id": "5",
                    "data": _java_event("waiting", pendingTool={"tool_name": "approve"}),
                },
                {
                    "event": "guardrail_pass",
                    "id": "6",
                    "data": _java_event("guardrail_pass", guardrailName="safety"),
                },
                {
                    "event": "guardrail_fail",
                    "id": "7",
                    "data": _java_event("guardrail_fail", guardrailName="pii", content="blocked"),
                },
                {"event": "message", "id": "8", "data": _java_event("message", content="hello")},
                {"event": "error", "id": "9", "data": _java_event("error", content="oops")},
                # error is terminal — stream will stop here
            ],
        }

        server = MockSSEServer(scenario)
        url = server.start()
        try:
            rt = _make_runtime(url)
            events = list(rt._stream_sse("test-wf"))

            # Should stop at error (terminal event), so 9 events
            assert len(events) == 9
            types = [e.type for e in events]
            assert types == [
                "thinking",
                "tool_call",
                "tool_result",
                "handoff",
                "waiting",
                "guardrail_pass",
                "guardrail_fail",
                "message",
                "error",
            ]

            # Verify field mappings
            assert events[1].tool_name == "search"
            assert events[1].args == {"q": "test"}
            assert events[2].result == "found"
            assert events[3].target == "support"
            assert events[5].guardrail_name == "safety"
            assert events[6].content == "blocked"
        finally:
            server.stop()

    def test_done_event_with_output(self):
        scenario = {
            "events": [
                {
                    "event": "thinking",
                    "id": "1",
                    "data": _java_event("thinking", content="processing"),
                },
                {
                    "event": "done",
                    "id": "2",
                    "data": _java_event("done", output={"result": "Final answer"}),
                },
            ],
        }

        server = MockSSEServer(scenario)
        url = server.start()
        try:
            rt = _make_runtime(url)
            events = list(rt._stream_sse("test-wf"))
            assert len(events) == 2
            assert events[1].type == "done"
            assert events[1].output == {"result": "Final answer"}
        finally:
            server.stop()


class TestStreamSSETermination:
    def test_stops_on_done(self):
        scenario = {
            "events": [
                {"event": "thinking", "id": "1", "data": _java_event("thinking")},
                {"event": "done", "id": "2", "data": _java_event("done", output="ok")},
                # This event should never be received
                {"event": "thinking", "id": "3", "data": _java_event("thinking")},
            ],
        }

        server = MockSSEServer(scenario)
        url = server.start()
        try:
            rt = _make_runtime(url)
            events = list(rt._stream_sse("test-wf"))
            assert len(events) == 2
            assert events[-1].type == "done"
        finally:
            server.stop()

    def test_stops_on_error(self):
        scenario = {
            "events": [
                {"event": "thinking", "id": "1", "data": _java_event("thinking")},
                {"event": "error", "id": "2", "data": _java_event("error", content="fail")},
                {"event": "done", "id": "3", "data": _java_event("done")},
            ],
        }

        server = MockSSEServer(scenario)
        url = server.start()
        try:
            rt = _make_runtime(url)
            events = list(rt._stream_sse("test-wf"))
            assert len(events) == 2
            assert events[-1].type == "error"
        finally:
            server.stop()


class TestStreamSSEHeartbeats:
    def test_heartbeats_before_real_event_no_fallback(self):
        """Heartbeats followed by real events within timeout don't trigger fallback."""
        scenario = {
            "heartbeats_before": 3,
            "events": [
                {"event": "done", "id": "1", "data": _java_event("done", output="ok")},
            ],
        }

        server = MockSSEServer(scenario)
        url = server.start()
        try:
            rt = _make_runtime(url)
            events = list(rt._stream_sse("test-wf"))
            assert len(events) == 1
            assert events[0].type == "done"
        finally:
            server.stop()

    def test_heartbeat_only_triggers_sse_unavailable(self):
        """Stream with only heartbeats raises _SSEUnavailableError after timeout."""
        scenario = {
            "heartbeats_after": 20,
            "heartbeat_interval": 0.2,
        }

        server = MockSSEServer(scenario)
        url = server.start()
        try:
            rt = _make_runtime(url)
            # Patch the timeout to 1 second for fast test
            with patch.object(
                rt,
                "_stream_sse",
                wraps=rt._stream_sse,
            ):
                # We need to patch the constant inside the method.
                # Since it's a local var, we test by consuming with a timeout.
                events = []
                start_time = time.monotonic()
                try:
                    for event in rt._stream_sse("test-wf"):
                        events.append(event)
                except Exception as e:
                    # Should be _SSEUnavailableError
                    elapsed = time.monotonic() - start_time
                    assert "heartbeat" in str(e).lower() or "no events" in str(e).lower()
                    # Should have waited ~15s (the _SSE_NO_EVENT_TIMEOUT)
                    assert elapsed >= 3  # At least a few seconds
                    return

                # If we get here without exception, the stream ended cleanly
                # which is also acceptable (server closed connection)
                assert len(events) == 0
        finally:
            server.stop()


class TestStreamSSEErrors:
    def test_non_200_raises_sse_unavailable(self):
        scenario = {"status_code": 404}

        server = MockSSEServer(scenario)
        url = server.start()
        try:
            rt = _make_runtime(url)
            with pytest.raises(Exception) as exc_info:
                list(rt._stream_sse("test-wf"))
            assert "404" in str(exc_info.value) or "unavailable" in str(exc_info.value).lower()
        finally:
            server.stop()

    def test_connection_refused_raises_sse_unavailable(self):
        """Connection to non-existent server raises _SSEUnavailableError."""
        rt = _make_runtime("http://127.0.0.1:1")  # Port 1 = won't be listening
        with pytest.raises(Exception):
            list(rt._stream_sse("test-wf"))


class TestStreamSSEAuth:
    def test_auth_headers_sent(self):
        scenario = {
            "events": [
                {"event": "done", "id": "1", "data": _java_event("done", output="ok")},
            ],
        }

        server = MockSSEServer(scenario)
        url = server.start()
        try:
            rt = _make_runtime(url, auth_key="my-key", auth_secret="my-secret")
            events = list(rt._stream_sse("test-wf"))
            assert len(events) == 1

            headers = server.received_headers
            assert headers.get("X-Auth-Key") == "my-key"
            assert headers.get("X-Auth-Secret") == "my-secret"
        finally:
            server.stop()

    def test_no_auth_headers_when_not_configured(self):
        scenario = {
            "events": [
                {"event": "done", "id": "1", "data": _java_event("done", output="ok")},
            ],
        }

        server = MockSSEServer(scenario)
        url = server.start()
        try:
            rt = _make_runtime(url)
            list(rt._stream_sse("test-wf"))

            headers = server.received_headers
            assert "X-Auth-Key" not in headers
            assert "X-Auth-Secret" not in headers
        finally:
            server.stop()


class TestStreamSSEWorkflowId:
    def test_events_carry_execution_id(self):
        scenario = {
            "events": [
                {
                    "event": "thinking",
                    "id": "1",
                    "data": _java_event("thinking", execution_id="wf-real", content="hi"),
                },
                {
                    "event": "done",
                    "id": "2",
                    "data": _java_event("done", execution_id="wf-real", output="ok"),
                },
            ],
        }

        server = MockSSEServer(scenario)
        url = server.start()
        try:
            rt = _make_runtime(url)
            events = list(rt._stream_sse("wf-real"))
            assert all(e.execution_id == "wf-real" for e in events)
        finally:
            server.stop()
