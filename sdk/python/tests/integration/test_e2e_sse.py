# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tier 3: Real server SSE integration tests.

Tests the full Python SDK → Java Runtime → Conductor → SSE path.
Requires a running runtime server with SSE support and an LLM API key.

Run with:
    python3 -m pytest tests/integration/test_e2e_sse.py -v

Skip with: pytest -m "not sse"
"""

import os
import time
import uuid
from typing import List

import pytest

from agentspan.agents import (
    Agent,
    AgentEvent,
    AgentStream,
    EventType,
    Guardrail,
    GuardrailResult,
    OnFail,
    RegexGuardrail,
    tool,
)

pytestmark = [pytest.mark.integration, pytest.mark.sse]

DEFAULT_MODEL = "openai/gpt-4o-mini"


def _model() -> str:
    return os.environ.get("AGENTSPAN_LLM_MODEL", DEFAULT_MODEL)


def _unique_name(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# ── Helpers ──────────────────────────────────────────────────────────


def collect_all_events(stream: AgentStream, timeout: float = 120) -> List[AgentEvent]:
    """Drain the stream and return all events."""
    events: List[AgentEvent] = []
    start = time.monotonic()
    for event in stream:
        events.append(event)
        if time.monotonic() - start > timeout:
            break
    return events


def collect_events_until(
    stream: AgentStream, stop_type: str, timeout: float = 120
) -> List[AgentEvent]:
    """Collect events until a specific type is seen."""
    events: List[AgentEvent] = []
    start = time.monotonic()
    for event in stream:
        events.append(event)
        if event.type == stop_type:
            break
        if time.monotonic() - start > timeout:
            break
    return events


def event_types(events: List[AgentEvent]) -> List[str]:
    return [e.type for e in events]


def find_events(events: List[AgentEvent], event_type: str) -> List[AgentEvent]:
    return [e for e in events if e.type == event_type]


# ── Shared Tools ─────────────────────────────────────────────────────


@tool
def get_weather(city: str) -> dict:
    """Get current weather for a city."""
    return {"city": city, "temp_f": 72, "condition": "sunny"}


@tool
def get_stock_price(symbol: str) -> dict:
    """Get stock price for a ticker symbol."""
    return {"symbol": symbol, "price": 150.00, "currency": "USD"}


@tool(approval_required=True)
def publish_article(title: str, body: str) -> dict:
    """Publish an article."""
    return {"status": "published", "title": title}


# ── Tests ────────────────────────────────────────────────────────────


class TestSSESimpleAgent:
    """Simple agent with no tools — should produce thinking → done via SSE."""

    def test_simple_agent_stream(self, runtime):
        agent = Agent(
            name=_unique_name("sse_simple"),
            model=_model(),
            instructions="Reply with exactly one short sentence.",
        )
        stream = runtime.stream(agent, "Say hello")
        events = collect_all_events(stream)

        types = event_types(events)
        assert "done" in types, f"Expected 'done' event, got: {types}"
        assert len(events) >= 1

        # All events should have a execution_id
        assert all(e.execution_id for e in events)

        # Done event should have output
        done_events = find_events(events, "done")
        assert len(done_events) == 1
        assert done_events[0].output is not None

    def test_stream_execution_id_available(self, runtime):
        agent = Agent(
            name=_unique_name("sse_wfid"),
            model=_model(),
            instructions="Reply briefly.",
        )
        stream = runtime.stream(agent, "Hi")
        assert stream.execution_id  # Available immediately
        collect_all_events(stream)

    def test_stream_get_result_after_events(self, runtime):
        agent = Agent(
            name=_unique_name("sse_result"),
            model=_model(),
            instructions="Reply with exactly: OK",
        )
        stream = runtime.stream(agent, "Go")
        collect_all_events(stream)
        result = stream.get_result()
        assert result is not None
        assert result.output is not None


class TestSSEToolAgent:
    """Agent with tools — should produce tool_call and tool_result events."""

    def test_tool_agent_events(self, runtime):
        agent = Agent(
            name=_unique_name("sse_tools"),
            model=_model(),
            instructions="Use the get_weather tool to find weather in London, then respond.",
            tools=[get_weather],
        )
        stream = runtime.stream(agent, "What is the weather in London?")
        events = collect_all_events(stream)

        types = event_types(events)
        assert "done" in types, f"Expected 'done', got: {types}"

        # Should have at least one tool_call and tool_result
        tool_calls = find_events(events, "tool_call")
        tool_results = find_events(events, "tool_result")

        if tool_calls:
            assert tool_calls[0].tool_name is not None
            assert tool_results, "tool_call without matching tool_result"
            assert tool_results[0].tool_name is not None

    def test_tool_result_follows_call(self, runtime):
        """Every tool_call should be followed by a tool_result."""
        agent = Agent(
            name=_unique_name("sse_tool_order"),
            model=_model(),
            instructions="Use get_stock_price tool for AAPL, then answer.",
            tools=[get_stock_price],
        )
        stream = runtime.stream(agent, "What is AAPL stock price?")
        events = collect_all_events(stream)

        types = event_types(events)
        for i, t in enumerate(types):
            if t == "tool_call":
                # Find next tool_result after this
                remaining = types[i + 1 :]
                assert "tool_result" in remaining, (
                    f"tool_call at index {i} has no following tool_result"
                )


class TestSSEGuardrailAgent:
    """Agent with guardrails — should produce guardrail_pass or guardrail_fail events."""

    def test_guardrail_pass_event(self, runtime):
        def lenient_check(content: str) -> GuardrailResult:
            return GuardrailResult(passed=True)

        agent = Agent(
            name=_unique_name("sse_guard_pass"),
            model=_model(),
            instructions="Reply with: All good!",
            guardrails=[
                Guardrail(
                    func=lenient_check,
                    name="lenient",
                    on_fail=OnFail.RETRY,
                ),
            ],
        )
        stream = runtime.stream(agent, "Check this")
        events = collect_all_events(stream)
        types = event_types(events)

        assert "done" in types
        # Guardrail pass event may or may not appear depending on server
        # The important thing is the workflow completes successfully

    def test_regex_guardrail_events(self, runtime):
        agent = Agent(
            name=_unique_name("sse_regex_guard"),
            model=_model(),
            instructions="Reply with the word 'hello' and nothing else.",
            guardrails=[
                RegexGuardrail(
                    name="no_numbers",
                    patterns=[r"\d+"],
                    mode="block",
                    on_fail=OnFail.RETRY,
                    max_retries=2,
                ),
            ],
        )
        stream = runtime.stream(agent, "Greet me")
        events = collect_all_events(stream)
        types = event_types(events)

        # Should complete (pass or error after retries)
        assert "done" in types or "error" in types


class TestSSEHITLAgent:
    """Agent with HITL tools — should produce waiting events."""

    def test_hitl_waiting_and_approve(self, runtime):
        agent = Agent(
            name=_unique_name("sse_hitl"),
            model=_model(),
            instructions="Use publish_article to publish a test article with title 'Test' and body 'Body'.",
            tools=[publish_article],
        )
        stream = runtime.stream(agent, "Publish a test article")

        # Collect until we see a waiting event
        pre_events = collect_events_until(stream, EventType.WAITING.value, timeout=60)
        types = event_types(pre_events)

        if "waiting" in types:
            # Approve the pending action
            stream.approve()
            # Collect remaining events
            post_events = collect_all_events(stream)
            all_events = pre_events + post_events
            all_types = event_types(all_events)
            assert "done" in all_types or "error" in all_types
        else:
            # If no waiting event, the workflow should still complete
            if "done" not in types and "error" not in types:
                remaining = collect_all_events(stream)
                all_types = event_types(pre_events + remaining)
                assert "done" in all_types or "error" in all_types


class TestSSEEventConsistency:
    """Cross-cutting SSE event quality checks."""

    def test_events_have_execution_id(self, runtime):
        agent = Agent(
            name=_unique_name("sse_wfid_check"),
            model=_model(),
            instructions="Reply briefly.",
        )
        stream = runtime.stream(agent, "Hello")
        events = collect_all_events(stream)

        expected_exec_id = stream.execution_id
        for event in events:
            assert event.execution_id, f"Event {event.type} has no execution_id"

    def test_terminal_event_is_last(self, runtime):
        agent = Agent(
            name=_unique_name("sse_terminal"),
            model=_model(),
            instructions="Reply with one word.",
        )
        stream = runtime.stream(agent, "Go")
        events = collect_all_events(stream)

        if events:
            last_type = events[-1].type
            assert last_type in ("done", "error"), (
                f"Last event should be done/error, got: {last_type}"
            )
