# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Mock execution — deterministic agent testing without LLM or server.

Provides :class:`MockEvent` (a factory for :class:`AgentEvent` objects) and
:func:`mock_run` which builds an :class:`AgentResult` from a scripted event
sequence.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from agentspan.agents.result import AgentEvent, AgentResult, EventType

# ── MockEvent factory ──────────────────────────────────────────────────


class MockEvent:
    """Factory for creating :class:`AgentEvent` instances in tests."""

    @staticmethod
    def thinking(content: str) -> AgentEvent:
        """Create a THINKING event."""
        return AgentEvent(type=EventType.THINKING, content=content)

    @staticmethod
    def tool_call(name: str, args: Optional[Dict[str, Any]] = None) -> AgentEvent:
        """Create a TOOL_CALL event."""
        return AgentEvent(type=EventType.TOOL_CALL, tool_name=name, args=args or {})

    @staticmethod
    def tool_result(name: str, result: Any = None) -> AgentEvent:
        """Create a TOOL_RESULT event."""
        return AgentEvent(type=EventType.TOOL_RESULT, tool_name=name, result=result)

    @staticmethod
    def handoff(target: str) -> AgentEvent:
        """Create a HANDOFF event."""
        return AgentEvent(type=EventType.HANDOFF, target=target)

    @staticmethod
    def message(content: str) -> AgentEvent:
        """Create a MESSAGE event."""
        return AgentEvent(type=EventType.MESSAGE, content=content)

    @staticmethod
    def guardrail_pass(name: str, content: str = "") -> AgentEvent:
        """Create a GUARDRAIL_PASS event."""
        return AgentEvent(
            type=EventType.GUARDRAIL_PASS,
            guardrail_name=name,
            content=content,
        )

    @staticmethod
    def guardrail_fail(name: str, content: str = "") -> AgentEvent:
        """Create a GUARDRAIL_FAIL event."""
        return AgentEvent(
            type=EventType.GUARDRAIL_FAIL,
            guardrail_name=name,
            content=content,
        )

    @staticmethod
    def waiting(content: str = "") -> AgentEvent:
        """Create a WAITING event (human-in-the-loop pause)."""
        return AgentEvent(type=EventType.WAITING, content=content)

    @staticmethod
    def done(output: Any) -> AgentEvent:
        """Create a DONE event with the final output."""
        return AgentEvent(type=EventType.DONE, output=output)

    @staticmethod
    def error(content: str) -> AgentEvent:
        """Create an ERROR event."""
        return AgentEvent(type=EventType.ERROR, content=content)


# ── Tool resolution helper ─────────────────────────────────────────────


def _resolve_tool_func(agent: Any, tool_name: str):
    """Find the Python callable for a tool on the agent, if any."""
    if not hasattr(agent, "tools") or agent.tools is None:
        return None
    for t in agent.tools:
        name = getattr(t, "name", None) or getattr(t, "__name__", None)
        if name == tool_name:
            return getattr(t, "func", None) or (t if callable(t) else None)
    return None


# ── mock_run ───────────────────────────────────────────────────────────


def mock_run(
    agent: Any,
    prompt: str,
    events: Sequence[AgentEvent],
    *,
    auto_execute_tools: bool = True,
) -> AgentResult:
    """Build an :class:`AgentResult` from a scripted event sequence.

    This function does **not** call any LLM or Conductor server.  It walks the
    provided events, optionally executes real tool functions when a
    ``TOOL_CALL`` is encountered, and assembles the result.

    Args:
        agent: The :class:`Agent` definition (used to resolve tool functions).
        prompt: The user prompt (stored in messages for context).
        events: Ordered list of :class:`AgentEvent` objects describing the
            scripted execution.
        auto_execute_tools: When ``True`` (default), if a ``TOOL_CALL`` event
            is encountered and the agent has a matching tool with a Python
            function, the function is called and a ``TOOL_RESULT`` event is
            automatically inserted.  Set to ``False`` to skip auto-execution
            (you must then provide ``TOOL_RESULT`` events yourself).

    Returns:
        An :class:`AgentResult` built from the events.
    """
    processed: List[AgentEvent] = []
    tool_calls: List[Dict[str, Any]] = []
    output = None
    status = "COMPLETED"
    pending_call: Optional[Dict[str, Any]] = None

    for ev in events:
        processed.append(ev)

        if ev.type == EventType.TOOL_CALL:
            pending_call = {"name": ev.tool_name, "args": ev.args}

            # Auto-execute the real tool function if available
            if auto_execute_tools:
                func = _resolve_tool_func(agent, ev.tool_name)
                if func is not None:
                    try:
                        tool_result = func(**(ev.args or {}))
                    except Exception as exc:
                        tool_result = f"Error: {exc}"
                    result_event = AgentEvent(
                        type=EventType.TOOL_RESULT,
                        tool_name=ev.tool_name,
                        result=tool_result,
                    )
                    processed.append(result_event)
                    pending_call["result"] = tool_result
                    tool_calls.append(pending_call)
                    pending_call = None

        elif ev.type == EventType.TOOL_RESULT:
            if pending_call is not None:
                pending_call["result"] = ev.result
                tool_calls.append(pending_call)
                pending_call = None
            else:
                tool_calls.append({"name": ev.tool_name, "result": ev.result})

        elif ev.type == EventType.DONE:
            output = ev.output

        elif ev.type == EventType.ERROR:
            output = ev.content
            status = "FAILED"

    # Flush any pending tool call without result
    if pending_call is not None:
        tool_calls.append(pending_call)

    messages: List[Dict[str, Any]] = [{"role": "user", "content": prompt}]
    if output is not None:
        messages.append({"role": "assistant", "content": str(output)})

    return AgentResult(
        output=output,
        execution_id="mock",
        tool_calls=tool_calls,
        status=status,
        events=processed,
        messages=messages,
    )
