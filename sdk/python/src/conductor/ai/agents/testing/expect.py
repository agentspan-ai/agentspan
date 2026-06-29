# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Fluent assertion API for agent correctness testing.

Usage::

    from conductor.ai.agents.testing import expect

    (expect(result)
        .completed()
        .used_tool("get_weather", args={"city": "NYC"})
        .did_not_use_tool("send_email")
        .output_contains("72")
        .no_errors())
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Type, Union

from conductor.ai.agents.result import AgentResult, EventType
from conductor.ai.agents.testing.assertions import (
    assert_agent_ran,
    assert_event_sequence,
    assert_events_contain,
    assert_guardrail_failed,
    assert_guardrail_passed,
    assert_handoff_to,
    assert_max_turns,
    assert_no_errors,
    assert_output_contains,
    assert_output_matches,
    assert_output_type,
    assert_status,
    assert_tool_call_order,
    assert_tool_called_with,
    assert_tool_not_used,
    assert_tool_used,
    assert_tools_used_exactly,
)


class AgentResultExpectation:
    """Fluent builder for chaining assertions on an :class:`AgentResult`."""

    def __init__(self, result: AgentResult) -> None:
        self._result = result

    # ── Status ──────────────────────────────────────────────────────

    def completed(self) -> AgentResultExpectation:
        """Assert status is ``"COMPLETED"``."""
        assert_status(self._result, "COMPLETED")
        return self

    def failed(self) -> AgentResultExpectation:
        """Assert status is ``"FAILED"``."""
        assert_status(self._result, "FAILED")
        return self

    def status(self, status: str) -> AgentResultExpectation:
        """Assert a specific status."""
        assert_status(self._result, status)
        return self

    def no_errors(self) -> AgentResultExpectation:
        """Assert no ERROR events."""
        assert_no_errors(self._result)
        return self

    # ── Tools ───────────────────────────────────────────────────────

    def used_tool(
        self, name: str, *, args: Optional[Dict[str, Any]] = None
    ) -> AgentResultExpectation:
        """Assert that a tool was used, optionally with specific args."""
        assert_tool_used(self._result, name)
        if args is not None:
            assert_tool_called_with(self._result, name, args=args)
        return self

    def did_not_use_tool(self, name: str) -> AgentResultExpectation:
        """Assert that a tool was NOT used."""
        assert_tool_not_used(self._result, name)
        return self

    def tool_call_order(self, names: Sequence[str]) -> AgentResultExpectation:
        """Assert tools were called in subsequence order."""
        assert_tool_call_order(self._result, names)
        return self

    def tools_used_exactly(self, names: Sequence[str]) -> AgentResultExpectation:
        """Assert exactly these tools were used (set equality)."""
        assert_tools_used_exactly(self._result, names)
        return self

    # ── Output ──────────────────────────────────────────────────────

    def output_contains(self, text: str, *, case_sensitive: bool = True) -> AgentResultExpectation:
        """Assert output contains a substring."""
        assert_output_contains(self._result, text, case_sensitive=case_sensitive)
        return self

    def output_matches(self, pattern: str) -> AgentResultExpectation:
        """Assert output matches a regex pattern."""
        assert_output_matches(self._result, pattern)
        return self

    def output_type(self, type_: Type) -> AgentResultExpectation:
        """Assert output is an instance of a type."""
        assert_output_type(self._result, type_)
        return self

    # ── Events ──────────────────────────────────────────────────────

    def events_contain(
        self,
        event_type: Union[str, EventType],
        *,
        expected: bool = True,
        **attrs: Any,
    ) -> AgentResultExpectation:
        """Assert an event of the given type exists (or does not)."""
        assert_events_contain(self._result, event_type, expected=expected, **attrs)
        return self

    def event_sequence(self, types: Sequence[Union[str, EventType]]) -> AgentResultExpectation:
        """Assert events appear in subsequence order."""
        assert_event_sequence(self._result, types)
        return self

    # ── Multi-agent ─────────────────────────────────────────────────

    def handoff_to(self, agent_name: str) -> AgentResultExpectation:
        """Assert a handoff to the given agent occurred."""
        assert_handoff_to(self._result, agent_name)
        return self

    def agent_ran(self, agent_name: str) -> AgentResultExpectation:
        """Assert that an agent participated."""
        assert_agent_ran(self._result, agent_name)
        return self

    # ── Guardrails ──────────────────────────────────────────────────

    def guardrail_passed(self, name: str) -> AgentResultExpectation:
        """Assert that a guardrail passed."""
        assert_guardrail_passed(self._result, name)
        return self

    def guardrail_failed(self, name: str) -> AgentResultExpectation:
        """Assert that a guardrail failed."""
        assert_guardrail_failed(self._result, name)
        return self

    # ── Turns ───────────────────────────────────────────────────────

    def max_turns(self, n: int) -> AgentResultExpectation:
        """Assert the agent did not exceed *n* turns."""
        assert_max_turns(self._result, n)
        return self


def expect(result: AgentResult) -> AgentResultExpectation:
    """Create a fluent assertion builder for an :class:`AgentResult`.

    Example::

        (expect(result)
            .completed()
            .used_tool("get_weather")
            .output_contains("sunny")
            .no_errors())
    """
    return AgentResultExpectation(result)
