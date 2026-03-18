# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tests for AsyncAgentStream."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from agentspan.agents.result import (
    AgentEvent,
    AgentHandle,
    AgentResult,
    AsyncAgentStream,
    EventType,
)


def _make_stream(events: list[AgentEvent]) -> AsyncAgentStream:
    """Create an AsyncAgentStream backed by mock events."""
    runtime = MagicMock()

    async def mock_stream_workflow(wf_id):
        for event in events:
            yield event

    runtime._stream_workflow_async = mock_stream_workflow
    runtime.respond_async = AsyncMock()
    runtime.get_status_async = AsyncMock()
    runtime.pause_async = AsyncMock()
    runtime.resume_async = AsyncMock()
    runtime.cancel_async = AsyncMock()

    handle = AgentHandle(workflow_id="wf-test", runtime=runtime)
    return AsyncAgentStream(handle=handle, runtime=runtime)


@pytest.mark.asyncio
async def test_aiter():
    """Async iteration yields all events."""
    events = [
        AgentEvent(type=EventType.THINKING, content="thinking...", workflow_id="wf-test"),
        AgentEvent(type=EventType.TOOL_CALL, tool_name="calc", args={"x": 1}, workflow_id="wf-test"),
        AgentEvent(type=EventType.TOOL_RESULT, tool_name="calc", result=42, workflow_id="wf-test"),
        AgentEvent(type=EventType.DONE, output="answer is 42", workflow_id="wf-test"),
    ]

    stream = _make_stream(events)
    collected = []
    async for event in stream:
        collected.append(event)

    assert len(collected) == 4
    assert collected[0].type == EventType.THINKING
    assert collected[-1].type == EventType.DONE
    assert stream._exhausted is True


@pytest.mark.asyncio
async def test_get_result():
    """get_result() drains the stream and returns AgentResult."""
    events = [
        AgentEvent(type=EventType.TOOL_CALL, tool_name="fn", args={}, workflow_id="wf-test"),
        AgentEvent(type=EventType.TOOL_RESULT, tool_name="fn", result="ok", workflow_id="wf-test"),
        AgentEvent(type=EventType.DONE, output="final", workflow_id="wf-test"),
    ]

    stream = _make_stream(events)
    result = await stream.get_result()

    assert isinstance(result, AgentResult)
    assert result.output == {"result": "final"}
    assert result.status == "COMPLETED"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "fn"
    assert result.workflow_id == "wf-test"


@pytest.mark.asyncio
async def test_get_result_after_iteration():
    """get_result() returns cached result after full iteration."""
    events = [
        AgentEvent(type=EventType.DONE, output="done", workflow_id="wf-test"),
    ]

    stream = _make_stream(events)
    async for _ in stream:
        pass

    result = await stream.get_result()
    assert result.output == {"result": "done"}


@pytest.mark.asyncio
async def test_error_result():
    """Error events produce FAILED status."""
    events = [
        AgentEvent(type=EventType.ERROR, content="something broke", workflow_id="wf-test"),
    ]

    stream = _make_stream(events)
    result = await stream.get_result()
    assert result.status == "FAILED"
    assert result.output == {"error": "something broke", "status": "FAILED"}


@pytest.mark.asyncio
async def test_hitl_methods():
    """HITL convenience methods delegate to handle."""
    events = [
        AgentEvent(type=EventType.WAITING, content="waiting", workflow_id="wf-test"),
    ]

    stream = _make_stream(events)

    await stream.approve()
    stream._runtime.respond_async.assert_called_once_with("wf-test", {"approved": True})

    stream._runtime.respond_async.reset_mock()
    await stream.reject("bad")
    stream._runtime.respond_async.assert_called_once_with(
        "wf-test", {"approved": False, "reason": "bad"}
    )

    stream._runtime.respond_async.reset_mock()
    await stream.send("hi")
    stream._runtime.respond_async.assert_called_once_with("wf-test", {"message": "hi"})

    stream._runtime.respond_async.reset_mock()
    await stream.respond({"custom": "data"})
    stream._runtime.respond_async.assert_called_once_with("wf-test", {"custom": "data"})


@pytest.mark.asyncio
async def test_workflow_id_property():
    """workflow_id property delegates to handle."""
    stream = _make_stream([])
    assert stream.workflow_id == "wf-test"


@pytest.mark.asyncio
async def test_repr():
    """repr shows useful debug info."""
    stream = _make_stream([])
    assert "AsyncAgentStream" in repr(stream)
    assert "wf-test" in repr(stream)
