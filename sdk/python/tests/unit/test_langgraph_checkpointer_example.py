# sdk/python/tests/unit/test_langgraph_checkpointer_example.py
"""
Example 3: LangGraph with MemorySaver checkpointer.
Verifies session_id -> thread_id mapping for multi-turn conversation.
"""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def graph_with_checkpointer():
    pytest.importorskip("langgraph")
    from langgraph.prebuilt import create_react_agent
    from langgraph.checkpoint.memory import MemorySaver
    from langchain_core.messages import AIMessage

    llm = MagicMock()
    llm.invoke.return_value = AIMessage(content="Hello!")
    llm.bind_tools = lambda tools: llm

    memory = MemorySaver()
    graph = create_react_agent(llm, tools=[], checkpointer=memory)
    return graph


class TestCheckpointerSupport:
    def test_session_id_is_passed_as_thread_id(self, graph_with_checkpointer):
        from langchain_core.messages import AIMessage
        from agentspan.agents.frameworks.langgraph import make_langgraph_worker

        ai_msg = AIMessage(content="Hello!", tool_calls=[])
        stream_chunks = [
            ("updates", {"agent": {"messages": [ai_msg]}}),
            ("values", {"messages": [ai_msg]}),
        ]

        task = MagicMock()
        task.task_id = "t-ckpt"
        task.workflow_instance_id = "wf-ckpt-1"
        task.input_data = {"prompt": "Hi", "session_id": "user-session-abc"}

        with patch.object(graph_with_checkpointer, "stream", return_value=iter(stream_chunks)) as mock_stream:
            with patch("agentspan.agents.frameworks.langgraph._push_event_nonblocking"):
                worker_fn = make_langgraph_worker(
                    graph_with_checkpointer, "memory_graph", "http://localhost:8080", "k", "s"
                )
                worker_fn(task)

        config_arg = mock_stream.call_args[0][1]
        assert config_arg["configurable"]["thread_id"] == "user-session-abc"

    def test_empty_session_id_passes_no_config(self, graph_with_checkpointer):
        from langchain_core.messages import AIMessage
        from agentspan.agents.frameworks.langgraph import make_langgraph_worker

        ai_msg = AIMessage(content="Hello!", tool_calls=[])
        stream_chunks = [
            ("updates", {"agent": {"messages": [ai_msg]}}),
            ("values", {"messages": [ai_msg]}),
        ]

        task = MagicMock()
        task.task_id = "t-no-session"
        task.workflow_instance_id = "wf-no-session"
        task.input_data = {"prompt": "Hi", "session_id": ""}

        with patch.object(graph_with_checkpointer, "stream", return_value=iter(stream_chunks)) as mock_stream:
            with patch("agentspan.agents.frameworks.langgraph._push_event_nonblocking"):
                worker_fn = make_langgraph_worker(
                    graph_with_checkpointer, "memory_graph", "http://localhost:8080", "k", "s"
                )
                worker_fn(task)

        config_arg = mock_stream.call_args[0][1]
        # Empty session_id -> empty config dict (no configurable.thread_id)
        assert "configurable" not in config_arg

    def test_checkpointer_error_returns_failed_result(self, graph_with_checkpointer):
        from agentspan.agents.frameworks.langgraph import make_langgraph_worker

        graph_with_checkpointer.stream = MagicMock(
            side_effect=ValueError("No checkpointer configured")
        )

        task = MagicMock()
        task.task_id = "t-err"
        task.workflow_instance_id = "wf-err"
        task.input_data = {"prompt": "Hi", "session_id": "s-1"}

        with patch("agentspan.agents.frameworks.langgraph._push_event_nonblocking"):
            worker_fn = make_langgraph_worker(
                graph_with_checkpointer, "memory_graph", "http://localhost:8080", "k", "s"
            )
            result = worker_fn(task)

        assert result.status == "FAILED"
        assert "checkpointer" in result.reason_for_incompletion.lower()
