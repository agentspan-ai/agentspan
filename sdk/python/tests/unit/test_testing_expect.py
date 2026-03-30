# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tests for agentspan.agents.testing.expect (fluent API)."""

import pytest

from agentspan.agents.result import AgentEvent, AgentResult, EventType
from agentspan.agents.testing.expect import expect
from agentspan.agents.testing.mock import MockEvent, mock_run


class _FakeAgent:
    def __init__(self, tools=None):
        self.tools = tools or []


def _make_result(**kwargs):
    defaults = dict(
        output="Hello",
        execution_id="test",
        status="COMPLETED",
        tool_calls=[],
        events=[],
    )
    defaults.update(kwargs)
    return AgentResult(**defaults)


class TestExpectFluent:
    def test_completed(self):
        result = _make_result(status="COMPLETED")
        expect(result).completed()

    def test_completed_fails(self):
        result = _make_result(status="FAILED")
        with pytest.raises(AssertionError):
            expect(result).completed()

    def test_failed(self):
        result = _make_result(status="FAILED")
        expect(result).failed()

    def test_chaining(self):
        result = _make_result(
            output="Weather is 72F sunny",
            tool_calls=[{"name": "get_weather", "args": {"city": "NYC"}}],
            events=[
                AgentEvent(type=EventType.TOOL_CALL, tool_name="get_weather"),
                AgentEvent(type=EventType.TOOL_RESULT, tool_name="get_weather"),
                AgentEvent(type=EventType.DONE, output="Weather is 72F sunny"),
            ],
        )
        (
            expect(result)
            .completed()
            .used_tool("get_weather", args={"city": "NYC"})
            .output_contains("72F")
            .output_matches(r"\d+F")
            .event_sequence([EventType.TOOL_CALL, EventType.DONE])
            .no_errors()
        )

    def test_did_not_use_tool(self):
        result = _make_result(tool_calls=[{"name": "get_weather"}])
        expect(result).did_not_use_tool("send_email")

    def test_did_not_use_tool_fails(self):
        result = _make_result(tool_calls=[{"name": "send_email"}])
        with pytest.raises(AssertionError):
            expect(result).did_not_use_tool("send_email")

    def test_handoff_to(self):
        result = _make_result(events=[AgentEvent(type=EventType.HANDOFF, target="coder")])
        expect(result).handoff_to("coder")

    def test_guardrails(self):
        result = _make_result(
            events=[
                AgentEvent(type=EventType.GUARDRAIL_PASS, guardrail_name="safety"),
                AgentEvent(type=EventType.GUARDRAIL_FAIL, guardrail_name="pii"),
            ]
        )
        (expect(result).guardrail_passed("safety").guardrail_failed("pii"))

    def test_max_turns(self):
        result = _make_result(
            events=[
                AgentEvent(type=EventType.TOOL_CALL),
                AgentEvent(type=EventType.DONE),
            ]
        )
        expect(result).max_turns(5)

    def test_max_turns_fails(self):
        result = _make_result(
            events=[
                AgentEvent(type=EventType.TOOL_CALL),
                AgentEvent(type=EventType.TOOL_CALL),
                AgentEvent(type=EventType.TOOL_CALL),
                AgentEvent(type=EventType.DONE),
            ]
        )
        with pytest.raises(AssertionError):
            expect(result).max_turns(2)

    def test_output_type(self):
        result = _make_result(output={"key": "value"})
        expect(result).output_type(dict)

    def test_tools_used_exactly(self):
        result = _make_result(tool_calls=[{"name": "a"}, {"name": "b"}])
        expect(result).tools_used_exactly(["a", "b"])

    def test_tool_call_order(self):
        result = _make_result(tool_calls=[{"name": "a"}, {"name": "b"}, {"name": "c"}])
        expect(result).tool_call_order(["a", "c"])


class TestExpectWithMockRun:
    """Integration: mock_run + expect together."""

    def test_full_flow(self):
        agent = _FakeAgent()
        result = mock_run(
            agent,
            "What's the weather?",
            events=[
                MockEvent.thinking("Let me check..."),
                MockEvent.tool_call("get_weather", args={"city": "NYC"}),
                MockEvent.tool_result("get_weather", result={"temp": 72}),
                MockEvent.done("The weather in NYC is 72F."),
            ],
            auto_execute_tools=False,
        )
        (
            expect(result)
            .completed()
            .used_tool("get_weather", args={"city": "NYC"})
            .output_contains("72F")
            .event_sequence(
                [
                    EventType.THINKING,
                    EventType.TOOL_CALL,
                    EventType.TOOL_RESULT,
                    EventType.DONE,
                ]
            )
            .no_errors()
        )

    def test_multi_agent_flow(self):
        agent = _FakeAgent()
        result = mock_run(
            agent,
            "Summarize and translate",
            events=[
                MockEvent.handoff("summarizer"),
                MockEvent.thinking("Summarizing..."),
                MockEvent.handoff("translator"),
                MockEvent.thinking("Translating..."),
                MockEvent.done("Python est un langage populaire."),
            ],
        )
        (
            expect(result)
            .completed()
            .handoff_to("summarizer")
            .handoff_to("translator")
            .output_contains("Python")
        )

    def test_error_flow(self):
        agent = _FakeAgent()
        result = mock_run(
            agent,
            "Bad request",
            events=[MockEvent.error("Rate limit exceeded")],
        )
        (expect(result).failed().output_contains("Rate limit"))
