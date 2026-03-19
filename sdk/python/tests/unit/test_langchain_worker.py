# sdk/python/tests/unit/test_langchain_worker.py
"""Unit tests for the LangChain passthrough worker."""
from unittest.mock import MagicMock, patch


def _make_executor(output="answer"):
    executor = MagicMock()
    type(executor).__name__ = "AgentExecutor"
    executor.invoke.return_value = {"output": output}
    return executor


def _make_task(prompt="Hello", session_id="", workflow_id="wf-456"):
    from conductor.client.http.models.task import Task
    task = MagicMock(spec=Task)
    task.input_data = {"prompt": prompt, "session_id": session_id}
    task.workflow_instance_id = workflow_id
    return task


class TestSerializeLangchain:
    def test_returns_single_worker_info(self):
        from agentspan.agents.frameworks.langchain import serialize_langchain
        executor = _make_executor()
        executor.name = "my_executor"

        raw_config, workers = serialize_langchain(executor)

        assert len(workers) == 1
        assert workers[0].name == "my_executor"

    def test_raw_config_has_name_and_worker_name(self):
        from agentspan.agents.frameworks.langchain import serialize_langchain
        executor = _make_executor()
        executor.name = "my_executor"

        raw_config, _ = serialize_langchain(executor)

        assert raw_config["name"] == "my_executor"
        assert raw_config["_worker_name"] == "my_executor"


class TestMakeLangchainWorker:
    def test_worker_returns_executor_output(self):
        from agentspan.agents.frameworks.langchain import make_langchain_worker

        executor = _make_executor(output="The answer is 42")
        task = _make_task(prompt="What is the answer?")

        with patch("agentspan.agents.frameworks.langchain._push_event_nonblocking"):
            worker_fn = make_langchain_worker(
                executor, "my_executor", "http://localhost:8080", "key", "secret"
            )
            result = worker_fn(task)

        assert result.status == "COMPLETED"
        assert result.output_data["result"] == "The answer is 42"

    def test_worker_passes_prompt_as_input(self):
        from agentspan.agents.frameworks.langchain import make_langchain_worker

        executor = _make_executor()
        task = _make_task(prompt="search for python")

        with patch("agentspan.agents.frameworks.langchain._push_event_nonblocking"):
            worker_fn = make_langchain_worker(
                executor, "my_executor", "http://localhost:8080", "key", "secret"
            )
            worker_fn(task)

        call_args = executor.invoke.call_args
        assert call_args[0][0]["input"] == "search for python"
        config = call_args[1]["config"]
        assert len(config["callbacks"]) == 1
        from agentspan.agents.frameworks.langchain import AgentspanCallbackHandler
        assert isinstance(config["callbacks"][0], AgentspanCallbackHandler)

    def test_worker_returns_failed_on_exception(self):
        from agentspan.agents.frameworks.langchain import make_langchain_worker

        executor = _make_executor()
        executor.invoke.side_effect = RuntimeError("tool error")
        task = _make_task()

        with patch("agentspan.agents.frameworks.langchain._push_event_nonblocking"):
            worker_fn = make_langchain_worker(
                executor, "my_executor", "http://localhost:8080", "key", "secret"
            )
            result = worker_fn(task)

        assert result.status == "FAILED"
        assert "tool error" in result.reason_for_incompletion

    def test_worker_pushes_tool_call_event_via_callback(self):
        from agentspan.agents.frameworks.langchain import AgentspanCallbackHandler
        from uuid import uuid4

        pushed_events = []

        def fake_push(wf_id, event, *args):
            pushed_events.append(event)

        with patch("agentspan.agents.frameworks.langchain._push_event_nonblocking", side_effect=fake_push):
            run_id = uuid4()
            handler = AgentspanCallbackHandler("wf-push-test", "http://localhost:8080", "k", "s")
            handler.on_tool_start({"name": "search"}, "python", run_id=run_id)
            handler.on_tool_end("result text", run_id=run_id)

        tool_calls = [e for e in pushed_events if e["type"] == "tool_call"]
        tool_results = [e for e in pushed_events if e["type"] == "tool_result"]
        assert len(tool_calls) == 1
        assert tool_calls[0]["toolName"] == "search"
        assert len(tool_results) == 1
        assert tool_results[0]["toolName"] == "search"  # verifies run_id keying
