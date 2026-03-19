# sdk/python/tests/unit/test_langgraph_stategraph_example.py
"""
Example 2: LangGraph custom StateGraph with non-messages state.
Verifies auto-detection of non-messages input/output schemas.
"""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def custom_graph():
    """Build a simple StateGraph with a custom state schema (no messages)."""
    pytest.importorskip("langgraph")
    from typing import TypedDict
    from langgraph.graph import StateGraph, END

    class State(TypedDict):
        query: str
        answer: str

    def process(state: State) -> State:
        return {"answer": f"Answer to: {state['query']}"}

    builder = StateGraph(State)
    builder.add_node("process", process)
    builder.set_entry_point("process")
    builder.add_edge("process", END)
    return builder.compile()


class TestCustomStateGraph:
    def test_detect_framework(self, custom_graph):
        from agentspan.agents.frameworks.serializer import detect_framework
        assert detect_framework(custom_graph) == "langgraph"

    def test_worker_extracts_non_messages_output_as_json(self, custom_graph):
        """When state has no messages key, output is JSON of the state dict."""
        from agentspan.agents.frameworks.langgraph import make_langgraph_worker
        import json

        stream_chunks = [
            ("updates", {"process": {"answer": "Answer to: hello"}}),
            ("values", {"query": "hello", "answer": "Answer to: hello"}),
        ]

        task = MagicMock()
        task.task_id = "t-custom"
        task.workflow_instance_id = "wf-custom-1"
        task.input_data = {"prompt": "hello", "session_id": ""}

        with patch.object(custom_graph, "stream", return_value=iter(stream_chunks)):
            with patch("agentspan.agents.frameworks.langgraph._push_event_nonblocking"):
                worker_fn = make_langgraph_worker(
                    custom_graph, "custom_graph", "http://localhost:8080", "k", "s"
                )
                result = worker_fn(task)

        assert result.status == "COMPLETED"
        # Output should be JSON of the state since there are no messages
        output = json.loads(result.output_data["result"])
        assert output["answer"] == "Answer to: hello"

    def test_worker_uses_first_required_string_property_as_input_key(self, custom_graph):
        """Non-messages graph: input key = first required string property."""
        from agentspan.agents.frameworks.langgraph import make_langgraph_worker

        stream_chunks = [
            ("updates", {"process": {"answer": "done"}}),
            ("values", {"query": "test prompt", "answer": "done"}),
        ]

        task = MagicMock()
        task.task_id = "t-input"
        task.workflow_instance_id = "wf-input-1"
        task.input_data = {"prompt": "test prompt", "session_id": ""}

        with patch.object(custom_graph, "stream", return_value=iter(stream_chunks)) as mock_stream:
            with patch("agentspan.agents.frameworks.langgraph._push_event_nonblocking"):
                worker_fn = make_langgraph_worker(
                    custom_graph, "custom_graph", "http://localhost:8080", "k", "s"
                )
                worker_fn(task)

        input_arg = mock_stream.call_args[0][0]
        # "query" is the first required string property in State schema
        assert "query" in input_arg
        assert input_arg["query"] == "test prompt"
