# sdk/python/tests/unit/test_langgraph_react_example.py
"""
Example 1: LangGraph ReAct agent.
Verifies that a graph built with create_react_agent can be:
1. Detected as "langgraph" framework
2. Serialized to (raw_config, [WorkerInfo])
3. Invoked via the pre-wrapped worker function with correct output extraction
"""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def react_graph():
    """Build a real create_react_agent graph with a mocked LLM."""
    pytest.importorskip("langgraph")
    from langgraph.prebuilt import create_react_agent
    from langchain_core.messages import AIMessage

    # Mock LLM that always returns a plain text response (no tool calls)
    llm = MagicMock()
    llm.invoke.return_value = AIMessage(content="The capital is Paris.")
    llm.bind_tools = lambda tools: llm  # bind_tools returns itself

    # Simple tool
    from langchain_core.tools import tool

    @tool
    def get_capital(country: str) -> str:
        """Get the capital of a country."""
        return f"The capital of {country} is Paris."

    graph = create_react_agent(llm, tools=[get_capital])
    return graph


class TestLangGraphReActDetection:
    def test_detect_framework_returns_langgraph(self, react_graph):
        from agentspan.agents.frameworks.serializer import detect_framework
        assert detect_framework(react_graph) == "langgraph"

    def test_serialize_returns_single_worker(self, react_graph):
        from agentspan.agents.frameworks.langgraph import serialize_langgraph
        raw_config, workers = serialize_langgraph(react_graph)
        assert len(workers) == 1

    def test_worker_invocation_extracts_ai_message_output(self, react_graph):
        from langchain_core.messages import HumanMessage, AIMessage
        from agentspan.agents.frameworks.langgraph import make_langgraph_worker

        # Patch the graph's stream to return controlled output
        final_ai_msg = AIMessage(content="The capital is Paris.", tool_calls=[])

        stream_chunks = [
            ("updates", {"agent": {"messages": [final_ai_msg]}}),
            ("values", {"messages": [
                HumanMessage(content="What is the capital of France?"),
                final_ai_msg,
            ]}),
        ]

        task = MagicMock()
        task.task_id = "t-1"
        task.workflow_instance_id = "wf-react-1"
        task.input_data = {"prompt": "What is the capital of France?", "session_id": ""}

        with patch.object(react_graph, "stream", return_value=iter(stream_chunks)):
            with patch("agentspan.agents.frameworks.langgraph._push_event_nonblocking"):
                worker_fn = make_langgraph_worker(
                    react_graph, "react_agent", "http://localhost:8080", "key", "secret"
                )
                result = worker_fn(task)

        assert result.status == "COMPLETED"
        assert result.output_data["result"] == "The capital is Paris."

    def test_worker_uses_messages_input_format(self, react_graph):
        """create_react_agent graphs use messages-based state."""
        from langchain_core.messages import HumanMessage, AIMessage
        from agentspan.agents.frameworks.langgraph import make_langgraph_worker

        final_msg = AIMessage(content="Done.", tool_calls=[])
        stream_chunks = [
            ("updates", {"agent": {"messages": [final_msg]}}),
            ("values", {"messages": [final_msg]}),
        ]

        task = MagicMock()
        task.task_id = "t-2"
        task.workflow_instance_id = "wf-react-2"
        task.input_data = {"prompt": "Hello", "session_id": ""}

        with patch.object(react_graph, "stream", return_value=iter(stream_chunks)) as mock_stream:
            with patch("agentspan.agents.frameworks.langgraph._push_event_nonblocking"):
                worker_fn = make_langgraph_worker(
                    react_graph, "react_agent", "http://localhost:8080", "key", "secret"
                )
                worker_fn(task)

        # Verify the input to stream() has messages key with HumanMessage
        input_arg = mock_stream.call_args[0][0]
        assert "messages" in input_arg
        assert isinstance(input_arg["messages"][0], HumanMessage)
        assert input_arg["messages"][0].content == "Hello"
