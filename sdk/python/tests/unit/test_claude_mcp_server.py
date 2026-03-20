# tests/unit/test_claude_mcp_server.py
"""Unit tests for AgentspanMcpServer — all dependencies mocked."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_conductor_client(result="tool-result"):
    client = MagicMock()
    client.start_tool_workflow = AsyncMock(return_value="wf-abc")
    client.start_workflow = AsyncMock(return_value="wf-sub")
    client.poll_until_done = AsyncMock(return_value=result)
    # Pre-register workflow (sync)
    client.register_tool_workflow = MagicMock()
    return client


def _make_event_client():
    client = MagicMock()
    client.push = AsyncMock()
    return client


def _make_echo_tool():
    """A minimal @tool-like object with _tool_def."""
    from unittest.mock import MagicMock

    def echo_fn(message: str) -> str:
        """Echo the message."""
        return f"echo:{message}"

    td = MagicMock()
    td.name = "echo_tool"
    td.description = "Echo the message."
    td.input_schema = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    }
    echo_fn._tool_def = td
    return echo_fn


# ── Schema generation ─────────────────────────────────────────────────────────

class TestMcpServerSchemaGeneration:
    def test_tool_appears_in_mcp_server(self):
        """@tool function is registered as an MCP tool with correct name."""
        from agentspan.agents.frameworks.claude_mcp_server import AgentspanMcpServer

        echo_tool = _make_echo_tool()
        conductor = _make_conductor_client()
        events = _make_event_client()

        server = AgentspanMcpServer(
            tools=[echo_tool],
            subagent_workflow_name=None,
            conductor_client=conductor,
            event_client=events,
            parent_workflow_id="wf-parent",
        )
        config = server.build()

        assert config["type"] == "sdk"
        assert config["name"] == "agentspan"
        # FastMCP instance has the tool registered
        mcp_instance = config["instance"]
        tool_names = [t.name for t in mcp_instance._tool_manager.list_tools()]
        assert "echo_tool" in tool_names

    def test_tool_description_preserved(self):
        """MCP tool description comes from @tool definition."""
        from agentspan.agents.frameworks.claude_mcp_server import AgentspanMcpServer

        echo_tool = _make_echo_tool()
        server = AgentspanMcpServer(
            tools=[echo_tool],
            subagent_workflow_name=None,
            conductor_client=_make_conductor_client(),
            event_client=_make_event_client(),
            parent_workflow_id="wf-parent",
        )
        config = server.build()
        tools = config["instance"]._tool_manager.list_tools()
        echo = next(t for t in tools if t.name == "echo_tool")
        assert "Echo" in echo.description

    def test_spawn_subagent_registered_when_workflow_name_set(self):
        """spawn_subagent tool registered when subagent_workflow_name is given."""
        from agentspan.agents.frameworks.claude_mcp_server import AgentspanMcpServer

        server = AgentspanMcpServer(
            tools=[],
            subagent_workflow_name="_fw_claude_test",
            conductor_client=_make_conductor_client(),
            event_client=_make_event_client(),
            parent_workflow_id="wf-parent",
        )
        config = server.build()
        tool_names = [t.name for t in config["instance"]._tool_manager.list_tools()]
        assert "spawn_subagent" in tool_names

    def test_spawn_subagent_not_registered_when_no_workflow_name(self):
        """spawn_subagent NOT added when subagent_workflow_name is None."""
        from agentspan.agents.frameworks.claude_mcp_server import AgentspanMcpServer

        server = AgentspanMcpServer(
            tools=[],
            subagent_workflow_name=None,
            conductor_client=_make_conductor_client(),
            event_client=_make_event_client(),
            parent_workflow_id="wf-parent",
        )
        config = server.build()
        tool_names = [t.name for t in config["instance"]._tool_manager.list_tools()]
        assert "spawn_subagent" not in tool_names

    def test_empty_tools_starts_with_zero_ecosystem_tools(self):
        """Server with no tools is valid (zero ecosystem tools)."""
        from agentspan.agents.frameworks.claude_mcp_server import AgentspanMcpServer

        server = AgentspanMcpServer(
            tools=[],
            subagent_workflow_name=None,
            conductor_client=_make_conductor_client(),
            event_client=_make_event_client(),
            parent_workflow_id="wf-parent",
        )
        config = server.build()
        assert config["type"] == "sdk"
        assert len(config["instance"]._tool_manager.list_tools()) == 0


# ── Conductor dispatch ────────────────────────────────────────────────────────

class TestToolDispatch:
    def _build_server(self, conductor=None, events=None):
        from agentspan.agents.frameworks.claude_mcp_server import AgentspanMcpServer

        return AgentspanMcpServer(
            tools=[_make_echo_tool()],
            subagent_workflow_name=None,
            conductor_client=conductor or _make_conductor_client(),
            event_client=events or _make_event_client(),
            parent_workflow_id="wf-parent",
        )

    def test_tool_dispatch_calls_start_tool_workflow(self):
        """Calling MCP tool starts a Conductor tool workflow."""
        conductor = _make_conductor_client(result="echo:hello")
        server = self._build_server(conductor=conductor)
        server.build()

        result = asyncio.run(server._dispatch_tool("echo_tool", {"message": "hello"}))

        conductor.start_tool_workflow.assert_called_once_with("echo_tool", {"message": "hello"})

    def test_tool_dispatch_polls_until_done(self):
        """Tool dispatch polls Conductor until workflow completes."""
        conductor = _make_conductor_client(result="echo:hello")
        server = self._build_server(conductor=conductor)
        server.build()

        result = asyncio.run(server._dispatch_tool("echo_tool", {"message": "hello"}))

        conductor.poll_until_done.assert_called_once_with("wf-abc")
        assert result == "echo:hello"

    def test_tool_dispatch_returns_conductor_result(self):
        """Tool dispatch returns the Conductor task output."""
        conductor = _make_conductor_client(result="echo:world")
        server = self._build_server(conductor=conductor)
        server.build()

        result = asyncio.run(server._dispatch_tool("echo_tool", {"message": "world"}))
        assert result == "echo:world"

    def test_tool_dispatch_raises_on_conductor_failure(self):
        """Tool dispatch raises RuntimeError when Conductor workflow fails."""
        conductor = _make_conductor_client()
        conductor.poll_until_done = AsyncMock(side_effect=RuntimeError("FAILED"))
        server = self._build_server(conductor=conductor)
        server.build()

        with pytest.raises(RuntimeError, match="FAILED"):
            asyncio.run(server._dispatch_tool("echo_tool", {"message": "x"}))

    def test_tool_without_tool_def_is_skipped(self):
        """Tool function missing _tool_def attribute is skipped gracefully."""
        from agentspan.agents.frameworks.claude_mcp_server import AgentspanMcpServer

        def bad_tool(x: str) -> str:
            return x
        # No _tool_def attribute

        server = AgentspanMcpServer(
            tools=[bad_tool],
            subagent_workflow_name=None,
            conductor_client=_make_conductor_client(),
            event_client=_make_event_client(),
            parent_workflow_id="wf-parent",
        )
        config = server.build()
        # Should not raise, but tool is not registered
        tool_names = [t.name for t in config["instance"]._tool_manager.list_tools()]
        assert "bad_tool" not in tool_names


# ── Subagent dispatch ─────────────────────────────────────────────────────────

class TestSubagentDispatch:
    def test_spawn_subagent_starts_conductor_workflow(self):
        """spawn_subagent starts a Conductor workflow with the prompt."""
        conductor = _make_conductor_client(result="subagent-done")
        from agentspan.agents.frameworks.claude_mcp_server import AgentspanMcpServer

        server = AgentspanMcpServer(
            tools=[],
            subagent_workflow_name="_fw_claude_test",
            conductor_client=conductor,
            event_client=_make_event_client(),
            parent_workflow_id="wf-parent",
        )
        server.build()

        result = asyncio.run(server._dispatch_subagent("Say hello"))

        conductor.start_workflow.assert_called_once_with(
            "_fw_claude_test",
            {"prompt": "Say hello", "_is_subagent": True},
        )

    def test_spawn_subagent_polls_and_returns_result(self):
        """spawn_subagent polls Conductor and returns result."""
        conductor = _make_conductor_client(result="subagent-done")
        from agentspan.agents.frameworks.claude_mcp_server import AgentspanMcpServer

        server = AgentspanMcpServer(
            tools=[],
            subagent_workflow_name="_fw_claude_test",
            conductor_client=conductor,
            event_client=_make_event_client(),
            parent_workflow_id="wf-parent",
        )
        server.build()

        result = asyncio.run(server._dispatch_subagent("Say hello"))
        assert result == "subagent-done"

    def test_spawn_subagent_raises_when_no_workflow_name(self):
        """_dispatch_subagent raises if subagent_workflow_name is None."""
        from agentspan.agents.frameworks.claude_mcp_server import AgentspanMcpServer

        server = AgentspanMcpServer(
            tools=[],
            subagent_workflow_name=None,
            conductor_client=_make_conductor_client(),
            event_client=_make_event_client(),
            parent_workflow_id="wf-parent",
        )
        with pytest.raises(RuntimeError, match="conductor_subagents"):
            asyncio.run(server._dispatch_subagent("prompt"))

    def test_spawn_subagent_raises_on_conductor_failure(self):
        """_dispatch_subagent raises RuntimeError when Conductor workflow fails."""
        conductor = _make_conductor_client()
        conductor.poll_until_done = AsyncMock(side_effect=RuntimeError("FAILED"))
        from agentspan.agents.frameworks.claude_mcp_server import AgentspanMcpServer

        server = AgentspanMcpServer(
            tools=[],
            subagent_workflow_name="_fw_claude_test",
            conductor_client=conductor,
            event_client=_make_event_client(),
            parent_workflow_id="wf-parent",
        )
        server.build()

        with pytest.raises(RuntimeError, match="FAILED"):
            asyncio.run(server._dispatch_subagent("test prompt"))


# ── Event emission ────────────────────────────────────────────────────────────

class TestEventEmission:
    def test_tool_dispatch_emits_tool_call_event(self):
        """tool_call event emitted before Conductor dispatch."""
        events = _make_event_client()
        conductor = _make_conductor_client(result="r")
        from agentspan.agents.frameworks.claude_mcp_server import AgentspanMcpServer

        server = AgentspanMcpServer(
            tools=[_make_echo_tool()],
            subagent_workflow_name=None,
            conductor_client=conductor,
            event_client=events,
            parent_workflow_id="wf-parent",
        )
        server.build()
        asyncio.run(server._dispatch_tool("echo_tool", {"message": "hi"}))

        calls = [c.args for c in events.push.call_args_list]
        assert any(
            args[0] == "wf-parent" and args[1] == "tool_call"
            for args in calls
        )

    def test_tool_dispatch_emits_tool_result_event(self):
        """tool_result event emitted after Conductor dispatch completes."""
        events = _make_event_client()
        from agentspan.agents.frameworks.claude_mcp_server import AgentspanMcpServer

        server = AgentspanMcpServer(
            tools=[_make_echo_tool()],
            subagent_workflow_name=None,
            conductor_client=_make_conductor_client(result="r"),
            event_client=events,
            parent_workflow_id="wf-parent",
        )
        server.build()
        asyncio.run(server._dispatch_tool("echo_tool", {"message": "hi"}))

        calls = [c.args for c in events.push.call_args_list]
        assert any(
            args[0] == "wf-parent" and args[1] == "tool_result"
            for args in calls
        )

    def test_subagent_emits_subagent_start_event(self):
        """subagent_start event emitted with sub-workflow ID before polling."""
        events = _make_event_client()
        conductor = _make_conductor_client(result="done")
        from agentspan.agents.frameworks.claude_mcp_server import AgentspanMcpServer

        server = AgentspanMcpServer(
            tools=[],
            subagent_workflow_name="_fw_claude_test",
            conductor_client=conductor,
            event_client=events,
            parent_workflow_id="wf-parent",
        )
        server.build()
        asyncio.run(server._dispatch_subagent("hello"))

        calls = [c.args for c in events.push.call_args_list]
        assert any(args[1] == "subagent_start" for args in calls)

    def test_subagent_emits_subagent_stop_event(self):
        """subagent_stop event emitted after sub-workflow completes."""
        events = _make_event_client()
        conductor = _make_conductor_client(result="done")
        from agentspan.agents.frameworks.claude_mcp_server import AgentspanMcpServer

        server = AgentspanMcpServer(
            tools=[],
            subagent_workflow_name="_fw_claude_test",
            conductor_client=conductor,
            event_client=events,
            parent_workflow_id="wf-parent",
        )
        server.build()
        asyncio.run(server._dispatch_subagent("hello"))

        calls = [c.args for c in events.push.call_args_list]
        assert any(args[1] == "subagent_stop" for args in calls)

    def test_event_failure_is_non_fatal(self):
        """Event push failure does not abort tool dispatch."""
        events = _make_event_client()
        events.push = AsyncMock(side_effect=Exception("network error"))
        conductor = _make_conductor_client(result="r")
        from agentspan.agents.frameworks.claude_mcp_server import AgentspanMcpServer

        server = AgentspanMcpServer(
            tools=[_make_echo_tool()],
            subagent_workflow_name=None,
            conductor_client=conductor,
            event_client=events,
            parent_workflow_id="wf-parent",
        )
        server.build()
        # Should not raise even though events fail
        result = asyncio.run(server._dispatch_tool("echo_tool", {"message": "x"}))
        assert result == "r"
