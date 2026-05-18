# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tests for context passing through runtime methods."""
from unittest.mock import MagicMock, patch

from agentspan.agents import Agent
from agentspan.agents.cli_config import _make_cli_tool
from agentspan.agents.tool import ToolContext


def test_start_via_server_includes_context_in_payload():
    """Verify context dict ends up in the /api/agent/start POST body."""
    from agentspan.agents import AgentRuntime

    agent = Agent(name="test", model="openai/gpt-4o-mini")
    rt = AgentRuntime()
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"executionId": "test-id", "requiredWorkers": []}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp
        rt._start_via_server(agent, "hello", context={"repo": "test/repo"})
        payload = mock_post.call_args.kwargs["json"]
        assert "context" in payload
        assert payload["context"] == {"repo": "test/repo"}


def test_start_via_server_without_context_omits_key():
    """Without context param, payload should not include context key."""
    from agentspan.agents import AgentRuntime

    agent = Agent(name="test", model="openai/gpt-4o-mini")
    rt = AgentRuntime()
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"executionId": "test-id", "requiredWorkers": []}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp
        rt._start_via_server(agent, "hello")
        payload = mock_post.call_args.kwargs["json"]
        assert "context" not in payload


def test_context_key_collision_with_state_updates():
    """Using _state_updates as context_key doesn't corrupt dispatch internals."""
    ctx = ToolContext(execution_id="test", agent_name="test", state={})
    tool_fn = _make_cli_tool(allowed_commands=[])
    with patch("agentspan.agents.cli_config.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="val\n", stderr="")
        tool_fn.__wrapped__(command="echo", context_key="_state_updates", context=ctx)
    assert ctx.state["_state_updates"] == "val"


def test_partial_context_preserved_on_tool_failure():
    """If a CLI tool fails, earlier context writes are preserved but new key is not added."""
    ctx = ToolContext(execution_id="test", agent_name="test", state={"existing": "value"})
    tool_fn = _make_cli_tool(allowed_commands=[])
    with patch("agentspan.agents.cli_config.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="fail")
        result = tool_fn.__wrapped__(command="false", context_key="new_key", context=ctx)
    assert result["status"] == "error"
    assert ctx.state == {"existing": "value"}  # existing preserved, new_key not added


def test_context_none_is_safe():
    """Passing context=None with a context_key should not raise."""
    tool_fn = _make_cli_tool(allowed_commands=[])
    with patch("agentspan.agents.cli_config.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="val\n", stderr="")
        result = tool_fn.__wrapped__(command="echo", context_key="key", context=None)
    assert result["status"] == "success"
