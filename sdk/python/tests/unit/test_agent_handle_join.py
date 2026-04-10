# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for AgentHandle.join() and AgentHandle.join_async()."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentspan.agents.result import (
    AgentHandle,
    AgentResult,
    AgentStatus,
    FinishReason,
    Status,
)


def _make_runtime(*, statuses, token_usage=None):
    """Build a minimal mock runtime that drives join().

    ``statuses`` is a list of AgentStatus objects that get_status()
    returns in sequence (one per poll iteration).
    """
    runtime = MagicMock()
    runtime.get_status.side_effect = list(statuses)

    async def _async_get_status(execution_id):
        if len(statuses) > 1:
            return statuses.pop(0)
        return statuses[0]

    runtime.get_status_async = AsyncMock(side_effect=_async_get_status)
    runtime._normalize_output.side_effect = lambda output, raw_status, reason=None: (
        output if isinstance(output, dict) else {"result": output}
    )
    runtime._derive_finish_reason.return_value = FinishReason.STOP
    runtime._extract_token_usage.return_value = token_usage
    return runtime


class TestAgentHandleJoinSync:
    """Tests for AgentHandle.join()."""

    def test_join_returns_agent_result_when_complete(self):
        """join() returns AgentResult when execution completes on first poll."""
        completed = AgentStatus(
            execution_id="wf-1",
            is_complete=True,
            status="COMPLETED",
            output={"result": "hello"},
        )
        runtime = _make_runtime(statuses=[completed])
        handle = AgentHandle(execution_id="wf-1", runtime=runtime)

        with patch("time.sleep"):
            result = handle.join()

        assert isinstance(result, AgentResult)
        assert result.execution_id == "wf-1"
        assert result.status == Status.COMPLETED

    def test_join_polls_until_complete(self):
        """join() keeps polling until is_complete=True."""
        running = AgentStatus(execution_id="wf-1", is_complete=False, is_running=True, status="RUNNING", output=None)
        completed = AgentStatus(
            execution_id="wf-1", is_complete=True, status="COMPLETED", output={"result": "done"}
        )
        runtime = _make_runtime(statuses=[running, running, completed])
        handle = AgentHandle(execution_id="wf-1", runtime=runtime)

        with patch("time.sleep"):
            result = handle.join()

        assert isinstance(result, AgentResult)
        assert result.status == Status.COMPLETED

    def test_join_raises_timeout_error_when_exhausted(self):
        """join(timeout=2) raises TimeoutError if execution never completes."""
        running = AgentStatus(
            execution_id="wf-99", is_complete=False, is_running=True, status="RUNNING", output=None
        )
        runtime = _make_runtime(statuses=[running] * 100)
        handle = AgentHandle(execution_id="wf-99", runtime=runtime)

        with patch("time.sleep"):
            with pytest.raises(TimeoutError) as exc_info:
                handle.join(timeout=2)

        assert "wf-99" in str(exc_info.value)
        assert "2" in str(exc_info.value)

    def test_join_timeout_none_uses_no_deadline(self):
        """join(timeout=None) polls until complete with no timeout guard."""
        completed = AgentStatus(
            execution_id="wf-2", is_complete=True, status="COMPLETED", output={"result": "ok"}
        )
        runtime = _make_runtime(statuses=[completed])
        handle = AgentHandle(execution_id="wf-2", runtime=runtime)

        with patch("time.sleep"):
            result = handle.join(timeout=None)

        assert result.execution_id == "wf-2"

    def test_join_result_carries_finish_reason(self):
        """join() sets finish_reason from _derive_finish_reason."""
        completed = AgentStatus(
            execution_id="wf-3", is_complete=True, status="COMPLETED", output={"result": "x"}
        )
        runtime = _make_runtime(statuses=[completed])
        runtime._derive_finish_reason.return_value = FinishReason.STOP
        handle = AgentHandle(execution_id="wf-3", runtime=runtime)

        with patch("time.sleep"):
            result = handle.join()

        assert result.finish_reason == FinishReason.STOP

    def test_join_result_carries_error_on_failure(self):
        """join() sets error field when execution failed."""
        failed = AgentStatus(
            execution_id="wf-4",
            is_complete=True,
            status="FAILED",
            output=None,
            reason="API key invalid",
        )
        runtime = _make_runtime(statuses=[failed])
        runtime._derive_finish_reason.return_value = FinishReason.ERROR
        handle = AgentHandle(execution_id="wf-4", runtime=runtime)

        with patch("time.sleep"):
            result = handle.join()

        assert result.error == "API key invalid"
        assert result.status == Status.FAILED

    def test_join_timeout_error_message_contains_execution_id_and_seconds(self):
        """TimeoutError message includes execution_id and timeout value."""
        running = AgentStatus(
            execution_id="exec-abc", is_complete=False, status="RUNNING", output=None
        )
        runtime = _make_runtime(statuses=[running] * 100)
        handle = AgentHandle(execution_id="exec-abc", runtime=runtime)

        with patch("time.sleep"):
            with pytest.raises(TimeoutError) as exc_info:
                handle.join(timeout=5)

        msg = str(exc_info.value)
        assert "exec-abc" in msg
        assert "5" in msg


class TestAgentHandleJoinAsync:
    """Tests for AgentHandle.join_async()."""

    @pytest.mark.asyncio
    async def test_join_async_returns_agent_result(self):
        """join_async() returns AgentResult when execution completes."""
        completed = AgentStatus(
            execution_id="wf-a1",
            is_complete=True,
            status="COMPLETED",
            output={"result": "async done"},
        )
        runtime = MagicMock()

        async def _get_status_async(eid):
            return completed

        runtime.get_status_async = AsyncMock(side_effect=_get_status_async)
        runtime._normalize_output.side_effect = lambda o, s, reason=None: o if isinstance(o, dict) else {"result": o}
        runtime._derive_finish_reason.return_value = FinishReason.STOP
        runtime._extract_token_usage.return_value = None

        handle = AgentHandle(execution_id="wf-a1", runtime=runtime)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await handle.join_async()

        assert isinstance(result, AgentResult)
        assert result.execution_id == "wf-a1"
        assert result.status == Status.COMPLETED

    @pytest.mark.asyncio
    async def test_join_async_raises_timeout_error(self):
        """join_async(timeout=2) raises TimeoutError if never complete."""
        running = AgentStatus(
            execution_id="wf-a2", is_complete=False, status="RUNNING", output=None
        )
        runtime = MagicMock()
        runtime.get_status_async = AsyncMock(return_value=running)
        runtime._normalize_output.side_effect = lambda o, s, reason=None: {"result": o}
        runtime._derive_finish_reason.return_value = FinishReason.STOP
        runtime._extract_token_usage.return_value = None

        handle = AgentHandle(execution_id="wf-a2", runtime=runtime)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(TimeoutError) as exc_info:
                await handle.join_async(timeout=2)

        assert "wf-a2" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_join_async_polls_until_complete(self):
        """join_async() keeps polling until is_complete."""
        responses = [
            AgentStatus(execution_id="wf-a3", is_complete=False, status="RUNNING", output=None),
            AgentStatus(execution_id="wf-a3", is_complete=False, status="RUNNING", output=None),
            AgentStatus(execution_id="wf-a3", is_complete=True, status="COMPLETED", output={"result": "yes"}),
        ]
        idx = {"i": 0}

        async def _get(eid):
            val = responses[min(idx["i"], len(responses) - 1)]
            idx["i"] += 1
            return val

        runtime = MagicMock()
        runtime.get_status_async = AsyncMock(side_effect=_get)
        runtime._normalize_output.side_effect = lambda o, s, reason=None: o if isinstance(o, dict) else {"result": o}
        runtime._derive_finish_reason.return_value = FinishReason.STOP
        runtime._extract_token_usage.return_value = None

        handle = AgentHandle(execution_id="wf-a3", runtime=runtime)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await handle.join_async()

        assert result.status == Status.COMPLETED
        assert runtime.get_status_async.call_count == 3
