# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""E2e test: _state_updates propagation through the full pipeline.

Validates the round-trip:
  tool mutates context.state
  → SDK dispatch wraps output with _state_updates
  → JOIN propagates _state_updates
  → merge_state merges into _agent_state workflow variable
  → SET_VARIABLE persists
  → ctx_inject reads _agent_state and prepends to next LLM prompt

Uses algorithmic validation only — no LLM output for assertions.
Includes counterfactuals: verifies state is NOT present when no mutation occurs.

Run with:
    python3 -m pytest tests/integration/test_e2e_state_updates.py -v
"""

import os
import time
import uuid

import pytest
import requests

from agentspan.agents import Agent, AgentEvent, AgentStream, tool
from agentspan.agents.tool import ToolContext

pytestmark = [pytest.mark.integration, pytest.mark.sse]

DEFAULT_MODEL = "openai/gpt-4o-mini"
_SERVER_URL = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")


def _model() -> str:
    return os.environ.get("AGENTSPAN_LLM_MODEL", DEFAULT_MODEL)


def _unique_name(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _conductor_base() -> str:
    return _SERVER_URL.rstrip("/").replace("/api", "")


def _get_workflow_variables(execution_id: str) -> dict:
    """Fetch workflow variables from Conductor API."""
    base = _conductor_base()
    url = f"{base}/api/workflow/{execution_id}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return data.get("variables", {})


def collect_all_events(stream: AgentStream, timeout: float = 120) -> list[AgentEvent]:
    events: list[AgentEvent] = []
    start = time.monotonic()
    for event in stream:
        events.append(event)
        if time.monotonic() - start > timeout:
            break
    return events


# ── Tools ────────────────────────────────────────────────────────────


STATE_KEY = "test_counter"
STATE_VALUE = 42
STATE_LABEL = "state_propagation_test"


@tool
def set_state_tool(context: ToolContext) -> dict:
    """A tool that mutates context.state to test state propagation."""
    context.state[STATE_KEY] = STATE_VALUE
    context.state["label"] = STATE_LABEL
    return {"status": "state_set", "counter": STATE_VALUE}


@tool
def no_state_tool() -> dict:
    """A tool that does NOT mutate state (no context parameter)."""
    return {"status": "ok", "note": "no state mutation"}


# ── Tests ────────────────────────────────────────────────────────────


class TestStateUpdatesPropagation:
    """Validates _state_updates flows through the full pipeline."""

    def test_state_mutation_propagates_to_workflow_variable(self, runtime):
        """Positive test: tool mutates context.state → _agent_state has the values."""
        agent = Agent(
            name=_unique_name("state_pos"),
            model=_model(),
            instructions=(
                "Call the set_state_tool tool exactly once, then respond with 'done'."
            ),
            tools=[set_state_tool],
        )
        stream = runtime.stream(agent, "Run the state tool now.")
        events = collect_all_events(stream)

        # Verify agent completed
        types = [e.type for e in events]
        assert "done" in types, f"Expected 'done' event, got: {types}"

        # Verify tool was actually called (not just LLM saying "done")
        tool_results = [e for e in events if e.type == "tool_result"]
        assert len(tool_results) >= 1, "set_state_tool was never called"

        # Verify _agent_state workflow variable contains our mutations
        execution_id = stream.execution_id
        variables = _get_workflow_variables(execution_id)
        agent_state = variables.get("_agent_state", {})

        assert isinstance(agent_state, dict), (
            f"_agent_state should be a dict, got {type(agent_state)}: {agent_state}"
        )
        assert agent_state.get(STATE_KEY) == STATE_VALUE, (
            f"Expected _agent_state['{STATE_KEY}'] == {STATE_VALUE}, "
            f"got: {agent_state}"
        )
        assert agent_state.get("label") == STATE_LABEL, (
            f"Expected _agent_state['label'] == '{STATE_LABEL}', "
            f"got: {agent_state}"
        )

    def test_no_state_mutation_means_no_agent_state(self, runtime):
        """Counterfactual: tool without context.state mutation → _agent_state empty or absent."""
        agent = Agent(
            name=_unique_name("state_neg"),
            model=_model(),
            instructions=(
                "Call the no_state_tool tool exactly once, then respond with 'done'."
            ),
            tools=[no_state_tool],
        )
        stream = runtime.stream(agent, "Run the no-state tool now.")
        events = collect_all_events(stream)

        types = [e.type for e in events]
        assert "done" in types, f"Expected 'done' event, got: {types}"

        # Verify tool was called
        tool_results = [e for e in events if e.type == "tool_result"]
        assert len(tool_results) >= 1, "no_state_tool was never called"

        # Verify _agent_state is empty or absent
        execution_id = stream.execution_id
        variables = _get_workflow_variables(execution_id)
        agent_state = variables.get("_agent_state", {})

        # _agent_state should be empty (no mutations occurred)
        if isinstance(agent_state, dict):
            assert len(agent_state) == 0, (
                f"_agent_state should be empty when no state mutation occurs, "
                f"but got: {agent_state}"
            )
        else:
            # If it's a string, it should be empty/null
            assert not agent_state, (
                f"_agent_state should be empty/absent, got: {agent_state}"
            )
