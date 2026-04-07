#!/usr/bin/env python3
"""
01 — Basic Agent Mock Tests
============================

The simplest possible mock tests. No server, no LLM, no API keys needed.

Covers:
  - Creating a single agent with tools
  - mock_run() with scripted events
  - Basic status and output assertions
  - Tool usage assertions
  - The fluent expect() API

Run:
    pytest examples/mock_tests/01_basic_agent.py -v
"""

import pytest

from agentspan.agents import Agent, tool
from agentspan.agents.testing import (
    MockEvent,
    assert_no_errors,
    assert_output_contains,
    assert_status,
    assert_tool_not_used,
    assert_tool_used,
    expect,
    mock_run,
)


# ── Tools ────────────────────────────────────────────────────────────


@tool
def get_weather(city: str) -> str:
    """Get current weather for a city."""
    return f"Sunny, 72°F in {city}"


@tool
def get_time(timezone: str) -> str:
    """Get current time in a timezone."""
    return f"2:30 PM in {timezone}"


# ── Agent ────────────────────────────────────────────────────────────

assistant = Agent(
    name="assistant",
    model="openai/gpt-4o",
    instructions="You are a helpful assistant. Use tools when needed.",
    tools=[get_weather, get_time],
)


# ── Tests ────────────────────────────────────────────────────────────


class TestBasicCompletion:
    """Agent completes successfully and returns output."""

    def test_simple_response(self):
        """Agent answers without using any tools."""
        result = mock_run(
            assistant,
            "Hello, how are you?",
            events=[
                MockEvent.done("I'm doing well! How can I help you today?"),
            ],
        )

        assert_status(result, "COMPLETED")
        assert_no_errors(result)
        assert_output_contains(result, "help", case_sensitive=False)

    def test_tool_call_and_response(self):
        """Agent calls a tool and incorporates the result."""
        result = mock_run(
            assistant,
            "What's the weather in Tokyo?",
            events=[
                MockEvent.tool_call("get_weather", args={"city": "Tokyo"}),
                MockEvent.tool_result("get_weather", result="Sunny, 72°F in Tokyo"),
                MockEvent.done("It's currently sunny and 72°F in Tokyo."),
            ],
            auto_execute_tools=False,
        )

        assert_status(result, "COMPLETED")
        assert_tool_used(result, "get_weather")
        assert_tool_not_used(result, "get_time")
        assert_output_contains(result, "Tokyo")

    def test_multiple_tool_calls(self):
        """Agent calls multiple tools in sequence."""
        result = mock_run(
            assistant,
            "What's the weather and time in London?",
            events=[
                MockEvent.tool_call("get_weather", args={"city": "London"}),
                MockEvent.tool_result("get_weather", result="Rainy, 55°F in London"),
                MockEvent.tool_call("get_time", args={"timezone": "Europe/London"}),
                MockEvent.tool_result("get_time", result="7:30 PM in Europe/London"),
                MockEvent.done("In London it's rainy at 55°F, and the time is 7:30 PM."),
            ],
            auto_execute_tools=False,
        )

        assert_tool_used(result, "get_weather")
        assert_tool_used(result, "get_time")
        assert_no_errors(result)


class TestFluentExpectAPI:
    """Same assertions using the chainable expect() API."""

    def test_expect_completed_with_output(self):
        """Fluent syntax for status + output checks."""
        result = mock_run(
            assistant,
            "What's the weather in Paris?",
            events=[
                MockEvent.tool_call("get_weather", args={"city": "Paris"}),
                MockEvent.tool_result("get_weather", result="Cloudy, 60°F"),
                MockEvent.done("It's cloudy and 60°F in Paris."),
            ],
            auto_execute_tools=False,
        )

        (
            expect(result)
            .completed()
            .used_tool("get_weather")
            .did_not_use_tool("get_time")
            .output_contains("Paris")
            .no_errors()
        )

    def test_expect_with_tool_args(self):
        """Verify the exact arguments passed to a tool."""
        result = mock_run(
            assistant,
            "Weather in Berlin please",
            events=[
                MockEvent.tool_call("get_weather", args={"city": "Berlin"}),
                MockEvent.tool_result("get_weather", result="Snowy, 28°F"),
                MockEvent.done("Berlin is snowy at 28°F."),
            ],
            auto_execute_tools=False,
        )

        (
            expect(result)
            .completed()
            .used_tool("get_weather", args={"city": "Berlin"})
            .no_errors()
        )


class TestAutoExecuteTools:
    """When auto_execute_tools=True (default), real tool functions run."""

    def test_auto_execute(self):
        """Tool functions execute automatically — no need for tool_result events."""
        result = mock_run(
            assistant,
            "Weather in NYC?",
            events=[
                MockEvent.tool_call("get_weather", args={"city": "NYC"}),
                # No tool_result needed — get_weather() runs automatically
                MockEvent.done("It's sunny and 72°F in NYC."),
            ],
            # auto_execute_tools=True is the default
        )

        assert_tool_used(result, "get_weather")
        assert_status(result, "COMPLETED")


class TestErrorScenarios:
    """Agent encounters errors during execution."""

    def test_error_event(self):
        """An error event marks the result as failed."""
        result = mock_run(
            assistant,
            "Do something impossible",
            events=[
                MockEvent.error("Something went wrong"),
            ],
        )

        assert_status(result, "FAILED")

        # expect() can assert failure too
        expect(result).failed()

    def test_thinking_then_response(self):
        """Thinking events are recorded but don't affect the result."""
        result = mock_run(
            assistant,
            "What's 2+2?",
            events=[
                MockEvent.thinking("Let me think about this..."),
                MockEvent.done("2 + 2 = 4"),
            ],
        )

        (
            expect(result)
            .completed()
            .output_contains("4")
            .no_errors()
        )
