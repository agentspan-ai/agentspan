# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tests for agentspan.agents.testing.assertions."""

import pytest

from agentspan.agents.result import AgentEvent, AgentResult, EventType
from agentspan.agents.testing.assertions import (
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

# ── Fixtures ───────────────────────────────────────────────────────────


def _make_result(
    output="Hello",
    status="COMPLETED",
    tool_calls=None,
    events=None,
):
    return AgentResult(
        output=output,
        execution_id="test-wf",
        tool_calls=tool_calls or [],
        status=status,
        events=events or [],
    )


# ── Tool assertions ───────────────────────────────────────────────────


class TestAssertToolUsed:
    def test_passes_when_tool_used(self):
        result = _make_result(tool_calls=[{"name": "get_weather", "args": {"city": "NYC"}}])
        assert_tool_used(result, "get_weather")

    def test_fails_when_tool_not_used(self):
        result = _make_result(tool_calls=[{"name": "other_tool"}])
        with pytest.raises(AssertionError, match="get_weather"):
            assert_tool_used(result, "get_weather")

    def test_fails_on_empty_tool_calls(self):
        result = _make_result()
        with pytest.raises(AssertionError):
            assert_tool_used(result, "get_weather")


class TestAssertToolNotUsed:
    def test_passes_when_tool_absent(self):
        result = _make_result(tool_calls=[{"name": "other_tool"}])
        assert_tool_not_used(result, "get_weather")

    def test_fails_when_tool_present(self):
        result = _make_result(tool_calls=[{"name": "get_weather"}])
        with pytest.raises(AssertionError, match="get_weather"):
            assert_tool_not_used(result, "get_weather")


class TestAssertToolCalledWith:
    def test_passes_with_matching_args(self):
        result = _make_result(
            tool_calls=[{"name": "get_weather", "args": {"city": "NYC", "units": "F"}}]
        )
        assert_tool_called_with(result, "get_weather", args={"city": "NYC"})

    def test_fails_with_wrong_args(self):
        result = _make_result(tool_calls=[{"name": "get_weather", "args": {"city": "London"}}])
        with pytest.raises(AssertionError, match="never with matching args"):
            assert_tool_called_with(result, "get_weather", args={"city": "NYC"})

    def test_fails_when_tool_not_found(self):
        result = _make_result()
        with pytest.raises(AssertionError, match="get_weather"):
            assert_tool_called_with(result, "get_weather", args={"city": "NYC"})

    def test_passes_without_args_check(self):
        result = _make_result(tool_calls=[{"name": "get_weather"}])
        assert_tool_called_with(result, "get_weather")


class TestAssertToolCallOrder:
    def test_passes_with_correct_order(self):
        result = _make_result(
            tool_calls=[
                {"name": "search"},
                {"name": "filter"},
                {"name": "format"},
            ]
        )
        assert_tool_call_order(result, ["search", "format"])

    def test_fails_with_wrong_order(self):
        result = _make_result(tool_calls=[{"name": "format"}, {"name": "search"}])
        with pytest.raises(AssertionError, match="subsequence"):
            assert_tool_call_order(result, ["search", "format"])


class TestAssertToolsUsedExactly:
    def test_passes_with_exact_set(self):
        result = _make_result(tool_calls=[{"name": "a"}, {"name": "b"}, {"name": "a"}])
        assert_tools_used_exactly(result, ["a", "b"])

    def test_fails_with_missing(self):
        result = _make_result(tool_calls=[{"name": "a"}])
        with pytest.raises(AssertionError, match="missing"):
            assert_tools_used_exactly(result, ["a", "b"])

    def test_fails_with_extra(self):
        result = _make_result(tool_calls=[{"name": "a"}, {"name": "b"}, {"name": "c"}])
        with pytest.raises(AssertionError, match="unexpected"):
            assert_tools_used_exactly(result, ["a", "b"])


# ── Output assertions ─────────────────────────────────────────────────


class TestAssertOutputContains:
    def test_passes_with_substring(self):
        result = _make_result(output="The weather is 72F and sunny")
        assert_output_contains(result, "72F")

    def test_fails_without_substring(self):
        result = _make_result(output="The weather is cloudy")
        with pytest.raises(AssertionError, match="72F"):
            assert_output_contains(result, "72F")

    def test_case_insensitive(self):
        result = _make_result(output="Hello World")
        assert_output_contains(result, "hello world", case_sensitive=False)

    def test_handles_none_output(self):
        result = _make_result(output=None)
        with pytest.raises(AssertionError):
            assert_output_contains(result, "hello")


class TestAssertOutputMatches:
    def test_passes_with_matching_pattern(self):
        result = _make_result(output="Temperature: 72 degrees")
        assert_output_matches(result, r"\d+ degrees")

    def test_fails_without_match(self):
        result = _make_result(output="It's sunny")
        with pytest.raises(AssertionError, match="pattern"):
            assert_output_matches(result, r"\d+ degrees")


class TestAssertOutputType:
    def test_passes_with_correct_type(self):
        result = _make_result(output={"temp": 72})
        assert_output_type(result, dict)

    def test_fails_with_wrong_type(self):
        result = _make_result(output="string")
        with pytest.raises(AssertionError, match="dict"):
            assert_output_type(result, dict)


# ── Status assertions ──────────────────────────────────────────────────


class TestAssertStatus:
    def test_passes_with_matching_status(self):
        result = _make_result(status="COMPLETED")
        assert_status(result, "COMPLETED")

    def test_fails_with_wrong_status(self):
        result = _make_result(status="FAILED")
        with pytest.raises(AssertionError, match="COMPLETED"):
            assert_status(result, "COMPLETED")


class TestAssertNoErrors:
    def test_passes_without_errors(self):
        result = _make_result(events=[AgentEvent(type=EventType.DONE, output="ok")])
        assert_no_errors(result)

    def test_fails_with_errors(self):
        result = _make_result(events=[AgentEvent(type=EventType.ERROR, content="boom")])
        with pytest.raises(AssertionError, match="boom"):
            assert_no_errors(result)


# ── Event assertions ───────────────────────────────────────────────────


class TestAssertEventsContain:
    def test_passes_when_event_present(self):
        result = _make_result(events=[AgentEvent(type=EventType.TOOL_CALL, tool_name="x")])
        assert_events_contain(result, EventType.TOOL_CALL)

    def test_fails_when_event_absent(self):
        result = _make_result(events=[AgentEvent(type=EventType.DONE)])
        with pytest.raises(AssertionError):
            assert_events_contain(result, EventType.TOOL_CALL)

    def test_expected_false(self):
        result = _make_result(events=[AgentEvent(type=EventType.DONE)])
        assert_events_contain(result, EventType.ERROR, expected=False)

    def test_expected_false_fails_when_present(self):
        result = _make_result(events=[AgentEvent(type=EventType.ERROR, content="bad")])
        with pytest.raises(AssertionError, match="NO event"):
            assert_events_contain(result, EventType.ERROR, expected=False)

    def test_with_attrs(self):
        result = _make_result(events=[AgentEvent(type=EventType.HANDOFF, target="math")])
        assert_events_contain(result, EventType.HANDOFF, target="math")

    def test_with_attrs_mismatch(self):
        result = _make_result(events=[AgentEvent(type=EventType.HANDOFF, target="math")])
        with pytest.raises(AssertionError):
            assert_events_contain(result, EventType.HANDOFF, target="code")


class TestAssertEventSequence:
    def test_passes_with_subsequence(self):
        result = _make_result(
            events=[
                AgentEvent(type=EventType.THINKING),
                AgentEvent(type=EventType.TOOL_CALL),
                AgentEvent(type=EventType.TOOL_RESULT),
                AgentEvent(type=EventType.DONE),
            ]
        )
        assert_event_sequence(
            result,
            [EventType.TOOL_CALL, EventType.DONE],
        )

    def test_fails_with_wrong_order(self):
        result = _make_result(
            events=[
                AgentEvent(type=EventType.DONE),
                AgentEvent(type=EventType.TOOL_CALL),
            ]
        )
        with pytest.raises(AssertionError, match="subsequence"):
            assert_event_sequence(
                result,
                [EventType.TOOL_CALL, EventType.DONE],
            )

    def test_passes_with_string_types(self):
        result = _make_result(
            events=[
                AgentEvent(type=EventType.TOOL_CALL),
                AgentEvent(type=EventType.DONE),
            ]
        )
        assert_event_sequence(result, ["tool_call", "done"])


# ── Multi-agent assertions ────────────────────────────────────────────


class TestAssertHandoffTo:
    def test_passes_with_matching_handoff(self):
        result = _make_result(events=[AgentEvent(type=EventType.HANDOFF, target="math_expert")])
        assert_handoff_to(result, "math_expert")

    def test_fails_without_handoff(self):
        result = _make_result(events=[AgentEvent(type=EventType.DONE)])
        with pytest.raises(AssertionError, match="math_expert"):
            assert_handoff_to(result, "math_expert")


class TestAssertAgentRan:
    def test_passes(self):
        result = _make_result(events=[AgentEvent(type=EventType.HANDOFF, target="summarizer")])
        assert_agent_ran(result, "summarizer")


# ── Guardrail assertions ──────────────────────────────────────────────


class TestAssertGuardrailPassed:
    def test_passes(self):
        result = _make_result(
            events=[AgentEvent(type=EventType.GUARDRAIL_PASS, guardrail_name="safety")]
        )
        assert_guardrail_passed(result, "safety")

    def test_fails(self):
        result = _make_result(events=[])
        with pytest.raises(AssertionError, match="safety"):
            assert_guardrail_passed(result, "safety")


class TestAssertGuardrailFailed:
    def test_passes(self):
        result = _make_result(
            events=[AgentEvent(type=EventType.GUARDRAIL_FAIL, guardrail_name="pii")]
        )
        assert_guardrail_failed(result, "pii")

    def test_fails(self):
        result = _make_result(events=[])
        with pytest.raises(AssertionError, match="pii"):
            assert_guardrail_failed(result, "pii")


# ── Turn assertions ───────────────────────────────────────────────────


class TestAssertMaxTurns:
    def test_passes_under_limit(self):
        result = _make_result(
            events=[
                AgentEvent(type=EventType.TOOL_CALL),
                AgentEvent(type=EventType.TOOL_RESULT),
                AgentEvent(type=EventType.DONE),
            ]
        )
        assert_max_turns(result, 5)

    def test_fails_over_limit(self):
        result = _make_result(
            events=[
                AgentEvent(type=EventType.TOOL_CALL),
                AgentEvent(type=EventType.TOOL_RESULT),
                AgentEvent(type=EventType.TOOL_CALL),
                AgentEvent(type=EventType.TOOL_RESULT),
                AgentEvent(type=EventType.DONE),
            ]
        )
        with pytest.raises(AssertionError, match="3"):
            assert_max_turns(result, 2)
