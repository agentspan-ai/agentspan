# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Composable assertion functions for agent correctness testing.

Every function takes an :class:`AgentResult` as its first argument and raises
:class:`AssertionError` with a clear message on failure.  They work identically
whether the result came from :func:`mock_run` or a live ``runtime.run()`` call.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Sequence, Type, Union

from conductor.ai.agents.result import AgentResult, EventType

# ── Tool assertions ────────────────────────────────────────────────────


def assert_tool_used(result: AgentResult, name: str) -> None:
    """Assert that a tool was called at least once.

    Args:
        result: The agent execution result.
        name: The tool name to look for.
    """
    names = [tc.get("name") for tc in result.tool_calls]
    if name not in names:
        raise AssertionError(
            f"Expected tool '{name}' to be used, but it was not.\nTools used: {names}"
        )


def assert_tool_not_used(result: AgentResult, name: str) -> None:
    """Assert that a tool was never called.

    Args:
        result: The agent execution result.
        name: The tool name that should not appear.
    """
    names = [tc.get("name") for tc in result.tool_calls]
    if name in names:
        raise AssertionError(
            f"Expected tool '{name}' NOT to be used, but it was called "
            f"{names.count(name)} time(s).\nTools used: {names}"
        )


def assert_tool_called_with(
    result: AgentResult,
    name: str,
    *,
    args: Optional[Dict[str, Any]] = None,
) -> None:
    """Assert that a tool was called with specific arguments (subset match).

    Args:
        result: The agent execution result.
        name: The tool name.
        args: Expected arguments.  Each key-value pair must be present in at
            least one call to this tool.  Extra keys in the actual call are OK.
    """
    matching = [tc for tc in result.tool_calls if tc.get("name") == name]
    if not matching:
        all_names = [tc.get("name") for tc in result.tool_calls]
        raise AssertionError(
            f"Expected tool '{name}' to be called, but it was not.\nTools used: {all_names}"
        )

    if args is None:
        return

    for tc in matching:
        tc_args = tc.get("args") or {}
        if all(tc_args.get(k) == v for k, v in args.items()):
            return

    raise AssertionError(
        f"Tool '{name}' was called but never with matching args.\n"
        f"Expected (subset): {args}\n"
        f"Actual calls: {[tc.get('args') for tc in matching]}"
    )


def assert_tool_call_order(result: AgentResult, names: Sequence[str]) -> None:
    """Assert that tools were called in a specific subsequence order.

    The tools in *names* must appear in order within the tool calls, but other
    tool calls may appear between them.

    Args:
        result: The agent execution result.
        names: Expected tool names in order.
    """
    actual = [tc.get("name") for tc in result.tool_calls]
    idx = 0
    for tool_name in actual:
        if idx < len(names) and tool_name == names[idx]:
            idx += 1
    if idx < len(names):
        raise AssertionError(
            f"Expected tool call order {list(names)} (subsequence), "
            f"but only matched up to index {idx} ('{names[idx]}').\n"
            f"Actual tool calls: {actual}"
        )


def assert_tools_used_exactly(result: AgentResult, names: Sequence[str]) -> None:
    """Assert that exactly these tools were used (set equality, ignoring order and count).

    Args:
        result: The agent execution result.
        names: The exact set of tool names expected.
    """
    actual = set(tc.get("name") for tc in result.tool_calls)
    expected = set(names)
    if actual != expected:
        missing = expected - actual
        extra = actual - expected
        parts = []
        if missing:
            parts.append(f"missing: {missing}")
        if extra:
            parts.append(f"unexpected: {extra}")
        raise AssertionError(
            f"Expected exactly tools {sorted(expected)}, got {sorted(actual)}.\n{'; '.join(parts)}"
        )


# ── Output assertions ──────────────────────────────────────────────────


def assert_output_contains(result: AgentResult, text: str, *, case_sensitive: bool = True) -> None:
    """Assert that the agent output contains a substring.

    Args:
        result: The agent execution result.
        text: The substring to look for.
        case_sensitive: Whether the match is case-sensitive (default True).
    """
    output = str(result.output) if result.output is not None else ""
    haystack = output if case_sensitive else output.lower()
    needle = text if case_sensitive else text.lower()
    if needle not in haystack:
        preview = output[:200] + ("..." if len(output) > 200 else "")
        raise AssertionError(
            f"Expected output to contain '{text}', but it does not.\nOutput: {preview}"
        )


def assert_output_matches(result: AgentResult, pattern: str) -> None:
    """Assert that the agent output matches a regular expression.

    Args:
        result: The agent execution result.
        pattern: A regular expression pattern (searched, not full-matched).
    """
    output = str(result.output) if result.output is not None else ""
    if not re.search(pattern, output):
        preview = output[:200] + ("..." if len(output) > 200 else "")
        raise AssertionError(
            f"Expected output to match pattern '{pattern}', but it does not.\nOutput: {preview}"
        )


def assert_output_type(result: AgentResult, type_: Type) -> None:
    """Assert that the agent output is an instance of the given type.

    Args:
        result: The agent execution result.
        type_: The expected type.
    """
    if not isinstance(result.output, type_):
        raise AssertionError(
            f"Expected output to be {type_.__name__}, "
            f"got {type(result.output).__name__}: {result.output!r}"
        )


# ── Status assertions ──────────────────────────────────────────────────


def assert_status(result: AgentResult, status: str) -> None:
    """Assert that the agent execution status matches.

    Args:
        result: The agent execution result.
        status: Expected status (e.g. ``"COMPLETED"``, ``"FAILED"``).
    """
    if result.status != status:
        raise AssertionError(f"Expected status '{status}', got '{result.status}'.")


def assert_no_errors(result: AgentResult) -> None:
    """Assert that no error events occurred during execution.

    Args:
        result: The agent execution result.
    """
    errors = [ev for ev in result.events if ev.type == EventType.ERROR]
    if errors:
        messages = [ev.content for ev in errors]
        raise AssertionError(
            f"Expected no errors, but {len(errors)} error(s) occurred.\nError messages: {messages}"
        )


# ── Event assertions ───────────────────────────────────────────────────


def assert_events_contain(
    result: AgentResult,
    event_type: Union[str, EventType],
    *,
    expected: bool = True,
    **attrs: Any,
) -> None:
    """Assert that at least one event of the given type exists (or does not).

    Args:
        result: The agent execution result.
        event_type: The event type to look for.
        expected: If ``True`` (default), assert the event exists.
            If ``False``, assert it does NOT exist.
        **attrs: Additional attributes to match on the event (e.g.
            ``target="math_expert"``).
    """
    event_type_str = event_type.value if isinstance(event_type, EventType) else event_type
    matching = [
        ev
        for ev in result.events
        if ev.type == event_type_str and all(getattr(ev, k, None) == v for k, v in attrs.items())
    ]

    if expected and not matching:
        raise AssertionError(
            f"Expected event of type '{event_type_str}'"
            + (f" with {attrs}" if attrs else "")
            + ", but none found.\n"
            f"Event types present: {[ev.type for ev in result.events]}"
        )
    if not expected and matching:
        raise AssertionError(
            f"Expected NO event of type '{event_type_str}'"
            + (f" with {attrs}" if attrs else "")
            + f", but found {len(matching)}."
        )


def assert_event_sequence(
    result: AgentResult,
    types: Sequence[Union[str, EventType]],
) -> None:
    """Assert that events of the given types appear in subsequence order.

    Other events may appear between the expected ones.

    Args:
        result: The agent execution result.
        types: Expected event types in order.
    """
    expected = [t.value if isinstance(t, EventType) else t for t in types]
    actual_types = [ev.type for ev in result.events]

    idx = 0
    for ev_type in actual_types:
        if idx < len(expected) and ev_type == expected[idx]:
            idx += 1
    if idx < len(expected):
        raise AssertionError(
            f"Expected event sequence {expected} (subsequence), "
            f"but only matched up to index {idx} ('{expected[idx]}').\n"
            f"Actual event types: {actual_types}"
        )


# ── Multi-agent assertions ─────────────────────────────────────────────


def assert_handoff_to(result: AgentResult, agent_name: str) -> None:
    """Assert that a handoff event occurred targeting the given agent.

    Args:
        result: The agent execution result.
        agent_name: The expected target agent name.
    """
    handoffs = [
        ev for ev in result.events if ev.type == EventType.HANDOFF and ev.target == agent_name
    ]
    if not handoffs:
        all_handoffs = [ev.target for ev in result.events if ev.type == EventType.HANDOFF]
        raise AssertionError(
            f"Expected handoff to '{agent_name}', but none found.\n"
            f"Handoffs that occurred: {all_handoffs}"
        )


def assert_agent_ran(result: AgentResult, agent_name: str) -> None:
    """Assert that an agent participated in the execution (via handoff events).

    Args:
        result: The agent execution result.
        agent_name: The expected agent name.
    """
    # Check handoff events for the agent name
    assert_handoff_to(result, agent_name)


# ── Guardrail assertions ──────────────────────────────────────────────


def assert_guardrail_passed(result: AgentResult, name: str) -> None:
    """Assert that a guardrail passed during execution.

    Args:
        result: The agent execution result.
        name: The guardrail name.
    """
    passing = [
        ev
        for ev in result.events
        if ev.type == EventType.GUARDRAIL_PASS and ev.guardrail_name == name
    ]
    if not passing:
        all_guardrails = [
            (ev.type, ev.guardrail_name)
            for ev in result.events
            if ev.type in (EventType.GUARDRAIL_PASS, EventType.GUARDRAIL_FAIL)
        ]
        raise AssertionError(
            f"Expected guardrail '{name}' to pass, but no matching event found.\n"
            f"Guardrail events: {all_guardrails}"
        )


def assert_guardrail_failed(result: AgentResult, name: str) -> None:
    """Assert that a guardrail failed during execution.

    Args:
        result: The agent execution result.
        name: The guardrail name.
    """
    failing = [
        ev
        for ev in result.events
        if ev.type == EventType.GUARDRAIL_FAIL and ev.guardrail_name == name
    ]
    if not failing:
        all_guardrails = [
            (ev.type, ev.guardrail_name)
            for ev in result.events
            if ev.type in (EventType.GUARDRAIL_PASS, EventType.GUARDRAIL_FAIL)
        ]
        raise AssertionError(
            f"Expected guardrail '{name}' to fail, but no matching event found.\n"
            f"Guardrail events: {all_guardrails}"
        )


# ── Turn/iteration assertions ─────────────────────────────────────────


def assert_max_turns(result: AgentResult, n: int) -> None:
    """Assert that the agent did not exceed *n* LLM turns.

    A "turn" is counted as each TOOL_CALL or DONE event (i.e. each time the
    LLM produced output that led to an action or final answer).

    Args:
        result: The agent execution result.
        n: Maximum number of turns allowed.
    """
    turns = sum(1 for ev in result.events if ev.type in (EventType.TOOL_CALL, EventType.DONE))
    if turns > n:
        raise AssertionError(f"Expected at most {n} turn(s), but the agent took {turns}.")
