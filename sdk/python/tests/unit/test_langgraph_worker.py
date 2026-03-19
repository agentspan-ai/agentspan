# sdk/python/tests/unit/test_langgraph_worker.py
"""Unit tests for the LangGraph passthrough worker."""
import pytest
from unittest.mock import MagicMock, patch, call


def _make_fake_graph(stream_chunks=None, input_schema=None):
    """Create a mock CompiledStateGraph."""
    graph = MagicMock()
    type(graph).__name__ = "CompiledStateGraph"
    graph.name = "test_graph"

    if input_schema is None:
        input_schema = {
            "type": "object",
            "properties": {
                "messages": {"type": "array"}
            }
        }
    graph.get_input_jsonschema.return_value = input_schema

    if stream_chunks is None:
        # Default: one updates chunk (node result), one values chunk (final state)
        stream_chunks = [
            ("updates", {"agent": {"messages": []}}),
            ("values", {"messages": [
                {"type": "ai", "content": "Hello!", "tool_calls": []}
            ]}),
        ]
    graph.stream.return_value = iter(stream_chunks)
    return graph


def _make_task(prompt="Hello", session_id="", workflow_id="wf-123"):
    from conductor.client.http.models.task import Task
    task = MagicMock(spec=Task)
    task.input_data = {"prompt": prompt, "session_id": session_id}
    task.workflow_instance_id = workflow_id
    return task


class TestSerializeLanggraph:
    def test_returns_single_worker_info(self):
        from agentspan.agents.frameworks.langgraph import serialize_langgraph
        graph = _make_fake_graph()

        raw_config, workers = serialize_langgraph(graph)

        assert len(workers) == 1
        assert workers[0].name == "test_graph"

    def test_raw_config_has_name_and_worker_name(self):
        from agentspan.agents.frameworks.langgraph import serialize_langgraph
        graph = _make_fake_graph()

        raw_config, _ = serialize_langgraph(graph)

        assert raw_config["name"] == "test_graph"
        assert raw_config["_worker_name"] == "test_graph"

    def test_graph_with_no_name_uses_default(self):
        from agentspan.agents.frameworks.langgraph import serialize_langgraph
        graph = _make_fake_graph()
        graph.name = None  # graph has no .name attribute

        raw_config, workers = serialize_langgraph(graph)

        assert raw_config["name"] == "langgraph_agent"


class TestMakeLanggraphWorker:
    def test_worker_extracts_output_from_messages_state(self):
        from agentspan.agents.frameworks.langgraph import make_langgraph_worker

        # Graph with messages-based state — last AIMessage content is the output
        chunks = [
            ("updates", {"agent": {"messages": []}}),
            ("values", {"messages": [
                {"type": "human", "content": "Hello"},
                {"type": "ai", "content": "World!", "tool_calls": []},
            ]}),
        ]
        graph = _make_fake_graph(stream_chunks=chunks)
        task = _make_task(prompt="Hello")

        with patch("agentspan.agents.frameworks.langgraph._push_event_nonblocking"):
            worker_fn = make_langgraph_worker(
                graph, "test_graph", "http://localhost:8080", "key", "secret"
            )
            result = worker_fn(task)

        assert result.status == "COMPLETED"
        assert result.output_data["result"] == "World!"

    def test_worker_uses_session_id_as_thread_id(self):
        from agentspan.agents.frameworks.langgraph import make_langgraph_worker

        graph = _make_fake_graph()
        task = _make_task(session_id="sess-42")

        with patch("agentspan.agents.frameworks.langgraph._push_event_nonblocking"):
            worker_fn = make_langgraph_worker(
                graph, "test_graph", "http://localhost:8080", "key", "secret"
            )
            worker_fn(task)

        # graph.stream must have been called with configurable.thread_id = "sess-42"
        config_arg = graph.stream.call_args.args[1]
        assert config_arg["configurable"]["thread_id"] == "sess-42"

    def test_worker_returns_failed_on_exception(self):
        from agentspan.agents.frameworks.langgraph import make_langgraph_worker

        graph = _make_fake_graph()
        graph.stream.side_effect = RuntimeError("checkpointer not set")
        task = _make_task()

        with patch("agentspan.agents.frameworks.langgraph._push_event_nonblocking"):
            worker_fn = make_langgraph_worker(
                graph, "test_graph", "http://localhost:8080", "key", "secret"
            )
            result = worker_fn(task)

        assert result.status == "FAILED"
        assert "checkpointer not set" in result.reason_for_incompletion

    def test_worker_pushes_thinking_event_for_node_update(self):
        from agentspan.agents.frameworks.langgraph import make_langgraph_worker

        chunks = [
            ("updates", {"agent": {"messages": []}}),
            ("values", {"messages": [
                {"type": "ai", "content": "Done", "tool_calls": []}
            ]}),
        ]
        graph = _make_fake_graph(stream_chunks=chunks)
        task = _make_task()

        with patch("agentspan.agents.frameworks.langgraph._push_event_nonblocking") as mock_push:
            worker_fn = make_langgraph_worker(
                graph, "test_graph", "http://localhost:8080", "key", "secret"
            )
            worker_fn(task)

        # Should have pushed at least one thinking event for the "agent" node
        push_calls = mock_push.call_args_list
        event_types = [c[0][1]["type"] for c in push_calls]
        assert "thinking" in event_types

    def test_worker_detects_messages_input_format(self):
        from agentspan.agents.frameworks.langgraph import make_langgraph_worker
        from langchain_core.messages import HumanMessage  # local import: langchain_core installed as dev dep

        graph = _make_fake_graph(input_schema={
            "type": "object",
            "properties": {"messages": {"type": "array"}},
            "required": ["messages"]
        })
        task = _make_task(prompt="test input")

        with patch("agentspan.agents.frameworks.langgraph._push_event_nonblocking"):
            worker_fn = make_langgraph_worker(
                graph, "test_graph", "http://localhost:8080", "key", "secret"
            )
            worker_fn(task)

        # graph.stream must have been called with {"messages": [HumanMessage(...)]}
        input_arg = graph.stream.call_args[0][0]
        assert "messages" in input_arg
        assert isinstance(input_arg["messages"][0], HumanMessage)

    def test_worker_passes_correct_stream_mode(self):
        from agentspan.agents.frameworks.langgraph import make_langgraph_worker

        graph = _make_fake_graph()
        task = _make_task()

        with patch("agentspan.agents.frameworks.langgraph._push_event_nonblocking"):
            worker_fn = make_langgraph_worker(
                graph, "test_graph", "http://localhost:8080", "key", "secret"
            )
            worker_fn(task)

        stream_kwargs = graph.stream.call_args[1]
        assert stream_kwargs["stream_mode"] == ["updates", "values"]
