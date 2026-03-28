# sdk/python/tests/unit/test_passthrough_registration.py
"""Tests for passthrough worker registration path in runtime.py."""
from unittest.mock import MagicMock, patch, call  # noqa: F401


def _make_graph():
    graph = MagicMock()
    type(graph).__name__ = "CompiledStateGraph"
    graph.name = "test_graph"
    return graph


class TestSerializeAgentDispatching:
    def test_langgraph_dispatches_to_serialize_langgraph(self):
        from agentspan.agents.frameworks.serializer import serialize_agent

        graph = _make_graph()

        with patch("agentspan.agents.frameworks.langgraph.serialize_langgraph") as mock_serialize:
            mock_serialize.return_value = ({"name": "test_graph"}, [])
            serialize_agent(graph)
            mock_serialize.assert_called_once_with(graph)

    def test_langchain_dispatches_to_serialize_langchain(self):
        from agentspan.agents.frameworks.serializer import serialize_agent

        executor = MagicMock()
        type(executor).__name__ = "AgentExecutor"

        with patch("agentspan.agents.frameworks.langchain.serialize_langchain") as mock_serialize:
            mock_serialize.return_value = ({"name": "my_exec"}, [])
            serialize_agent(executor)
            mock_serialize.assert_called_once_with(executor)

    def test_claude_agent_sdk_dispatches_to_serialize_claude_agent_sdk(self):
        from agentspan.agents.frameworks.serializer import serialize_agent

        options = MagicMock()
        type(options).__name__ = "ClaudeCodeOptions"

        with patch(
            "agentspan.agents.frameworks.claude_agent_sdk.serialize_claude_agent_sdk"
        ) as mock_serialize:
            mock_serialize.return_value = ({"name": "test_agent"}, [])
            serialize_agent(options)
            mock_serialize.assert_called_once_with(options)


class TestPassthroughTaskDef:
    def test_passthrough_task_def_has_no_timeout(self):
        from agentspan.agents.runtime.runtime import _passthrough_task_def

        td = _passthrough_task_def("my_graph")

        assert td.timeout_seconds == 0
        assert td.response_timeout_seconds == 3600
        assert td.name == "my_graph"


class TestSerializeAgentFuncPlaceholder:
    def test_serialize_langgraph_returns_func_none_placeholder(self):
        """serialize_langgraph returns func=None; _build_passthrough_func fills it later.
        This test documents the design: serialize_agent() is only called for rawConfig,
        and _build_passthrough_func() provides the actual pre-wrapped worker func.
        """
        from agentspan.agents.frameworks.serializer import serialize_agent

        graph = MagicMock()
        type(graph).__name__ = "CompiledStateGraph"
        graph.name = "test_graph"

        with patch("agentspan.agents.frameworks.langgraph.serialize_langgraph") as mock_sl:
            mock_sl.return_value = ({"name": "test_graph"}, [
                MagicMock(name="test_graph", func=None)
            ])
            _, workers = serialize_agent(graph)

        # func=None is expected here — it is a placeholder
        assert workers[0].func is None  # filled by _build_passthrough_func before registration


class TestBuildPassthroughFunc:
    def test_build_passthrough_func_passes_auth_to_langgraph_worker(self):
        """Verifies auth_key/auth_secret (not key_id/key_secret) are passed."""
        from agentspan.agents.runtime.runtime import AgentRuntime
        from agentspan.agents.runtime.config import AgentConfig

        config = AgentConfig(
            server_url="http://testserver:8080/api",
            auth_key="my_key",
            auth_secret="my_secret",
        )

        graph = MagicMock()
        type(graph).__name__ = "CompiledStateGraph"

        with patch("agentspan.agents.frameworks.langgraph.make_langgraph_worker") as mock_worker:
            mock_worker.return_value = MagicMock()
            # Build a minimal runtime just to call _build_passthrough_func
            runtime = AgentRuntime.__new__(AgentRuntime)
            runtime._config = config
            runtime._build_passthrough_func(graph, "langgraph", "test_graph")

        mock_worker.assert_called_once_with(
            graph, "test_graph", "http://testserver:8080/api", "my_key", "my_secret"
        )

    def test_build_passthrough_func_passes_auth_to_claude_agent_sdk_worker(self):
        from agentspan.agents.runtime.runtime import AgentRuntime
        from agentspan.agents.runtime.config import AgentConfig

        config = AgentConfig(
            server_url="http://testserver:8080/api",
            auth_key="my_key",
            auth_secret="my_secret",
        )

        options = MagicMock()
        type(options).__name__ = "ClaudeCodeOptions"

        with patch(
            "agentspan.agents.frameworks.claude_agent_sdk.make_claude_agent_sdk_worker"
        ) as mock_worker:
            mock_worker.return_value = MagicMock()
            runtime = AgentRuntime.__new__(AgentRuntime)
            runtime._config = config
            runtime._build_passthrough_func(options, "claude_agent_sdk", "test_agent")

        mock_worker.assert_called_once_with(
            options, "test_agent", "http://testserver:8080/api", "my_key", "my_secret"
        )
