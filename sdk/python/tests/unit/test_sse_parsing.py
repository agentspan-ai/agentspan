# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tier 1: Unit tests for SSE parsing — _parse_sse() and _sse_to_agent_event().

Tests the static methods on AgentRuntime that parse SSE wire format
into AgentEvent objects.  Zero external dependencies.
"""

import json

from agentspan.agents.runtime.runtime import AgentRuntime

# ── Helpers ──────────────────────────────────────────────────────────


def _make_sse_lines(*events):
    """Build a list of SSE wire-format lines from event dicts.

    Each event dict has: event, id (optional), data (dict).
    Returns a flat list of strings as _parse_sse expects.
    """
    lines = []
    for ev in events:
        if ev.get("_comment"):
            lines.append(ev["_comment"])
            lines.append("")
            continue
        if "id" in ev:
            lines.append(f"id:{ev['id']}")
        if "event" in ev:
            lines.append(f"event:{ev['event']}")
        if "data" in ev:
            data = ev["data"] if isinstance(ev["data"], str) else json.dumps(ev["data"])
            lines.append(f"data:{data}")
        lines.append("")  # blank line = event boundary
    return lines


def _java_event(event_type, execution_id="wf-1", **fields):
    """Construct a dict matching the Java AgentSSEEvent JSON shape."""
    data = {"type": event_type, "executionId": execution_id}
    data.update(fields)
    return data


# ── _parse_sse() tests ───────────────────────────────────────────────


class TestParseSSE:
    def test_parse_single_event(self):
        lines = _make_sse_lines(
            {
                "event": "thinking",
                "id": "1",
                "data": {"type": "thinking", "executionId": "wf-1", "content": "llm"},
            }
        )
        events = list(AgentRuntime._parse_sse(iter(lines)))
        assert len(events) == 1
        assert events[0]["event"] == "thinking"
        assert events[0]["id"] == "1"
        assert events[0]["data"]["content"] == "llm"

    def test_parse_multiple_events(self):
        lines = _make_sse_lines(
            {"event": "thinking", "id": "1", "data": {"type": "thinking"}},
            {"event": "tool_call", "id": "2", "data": {"type": "tool_call", "toolName": "search"}},
            {"event": "done", "id": "3", "data": {"type": "done", "output": "answer"}},
        )
        events = list(AgentRuntime._parse_sse(iter(lines)))
        assert len(events) == 3
        assert events[0]["event"] == "thinking"
        assert events[1]["event"] == "tool_call"
        assert events[2]["event"] == "done"

    def test_parse_heartbeat_comment(self):
        lines = [":heartbeat", ""]
        events = list(AgentRuntime._parse_sse(iter(lines)))
        assert len(events) == 1
        assert events[0]["_heartbeat"] is True

    def test_parse_heartbeat_mixed_with_events(self):
        lines = [
            ":heartbeat",
            "",
            "event:thinking",
            "id:1",
            "data:{}",
            "",
            ":heartbeat",
            "",
            "event:done",
            "id:2",
            'data:{"output":"ok"}',
            "",
        ]
        events = list(AgentRuntime._parse_sse(iter(lines)))
        assert len(events) == 4
        assert events[0]["_heartbeat"] is True
        assert events[1]["event"] == "thinking"
        assert events[2]["_heartbeat"] is True
        assert events[3]["event"] == "done"

    def test_parse_bytes_input(self):
        """requests.iter_lines() yields bytes by default."""
        lines = [
            b"event:thinking",
            b"id:1",
            b'data:{"type":"thinking","content":"processing"}',
            b"",
        ]
        events = list(AgentRuntime._parse_sse(iter(lines)))
        assert len(events) == 1
        assert events[0]["event"] == "thinking"
        assert events[0]["data"]["content"] == "processing"

    def test_parse_event_without_id(self):
        lines = ["event:thinking", 'data:{"type":"thinking"}', ""]
        events = list(AgentRuntime._parse_sse(iter(lines)))
        assert len(events) == 1
        assert events[0]["id"] is None
        assert events[0]["event"] == "thinking"

    def test_parse_event_without_event_type(self):
        lines = ["id:1", 'data:{"type":"message","content":"hi"}', ""]
        events = list(AgentRuntime._parse_sse(iter(lines)))
        assert len(events) == 1
        assert events[0]["event"] is None
        assert events[0]["id"] == "1"
        assert events[0]["data"]["content"] == "hi"

    def test_parse_invalid_json_falls_back_to_content(self):
        lines = ["event:error", "data:not-valid-json", ""]
        events = list(AgentRuntime._parse_sse(iter(lines)))
        assert len(events) == 1
        assert events[0]["data"] == {"content": "not-valid-json"}

    def test_parse_multiline_data(self):
        lines = [
            "event:done",
            "id:1",
            'data:{"output":',
            'data:"hello world"}',
            "",
        ]
        events = list(AgentRuntime._parse_sse(iter(lines)))
        assert len(events) == 1
        # Multiline data lines are joined with \n then parsed
        assert events[0]["data"]["output"] == "hello world"

    def test_parse_empty_input(self):
        events = list(AgentRuntime._parse_sse(iter([])))
        assert len(events) == 0

    def test_parse_only_blank_lines(self):
        events = list(AgentRuntime._parse_sse(iter(["", "", ""])))
        assert len(events) == 0


# ── _sse_to_agent_event() tests ──────────────────────────────────────


class TestSSEToAgentEvent:
    def test_thinking_event(self):
        sse = {"event": "thinking", "data": _java_event("thinking", content="agent_llm")}
        ev = AgentRuntime._sse_to_agent_event(sse, "wf-1")
        assert ev.type == "thinking"
        assert ev.content == "agent_llm"
        assert ev.execution_id == "wf-1"

    def test_tool_call_event(self):
        sse = {
            "event": "tool_call",
            "data": _java_event("tool_call", toolName="search", args={"q": "hello"}),
        }
        ev = AgentRuntime._sse_to_agent_event(sse, "wf-1")
        assert ev.type == "tool_call"
        assert ev.tool_name == "search"
        assert ev.args == {"q": "hello"}

    def test_tool_result_event(self):
        sse = {
            "event": "tool_result",
            "data": _java_event("tool_result", toolName="search", result="found it"),
        }
        ev = AgentRuntime._sse_to_agent_event(sse, "wf-1")
        assert ev.type == "tool_result"
        assert ev.tool_name == "search"
        assert ev.result == "found it"

    def test_handoff_event(self):
        sse = {"event": "handoff", "data": _java_event("handoff", target="support")}
        ev = AgentRuntime._sse_to_agent_event(sse, "wf-1")
        assert ev.type == "handoff"
        assert ev.target == "support"

    def test_waiting_event(self):
        sse = {
            "event": "waiting",
            "data": _java_event(
                "waiting", pendingTool={"tool_name": "approve", "taskRefName": "hitl"}
            ),
        }
        ev = AgentRuntime._sse_to_agent_event(sse, "wf-1")
        assert ev.type == "waiting"

    def test_guardrail_pass_event(self):
        sse = {
            "event": "guardrail_pass",
            "data": _java_event("guardrail_pass", guardrailName="safety_check"),
        }
        ev = AgentRuntime._sse_to_agent_event(sse, "wf-1")
        assert ev.type == "guardrail_pass"
        assert ev.guardrail_name == "safety_check"

    def test_guardrail_fail_event(self):
        sse = {
            "event": "guardrail_fail",
            "data": _java_event(
                "guardrail_fail", guardrailName="pii_filter", content="SSN detected"
            ),
        }
        ev = AgentRuntime._sse_to_agent_event(sse, "wf-1")
        assert ev.type == "guardrail_fail"
        assert ev.guardrail_name == "pii_filter"
        assert ev.content == "SSN detected"

    def test_error_event(self):
        sse = {
            "event": "error",
            "data": _java_event("error", content="Task failed", toolName="task_ref"),
        }
        ev = AgentRuntime._sse_to_agent_event(sse, "wf-1")
        assert ev.type == "error"
        assert ev.content == "Task failed"

    def test_done_event(self):
        sse = {"event": "done", "data": _java_event("done", output={"result": "Final answer"})}
        ev = AgentRuntime._sse_to_agent_event(sse, "wf-1")
        assert ev.type == "done"
        assert ev.output == {"result": "Final answer"}

    def test_message_event(self):
        sse = {"event": "message", "data": _java_event("message", content="Hello")}
        ev = AgentRuntime._sse_to_agent_event(sse, "wf-1")
        assert ev.type == "message"
        assert ev.content == "Hello"

    def test_execution_id_from_data(self):
        """executionId in data overrides the fallback parameter."""
        sse = {"event": "thinking", "data": {"type": "thinking", "executionId": "wf-actual"}}
        ev = AgentRuntime._sse_to_agent_event(sse, "wf-fallback")
        assert ev.execution_id == "wf-actual"

    def test_execution_id_fallback(self):
        """When data has no executionId, uses the fallback parameter."""
        sse = {"event": "thinking", "data": {"type": "thinking"}}
        ev = AgentRuntime._sse_to_agent_event(sse, "wf-fallback")
        assert ev.execution_id == "wf-fallback"

    def test_returns_none_for_missing_type(self):
        sse = {"data": {"content": "something"}}
        ev = AgentRuntime._sse_to_agent_event(sse, "wf-1")
        assert ev is None

    def test_type_from_data_when_event_key_missing(self):
        """When SSE 'event' field is absent, type comes from data['type']."""
        sse = {"data": {"type": "done", "output": "result"}}
        ev = AgentRuntime._sse_to_agent_event(sse, "wf-1")
        assert ev is not None
        assert ev.type == "done"
        assert ev.output == "result"

    def test_camel_to_snake_field_mapping(self):
        """Verify Java camelCase fields map to Python snake_case."""
        sse = {
            "event": "tool_call",
            "data": {
                "type": "tool_call",
                "executionId": "wf-123",
                "toolName": "my_tool",
                "guardrailName": "my_guard",
            },
        }
        ev = AgentRuntime._sse_to_agent_event(sse, "wf-1")
        assert ev.tool_name == "my_tool"
        assert ev.execution_id == "wf-123"
        assert ev.guardrail_name == "my_guard"


# ── End-to-end: wire format → AgentEvent ────────────────────────────


class TestParseAndConvert:
    """Test the full pipeline: SSE wire lines → _parse_sse → _sse_to_agent_event."""

    def test_all_event_types_round_trip(self):
        """Wire format for all 10 event types parses and converts correctly."""
        wire_events = [
            {"event": "thinking", "id": "1", "data": _java_event("thinking", content="agent_llm")},
            {
                "event": "tool_call",
                "id": "2",
                "data": _java_event("tool_call", toolName="search", args={"q": "test"}),
            },
            {
                "event": "tool_result",
                "id": "3",
                "data": _java_event("tool_result", toolName="search", result="data"),
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
            {"event": "done", "id": "10", "data": _java_event("done", output={"result": "Final"})},
        ]

        lines = _make_sse_lines(*wire_events)
        parsed = list(AgentRuntime._parse_sse(iter(lines)))
        assert len(parsed) == 10

        agent_events = [AgentRuntime._sse_to_agent_event(p, "wf-1") for p in parsed]
        assert all(e is not None for e in agent_events)

        types = [e.type for e in agent_events]
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
            "done",
        ]

        # Spot-check field mappings
        assert agent_events[1].tool_name == "search"
        assert agent_events[1].args == {"q": "test"}
        assert agent_events[2].result == "data"
        assert agent_events[3].target == "support"
        assert agent_events[5].guardrail_name == "safety"
        assert agent_events[6].guardrail_name == "pii"
        assert agent_events[6].content == "blocked"
        assert agent_events[9].output == {"result": "Final"}
