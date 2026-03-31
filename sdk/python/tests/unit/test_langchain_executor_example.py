# sdk/python/tests/unit/test_langchain_executor_example.py
"""
Example 4: LangChain AgentExecutor.
Verifies full pipeline from executor creation through worker invocation.
"""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def agent_executor():
    """Build a minimal AgentExecutor-like object (mock with real type name)."""
    pytest.importorskip("langchain")

    # Build a MagicMock whose type name is "AgentExecutor" so that
    # detect_framework() recognises it as a LangChain executor.
    executor = MagicMock()
    type(executor).__name__ = "AgentExecutor"
    executor.invoke.return_value = {"output": "42"}
    executor.name = "math_executor"
    return executor


class TestLangChainExecutorDetection:
    def test_detect_framework_returns_langchain(self, agent_executor):
        from agentspan.agents.frameworks.serializer import detect_framework
        assert detect_framework(agent_executor) == "langchain"

    def test_serialize_returns_single_worker(self, agent_executor):
        from agentspan.agents.frameworks.langchain import serialize_langchain
        raw_config, workers = serialize_langchain(agent_executor)
        assert len(workers) == 1
        assert raw_config["name"] == "math_executor"


class TestLangChainWorkerInvocation:
    def test_worker_returns_executor_output(self, agent_executor):
        from agentspan.agents.frameworks.langchain import make_langchain_worker

        task = MagicMock()
        task.task_id = "t-lc"
        task.workflow_instance_id = "wf-lc-1"
        task.input_data = {"prompt": "What is 6*7?", "session_id": ""}

        with patch("agentspan.agents.frameworks.langchain._push_event_nonblocking"):
            worker_fn = make_langchain_worker(
                agent_executor, "math_executor", "http://localhost:8080", "k", "s"
            )
            result = worker_fn(task)

        assert result.status == "COMPLETED"
        assert result.output_data["result"] == "42"

    def test_worker_injects_callback_handler(self, agent_executor):
        """Verify that AgentspanCallbackHandler is passed to executor.invoke."""
        from agentspan.agents.frameworks.langchain import make_langchain_worker, AgentspanCallbackHandler

        task = MagicMock()
        task.task_id = "t-cb"
        task.workflow_instance_id = "wf-cb-1"
        task.input_data = {"prompt": "test", "session_id": ""}

        with patch("agentspan.agents.frameworks.langchain._push_event_nonblocking"):
            worker_fn = make_langchain_worker(
                agent_executor, "math_executor", "http://localhost:8080", "k", "s"
            )
            worker_fn(task)

        invoke_call = agent_executor.invoke.call_args
        # config is passed as a keyword argument: executor.invoke({...}, config={...})
        config = invoke_call[1].get("config") or (invoke_call[0][1] if len(invoke_call[0]) > 1 else {})
        callbacks = config.get("callbacks", [])
        assert any(isinstance(cb, AgentspanCallbackHandler) for cb in callbacks)

    def test_callback_on_tool_start_pushes_event(self):
        """Callback pushes tool_call event on tool start."""
        pytest.importorskip("langchain_core")
        from agentspan.agents.frameworks.langchain import AgentspanCallbackHandler
        from uuid import uuid4

        pushed = []
        with patch("agentspan.agents.frameworks.langchain._push_event_nonblocking",
                   side_effect=lambda exec_id, event, *a: pushed.append(event)):
            run_id = uuid4()
            handler = AgentspanCallbackHandler("wf-1", "http://localhost:8080", "k", "s")
            handler.on_tool_start({"name": "calculator"}, "6*7", run_id=run_id)

        assert len(pushed) == 1
        assert pushed[0]["type"] == "tool_call"
        assert pushed[0]["toolName"] == "calculator"

    def test_callback_on_tool_end_pushes_event(self):
        """Callback pushes tool_result event on tool end."""
        pytest.importorskip("langchain_core")
        from agentspan.agents.frameworks.langchain import AgentspanCallbackHandler
        from uuid import uuid4

        pushed = []
        with patch("agentspan.agents.frameworks.langchain._push_event_nonblocking",
                   side_effect=lambda exec_id, event, *a: pushed.append(event)):
            run_id = uuid4()
            handler = AgentspanCallbackHandler("wf-1", "http://localhost:8080", "k", "s")
            handler.on_tool_start({"name": "calculator"}, "6*7", run_id=run_id)
            handler.on_tool_end("42", run_id=run_id)

        results = [e for e in pushed if e["type"] == "tool_result"]
        assert len(results) == 1
        assert results[0]["result"] == "42"
