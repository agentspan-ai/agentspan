# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.
"""Tests for AgentspanTransport (claude_transport.py)."""

import asyncio
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Ensure `anthropic` is importable before loading claude_transport.
# We install a stub module in sys.modules so the try/except ImportError in
# claude_transport.py resolves to our mock rather than raising.
# ---------------------------------------------------------------------------
_mock_anthropic = MagicMock()
_mock_async_anthropic_instance = MagicMock()
_mock_async_anthropic_instance.messages = MagicMock()
_mock_async_anthropic_instance.messages.create = AsyncMock()
_mock_anthropic.AsyncAnthropic = MagicMock(return_value=_mock_async_anthropic_instance)

# Inject before any import of claude_transport
if "anthropic" not in sys.modules:
    sys.modules["anthropic"] = _mock_anthropic

# Now import the module — the try/except will succeed using our mock
from agentspan.agents.frameworks.claude_transport import (  # noqa: E402
    _DRAIN_SENTINEL,
    AgentspanTransport,
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_transport(
    agent_config=None,
    conductor_client=None,
    event_client=None,
    workflow_id="wf-1",
    cwd="/tmp",
):
    """Create an AgentspanTransport with a fresh mock Anthropic client."""
    if agent_config is None:
        agent_config = {"allowed_tools": ["Bash", "Read"], "model": "claude-opus-4-6"}
    if conductor_client is None:
        conductor_client = MagicMock()
    if event_client is None:
        event_client = MagicMock()

    # Each transport gets its own mock client so tests can configure independently
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock()

    with patch(
        "agentspan.agents.frameworks.claude_transport.anthropic.AsyncAnthropic",
        return_value=mock_client,
    ):
        transport = AgentspanTransport(
            agent_config=agent_config,
            conductor_client=conductor_client,
            event_client=event_client,
            workflow_id=workflow_id,
            cwd=cwd,
        )
    # Replace the client so tests can configure it directly
    transport._client = mock_client
    return transport


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAgentspanTransportInit:
    def test_init_stores_config(self):
        conductor = MagicMock()
        events = MagicMock()
        config = {"allowed_tools": ["Bash"], "model": "claude-sonnet-4-6"}

        transport = _make_transport(
            agent_config=config,
            conductor_client=conductor,
            event_client=events,
            workflow_id="wf-1",
            cwd="/tmp",
        )

        assert transport._workflow_id == "wf-1"
        assert transport._cwd == "/tmp"
        assert transport._agent_config is config
        assert transport._conductor is conductor
        assert transport._events is events

    def test_is_ready_returns_true(self):
        transport = _make_transport()
        assert transport.is_ready() is True

    def test_get_tool_schemas_filters_by_allowed(self):
        transport = _make_transport(agent_config={"allowed_tools": ["Read", "Bash"]})
        schemas = transport._get_tool_schemas()
        assert len(schemas) == 2
        names = {s["name"] for s in schemas}
        assert names == {"Read", "Bash"}

    def test_get_tool_schemas_empty(self):
        transport = _make_transport(agent_config={"allowed_tools": []})
        schemas = transport._get_tool_schemas()
        assert schemas == []


class TestAgentspanTransportWrite:
    def test_write_user_message_triggers_run_turn(self):
        transport = _make_transport()
        message = {"role": "user", "content": "hello"}
        data = json.dumps({"type": "user", "message": message})

        with patch.object(transport, "_run_turn", new_callable=AsyncMock) as mock_run:
            asyncio.run(transport.write(data))
            mock_run.assert_called_once()

        assert transport._conversation == [message]

    def test_write_non_user_message_ignored(self):
        transport = _make_transport()
        data = json.dumps({"type": "system", "message": {"content": "init"}})

        with patch.object(transport, "_run_turn", new_callable=AsyncMock) as mock_run:
            asyncio.run(transport.write(data))
            mock_run.assert_not_called()

        assert transport._conversation == []


class TestAgentspanTransportRunTurn:
    def _make_simple_response(self, text="Hello!"):
        """Create a mock response with a single TextBlock and stop_reason=end_turn."""
        mock_block = MagicMock()
        mock_block.type = "text"
        mock_block.text = text
        mock_block.model_dump.return_value = {"type": "text", "text": text}

        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [mock_block]
        return mock_response

    def _drain_non_sentinel(self, transport):
        """Drain queue, returning all items except the sentinel."""
        items = []
        while not transport._queue.empty():
            item = transport._queue.get_nowait()
            if item is not _DRAIN_SENTINEL:
                items.append(item)
        return items

    def test_run_turn_simple_response(self):
        transport = _make_transport(
            agent_config={
                "allowed_tools": ["Bash"],
                "model": "claude-opus-4-6",
            }
        )
        mock_response = self._make_simple_response("Hello!")
        transport._client.messages.create = AsyncMock(return_value=mock_response)
        transport._conversation = [{"role": "user", "content": "Hi"}]

        asyncio.run(transport._run_turn())
        items = self._drain_non_sentinel(transport)

        assert len(items) == 2
        assistant_msg = items[0]
        result_msg = items[1]

        assert assistant_msg["type"] == "assistant"
        assert assistant_msg["message"]["role"] == "assistant"
        assert assistant_msg["message"]["content"] == [{"type": "text", "text": "Hello!"}]

        assert result_msg["type"] == "result"
        assert result_msg["result"] == "Hello!"
        assert result_msg["is_error"] is False

    def test_run_turn_tool_use_then_end(self):
        conductor = MagicMock()
        conductor.run_task = AsyncMock(return_value={"output": "file content"})
        events = MagicMock()
        events.push = AsyncMock()

        transport = _make_transport(
            agent_config={"allowed_tools": ["Read"], "model": "claude-opus-4-6"},
            conductor_client=conductor,
            event_client=events,
            cwd="/tmp",
        )
        transport._conversation = [{"role": "user", "content": "read a file"}]

        # First response: tool_use
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "Read"
        tool_block.id = "tool-123"
        tool_block.input = {"file_path": "/tmp/foo.txt"}
        tool_block.model_dump.return_value = {
            "type": "tool_use",
            "name": "Read",
            "id": "tool-123",
            "input": {"file_path": "/tmp/foo.txt"},
        }

        first_response = MagicMock()
        first_response.stop_reason = "tool_use"
        first_response.content = [tool_block]

        # Second response: end_turn
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Done"
        text_block.model_dump.return_value = {"type": "text", "text": "Done"}

        second_response = MagicMock()
        second_response.stop_reason = "end_turn"
        second_response.content = [text_block]

        transport._client.messages.create = AsyncMock(side_effect=[first_response, second_response])

        asyncio.run(transport._run_turn())
        items = self._drain_non_sentinel(transport)

        # Verify conductor was called correctly
        conductor.run_task.assert_called_once_with(
            "claude_builtin_read",
            {"file_path": "/tmp/foo.txt", "cwd": "/tmp"},
        )

        # Verify events were pushed
        push_calls = events.push.call_args_list
        event_types = [call.args[1] for call in push_calls]
        assert "tool_call" in event_types
        assert "tool_result" in event_types

        # Find result message
        result_msg = next(i for i in items if i.get("type") == "result")
        assert result_msg["result"] == "Done"

    def test_run_turn_system_prompt_included(self):
        transport = _make_transport(
            agent_config={
                "allowed_tools": [],
                "model": "claude-opus-4-6",
                "system_prompt": "You are a helpful assistant.",
            }
        )
        mock_response = self._make_simple_response()
        transport._client.messages.create = AsyncMock(return_value=mock_response)
        transport._conversation = [{"role": "user", "content": "hi"}]

        asyncio.run(transport._run_turn())

        call_kwargs = transport._client.messages.create.call_args[1]
        assert call_kwargs.get("system") == "You are a helpful assistant."

    def test_run_turn_no_system_prompt_when_none(self):
        transport = _make_transport(
            agent_config={
                "allowed_tools": [],
                "model": "claude-opus-4-6",
                # No system_prompt key
            }
        )
        mock_response = self._make_simple_response()
        transport._client.messages.create = AsyncMock(return_value=mock_response)
        transport._conversation = [{"role": "user", "content": "hi"}]

        asyncio.run(transport._run_turn())

        call_kwargs = transport._client.messages.create.call_args[1]
        assert "system" not in call_kwargs


class TestAgentspanTransportExecuteTool:
    def test_execute_tool_agent_calls_run_subagent(self):
        transport = _make_transport()

        with patch.object(transport, "_run_subagent", new_callable=AsyncMock) as mock_sub:
            mock_sub.return_value = "subresult"
            result = asyncio.run(transport._execute_tool("Agent", {"prompt": "do X"}))

        mock_sub.assert_called_once_with({"prompt": "do X"})
        assert result == "subresult"

    def test_execute_tool_non_agent_calls_conductor(self):
        conductor = MagicMock()
        conductor.run_task = AsyncMock(return_value={"output": "out"})
        transport = _make_transport(conductor_client=conductor, cwd="/tmp")

        result = asyncio.run(transport._execute_tool("Bash", {"command": "ls"}))

        conductor.run_task.assert_called_once_with(
            "claude_builtin_bash",
            {"command": "ls", "cwd": "/tmp"},
        )
        assert result == "out"


class TestRunSubagentWorkflowName:
    def test_uses_worker_name_from_config(self):
        """_run_subagent uses _worker_name from agent_config, not hardcoded value."""
        conductor = MagicMock()
        conductor.start_workflow = AsyncMock(return_value="sub-wf-1")
        conductor.poll_until_done = AsyncMock(return_value="result")
        events = MagicMock()
        events.push = AsyncMock()

        transport = _make_transport(
            agent_config={
                "_worker_name": "my_custom_workflow",
                "allowed_tools": [],
                "model": "claude-opus-4-6",
            },
            conductor_client=conductor,
            event_client=events,
        )

        asyncio.run(transport._run_subagent({"prompt": "do it"}))

        conductor.start_workflow.assert_called_once_with(
            "my_custom_workflow",
            {"prompt": "do it", "cwd": "/tmp"},
        )

    def test_falls_back_to_default_when_no_worker_name(self):
        """_run_subagent falls back to 'claude_agent_workflow' if _worker_name absent."""
        conductor = MagicMock()
        conductor.start_workflow = AsyncMock(return_value="sub-wf-2")
        conductor.poll_until_done = AsyncMock(return_value="result")
        events = MagicMock()
        events.push = AsyncMock()

        transport = _make_transport(
            agent_config={"allowed_tools": [], "model": "claude-opus-4-6"},
            conductor_client=conductor,
            event_client=events,
        )

        asyncio.run(transport._run_subagent({"prompt": "do it"}))

        conductor.start_workflow.assert_called_once_with(
            "claude_agent_workflow",
            {"prompt": "do it", "cwd": "/tmp"},
        )


class TestAgentspanTransportDrainQueue:
    def test_drain_queue_stops_at_sentinel(self):
        transport = _make_transport()
        transport._queue.put_nowait({"type": "assistant"})
        transport._queue.put_nowait({"type": "result"})
        transport._queue.put_nowait(_DRAIN_SENTINEL)
        transport._queue.put_nowait({"type": "extra"})  # should not be yielded

        async def collect():
            items = []
            async for item in transport._drain_queue():
                items.append(item)
            return items

        items = asyncio.run(collect())
        assert len(items) == 2
        assert items[0] == {"type": "assistant"}
        assert items[1] == {"type": "result"}
