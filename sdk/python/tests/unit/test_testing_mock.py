# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tests for agentspan.agents.testing.mock."""

from agentspan.agents.result import EventType
from agentspan.agents.testing.mock import MockEvent, mock_run

# ── Helpers ────────────────────────────────────────────────────────────


class _FakeAgent:
    """Minimal agent-like object for testing."""

    def __init__(self, tools=None):
        self.tools = tools or []


class _FakeTool:
    """Minimal tool-like object."""

    def __init__(self, name, func):
        self.name = name
        self.func = func


# ── MockEvent ──────────────────────────────────────────────────────────


class TestMockEvent:
    def test_thinking(self):
        ev = MockEvent.thinking("Let me think...")
        assert ev.type == EventType.THINKING
        assert ev.content == "Let me think..."

    def test_tool_call(self):
        ev = MockEvent.tool_call("get_weather", args={"city": "NYC"})
        assert ev.type == EventType.TOOL_CALL
        assert ev.tool_name == "get_weather"
        assert ev.args == {"city": "NYC"}

    def test_tool_call_no_args(self):
        ev = MockEvent.tool_call("ping")
        assert ev.args == {}

    def test_tool_result(self):
        ev = MockEvent.tool_result("get_weather", result={"temp": 72})
        assert ev.type == EventType.TOOL_RESULT
        assert ev.tool_name == "get_weather"
        assert ev.result == {"temp": 72}

    def test_handoff(self):
        ev = MockEvent.handoff("math_expert")
        assert ev.type == EventType.HANDOFF
        assert ev.target == "math_expert"

    def test_message(self):
        ev = MockEvent.message("Hello")
        assert ev.type == EventType.MESSAGE
        assert ev.content == "Hello"

    def test_guardrail_pass(self):
        ev = MockEvent.guardrail_pass("safety")
        assert ev.type == EventType.GUARDRAIL_PASS
        assert ev.guardrail_name == "safety"

    def test_guardrail_fail(self):
        ev = MockEvent.guardrail_fail("pii", "Contains SSN")
        assert ev.type == EventType.GUARDRAIL_FAIL
        assert ev.guardrail_name == "pii"
        assert ev.content == "Contains SSN"

    def test_waiting(self):
        ev = MockEvent.waiting("Approval needed")
        assert ev.type == EventType.WAITING
        assert ev.content == "Approval needed"

    def test_done(self):
        ev = MockEvent.done("The answer is 42")
        assert ev.type == EventType.DONE
        assert ev.output == "The answer is 42"

    def test_error(self):
        ev = MockEvent.error("Something broke")
        assert ev.type == EventType.ERROR
        assert ev.content == "Something broke"


# ── mock_run ───────────────────────────────────────────────────────────


class TestMockRun:
    def test_simple_done(self):
        agent = _FakeAgent()
        result = mock_run(agent, "Hello", events=[MockEvent.done("Hi there!")])
        assert result.output == "Hi there!"
        assert result.status == "COMPLETED"
        assert result.execution_id == "mock"
        assert len(result.events) == 1
        assert result.tool_calls == []

    def test_tool_call_with_manual_result(self):
        agent = _FakeAgent()
        result = mock_run(
            agent,
            "Weather?",
            events=[
                MockEvent.tool_call("get_weather", args={"city": "NYC"}),
                MockEvent.tool_result("get_weather", result={"temp": 72}),
                MockEvent.done("It's 72F"),
            ],
            auto_execute_tools=False,
        )
        assert result.output == "It's 72F"
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "get_weather"
        assert result.tool_calls[0]["args"] == {"city": "NYC"}
        assert result.tool_calls[0]["result"] == {"temp": 72}

    def test_auto_execute_tools(self):
        def fake_weather(city: str) -> dict:
            return {"city": city, "temp": 72}

        tool = _FakeTool("get_weather", fake_weather)
        agent = _FakeAgent(tools=[tool])

        result = mock_run(
            agent,
            "Weather?",
            events=[
                MockEvent.tool_call("get_weather", args={"city": "NYC"}),
                MockEvent.done("It's 72F"),
            ],
        )
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["result"] == {"city": "NYC", "temp": 72}
        # Auto-inserted tool_result event
        assert len(result.events) == 3  # tool_call + auto tool_result + done

    def test_auto_execute_tool_error(self):
        def bad_tool(city: str) -> dict:
            raise ValueError("API down")

        tool = _FakeTool("get_weather", bad_tool)
        agent = _FakeAgent(tools=[tool])

        result = mock_run(
            agent,
            "Weather?",
            events=[
                MockEvent.tool_call("get_weather", args={"city": "NYC"}),
                MockEvent.done("Sorry, tool failed"),
            ],
        )
        assert "Error: API down" in str(result.tool_calls[0]["result"])

    def test_error_event_sets_failed_status(self):
        agent = _FakeAgent()
        result = mock_run(
            agent,
            "Hello",
            events=[MockEvent.error("Something went wrong")],
        )
        assert result.status == "FAILED"
        assert result.output == "Something went wrong"

    def test_messages_include_prompt_and_output(self):
        agent = _FakeAgent()
        result = mock_run(agent, "Hi", events=[MockEvent.done("Hello!")])
        assert result.messages[0] == {"role": "user", "content": "Hi"}
        assert result.messages[1] == {"role": "assistant", "content": "Hello!"}

    def test_multiple_tool_calls(self):
        agent = _FakeAgent()
        result = mock_run(
            agent,
            "Complex task",
            events=[
                MockEvent.tool_call("search", args={"q": "test"}),
                MockEvent.tool_result("search", result=["a", "b"]),
                MockEvent.tool_call("format", args={"items": ["a", "b"]}),
                MockEvent.tool_result("format", result="a, b"),
                MockEvent.done("Results: a, b"),
            ],
            auto_execute_tools=False,
        )
        assert len(result.tool_calls) == 2
        assert result.tool_calls[0]["name"] == "search"
        assert result.tool_calls[1]["name"] == "format"

    def test_handoff_events_preserved(self):
        agent = _FakeAgent()
        result = mock_run(
            agent,
            "Do math",
            events=[
                MockEvent.handoff("math_expert"),
                MockEvent.done("42"),
            ],
        )
        handoffs = [ev for ev in result.events if ev.type == EventType.HANDOFF]
        assert len(handoffs) == 1
        assert handoffs[0].target == "math_expert"

    def test_guardrail_events_preserved(self):
        agent = _FakeAgent()
        result = mock_run(
            agent,
            "Test",
            events=[
                MockEvent.guardrail_pass("safety"),
                MockEvent.guardrail_fail("pii", "Found SSN"),
                MockEvent.done("Filtered output"),
            ],
        )
        assert any(
            ev.type == EventType.GUARDRAIL_PASS and ev.guardrail_name == "safety"
            for ev in result.events
        )
        assert any(
            ev.type == EventType.GUARDRAIL_FAIL and ev.guardrail_name == "pii"
            for ev in result.events
        )

    def test_pending_tool_call_flushed(self):
        """Tool call without result is still recorded."""
        agent = _FakeAgent()
        result = mock_run(
            agent,
            "Test",
            events=[MockEvent.tool_call("slow_tool", args={"x": 1})],
            auto_execute_tools=False,
        )
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "slow_tool"
        assert "result" not in result.tool_calls[0]
