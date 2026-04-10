# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for deterministic stop signal and signal methods."""

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from agentspan.agents.result import AgentHandle, FinishReason


# ── FinishReason.STOPPED ────────────────────────────────────────────────


class TestFinishReasonStopped:
    """STOPPED is a valid FinishReason."""

    def test_stopped_exists(self):
        assert FinishReason.STOPPED == "stopped"

    def test_stopped_string_comparison(self):
        assert FinishReason.STOPPED == "stopped"


# ── AgentHandle.stop() ─────────────────────────────────────────────────


class TestHandleStop:
    """handle.stop() sends a stop signal to the runtime."""

    def test_stop_calls_runtime_stop(self):
        runtime = MagicMock()
        handle = AgentHandle(execution_id="wf-1", runtime=runtime)
        handle.stop()
        runtime.stop.assert_called_once_with("wf-1")

    def test_stop_is_stateless(self):
        """Multiple stop calls all delegate — server handles idempotency."""
        runtime = MagicMock()
        handle = AgentHandle(execution_id="wf-1", runtime=runtime)
        handle.stop()
        handle.stop()
        assert runtime.stop.call_count == 2


class TestHandleStopAsync:
    """handle.stop_async() is the async variant."""

    @pytest.mark.asyncio
    async def test_stop_async_calls_runtime(self):
        runtime = MagicMock()
        runtime.stop_async = AsyncMock()
        handle = AgentHandle(execution_id="wf-1", runtime=runtime)
        await handle.stop_async()
        runtime.stop_async.assert_called_once_with("wf-1")


# ── AgentRuntime.stop() ────────────────────────────────────────────────


class TestRuntimeStop:
    """AgentRuntime.stop() calls the server stop endpoint and sends WMQ unblock."""

    @patch("agentspan.agents.runtime.runtime.req_lib", create=True)
    def test_stop_calls_server_endpoint(self, mock_requests):
        from agentspan.agents.runtime.runtime import AgentRuntime

        rt = AgentRuntime.__new__(AgentRuntime)
        rt._workflow_client = MagicMock()
        rt._agent_api_url = MagicMock(return_value="http://localhost/api/agent/wf-1/stop")
        rt._agent_api_headers = MagicMock(return_value={})

        # Mock requests.post
        import requests as req_lib
        with patch.object(req_lib, "post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            mock_post.return_value.raise_for_status = MagicMock()
            rt.stop("wf-1")
            mock_post.assert_called_once()

    def test_stop_sends_wmq_unblock(self):
        from agentspan.agents.runtime.runtime import AgentRuntime

        rt = AgentRuntime.__new__(AgentRuntime)
        rt._workflow_client = MagicMock()
        rt._agent_api_url = MagicMock(return_value="http://localhost/api/agent/wf-1/stop")
        rt._agent_api_headers = MagicMock(return_value={})

        import requests as req_lib
        with patch.object(req_lib, "post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            mock_post.return_value.raise_for_status = MagicMock()
            rt.stop("wf-1")
            rt._workflow_client.send_message.assert_called_once_with(
                "wf-1", {"_signal": "stop"}
            )

    def test_stop_wmq_failure_is_swallowed(self):
        """If WMQ send fails, stop still succeeds."""
        from agentspan.agents.runtime.runtime import AgentRuntime

        rt = AgentRuntime.__new__(AgentRuntime)
        rt._workflow_client = MagicMock()
        rt._workflow_client.send_message.side_effect = Exception("no WMQ")
        rt._agent_api_url = MagicMock(return_value="http://localhost/api/agent/wf-1/stop")
        rt._agent_api_headers = MagicMock(return_value={})

        import requests as req_lib
        with patch.object(req_lib, "post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            mock_post.return_value.raise_for_status = MagicMock()
            rt.stop("wf-1")  # should not raise


# ── AgentRuntime.signal() ──────────────────────────────────────────────


class TestRuntimeSignal:
    """AgentRuntime.signal() calls the server signal endpoint."""

    def test_signal_calls_server_endpoint(self):
        from agentspan.agents.runtime.runtime import AgentRuntime

        rt = AgentRuntime.__new__(AgentRuntime)
        rt._agent_api_url = MagicMock(return_value="http://localhost/api/agent/wf-1/signal")
        rt._agent_api_headers = MagicMock(return_value={})

        import requests as req_lib
        with patch.object(req_lib, "post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            mock_post.return_value.raise_for_status = MagicMock()
            rt.signal("wf-1", "budget cut, wrap up")
            mock_post.assert_called_once_with(
                "http://localhost/api/agent/wf-1/signal",
                json={"message": "budget cut, wrap up"},
                headers={},
                timeout=30,
            )

    def test_signal_clear(self):
        from agentspan.agents.runtime.runtime import AgentRuntime

        rt = AgentRuntime.__new__(AgentRuntime)
        rt._agent_api_url = MagicMock(return_value="http://localhost/api/agent/wf-1/signal")
        rt._agent_api_headers = MagicMock(return_value={})

        import requests as req_lib
        with patch.object(req_lib, "post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            mock_post.return_value.raise_for_status = MagicMock()
            rt.signal("wf-1", "")
            mock_post.assert_called_once()


# ── wait_for_message_tool blocking parameter ────────────────────────────


class TestWaitForMessageToolBlocking:
    """wait_for_message_tool supports a blocking parameter."""

    def test_default_is_blocking(self):
        from agentspan.agents.tool import wait_for_message_tool

        td = wait_for_message_tool(name="wait", description="Wait")
        # Default blocking=True means no explicit "blocking" key in config
        assert "blocking" not in td.config

    def test_non_blocking_sets_config(self):
        from agentspan.agents.tool import wait_for_message_tool

        td = wait_for_message_tool(name="poll", description="Poll", blocking=False)
        assert td.config["blocking"] is False

    def test_batch_size_preserved(self):
        from agentspan.agents.tool import wait_for_message_tool

        td = wait_for_message_tool(name="poll", description="Poll", batch_size=5, blocking=False)
        assert td.config["batchSize"] == 5
        assert td.config["blocking"] is False
