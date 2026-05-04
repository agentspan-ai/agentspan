# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""E2E test for Conductor lease extension (heartbeat) behavior.

The Python SDK registers all worker tasks with ``response_timeout_seconds=10``
and ``lease_extend_enabled=True``.  The worker sends periodic heartbeats
(at 80 % of the timeout window) to extend the lease.

This test creates a tool that takes longer than the 10 s timeout.
If lease extension is working, the task completes normally.
If it is broken, the task times out (TIMED_OUT / FAILED).

Requirements:
    - Running Conductor server with conductor-python >= 1.3.11
    - export AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - LLM provider configured
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
    tool,
)

pytestmark = pytest.mark.integration

DEFAULT_MODEL = "openai/gpt-4o-mini"


def _model() -> str:
    return os.environ.get("AGENTSPAN_LLM_MODEL", DEFAULT_MODEL)


def _unique_name(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _event_type_str(event: AgentEvent) -> str:
    t = event.type
    if isinstance(t, EventType):
        return t.value
    return str(t)


def collect_all_events(stream: AgentStream) -> List[AgentEvent]:
    events: List[AgentEvent] = []
    for event in stream:
        events.append(event)
    return events


def event_types(events: List[AgentEvent]) -> List[str]:
    return [_event_type_str(e) for e in events]


@tool
def slow_computation(query: str) -> dict:
    """Run a computation that takes a while to complete."""
    # Sleep for 15 s — well past the 10 s response_timeout_seconds.
    # Without lease extension heartbeats the task would time out.
    time.sleep(15)
    return {"result": f"Computed answer for: {query}", "elapsed_seconds": 15}


class TestLeaseExtension:
    """Verify that lease extension keeps long-running tasks alive."""

    def test_long_tool_completes_with_lease_extension(self, runtime, model):
        """A tool sleeping 15 s must complete — not time out — thanks to heartbeats.

        The default response_timeout_seconds is 10 s.  Without heartbeats the
        Conductor server would mark the task TIMED_OUT after ~10 s.  Lease
        extension sends heartbeats every 8 s (80 % of 10 s) to reset the
        timeout window.  Completion proves the mechanism works end-to-end.
        """
        agent = Agent(
            name=_unique_name("e2e_lease"),
            model=model,
            tools=[slow_computation],
            instructions=(
                "Use the slow_computation tool to answer the user's question. "
                "Always call the tool — do not answer from memory."
            ),
        )

        stream = runtime.stream(agent, "Run a slow computation for 'lease test'.")
        events = collect_all_events(stream)
        types = event_types(events)

        # ── Primary assertion: task completed, not timed out ──
        assert types[-1] == "done", (
            f"Expected terminal 'done' (lease extension should keep task alive). "
            f"Got: {types}"
        )

        result = stream.get_result()
        assert result is not None
        assert result.status == "COMPLETED", (
            f"Expected COMPLETED but got {result.status}. "
            f"If TIMED_OUT, lease extension heartbeats are not working."
        )

        # The tool should have been called at least once
        tool_calls = [t for t in types if t == "tool_call"]
        assert len(tool_calls) >= 1, (
            f"Expected at least 1 tool_call for slow_computation. Events: {types}"
        )
