# sdk/python/tests/unit/test_passthrough_registration.py
"""Tests for passthrough worker registration path in runtime.py."""
from unittest.mock import MagicMock, patch, call


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


class TestPassthroughTaskDef:
    def test_passthrough_task_def_has_600s_timeout(self):
        from agentspan.agents.runtime.runtime import _passthrough_task_def

        td = _passthrough_task_def("my_graph")

        assert td.timeout_seconds == 600
        assert td.response_timeout_seconds == 600
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
