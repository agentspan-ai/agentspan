# sdk/python/tests/unit/test_credential_injection_integration.py
"""Integration tests for credential injection in framework-extracted tools.

These tests exercise the real code path from serialization through worker
invocation.  Only the external credential server HTTP call is stubbed.
Everything else — serialize_agent, make_tool_worker, Conductor Task,
os.environ injection — is real.
"""
import pytest

pytest.importorskip("langchain_core", reason="langchain_core not installed")
import os
from unittest.mock import MagicMock, patch

import pytest
from conductor.client.http.models import Task, TaskResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _real_conductor_task(workflow_instance_id="wf-integ-001"):
    """Build a real Conductor Task object (not a mock)."""
    task = Task()
    task.task_id = "task-integ-001"
    task.workflow_instance_id = workflow_instance_id
    task.input_data = {
        "__agentspan_ctx__": {"execution_token": "tok-integ-fake"},
    }
    return task


def _make_lc_tool_and_graph():
    """Create a real LangChain @lc_tool and a real create_react_agent graph.

    Returns (graph, tool_func) where tool_func is the raw @lc_tool object.
    Uses a real ChatOpenAI with a fake key — no API call is made.
    """
    os.environ.setdefault("OPENAI_API_KEY", "sk-fake-key-for-testing")

    from langchain_core.tools import tool as lc_tool
    from langchain_openai import ChatOpenAI
    from langgraph.prebuilt import create_react_agent

    @lc_tool
    def check_github_token() -> str:
        """Check if GitHub token is available in the environment."""
        token = os.environ.get("GITHUB_TOKEN", "")
        if token:
            return f"found:{token[:8]}"
        return "NOT_FOUND"

    llm = ChatOpenAI(model="gpt-4o")
    graph = create_react_agent(llm, tools=[check_github_token])
    return graph, check_github_token


# Patch target: the credential fetcher factory in _dispatch (the only external dep)
_FETCHER_PATCH = "agentspan.agents.runtime._dispatch._get_credential_fetcher"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFullExtractionPathIntegration:
    """End-to-end integration: real serialize_agent → real make_tool_worker →
    real Conductor Task → real os.environ injection."""

    def test_serialize_agent_takes_full_extraction_path(self):
        """Verify that a create_react_agent graph with tools goes through
        full extraction (not passthrough or graph-structure)."""
        from agentspan.agents.frameworks.serializer import serialize_agent

        graph, _ = _make_lc_tool_and_graph()
        raw_config, workers = serialize_agent(graph)

        # Full extraction: model + tools found → workers have func != None
        assert len(workers) == 1
        assert workers[0].func is not None, "Expected full extraction (func != None)"
        assert workers[0].name == "check_github_token"
        assert "model" in raw_config
        assert "tools" in raw_config
        assert "_graph" not in raw_config

    def test_extracted_tool_receives_credential_in_environ(self):
        """The extracted tool function sees GITHUB_TOKEN in os.environ when
        invoked through make_tool_worker with credential_names."""
        from agentspan.agents.frameworks.serializer import serialize_agent
        from agentspan.agents.runtime._dispatch import make_tool_worker

        graph, _ = _make_lc_tool_and_graph()
        _, workers = serialize_agent(graph)

        # This is what _register_framework_workers does:
        tool_func = workers[0].func
        tool_func._agentspan_framework_callable = True
        worker_fn = make_tool_worker(
            tool_func, workers[0].name, credential_names=["GITHUB_TOKEN"],
        )

        fake_fetcher = MagicMock()
        fake_fetcher.fetch.return_value = {"GITHUB_TOKEN": "ghp_real_token_123"}
        task = _real_conductor_task()

        with patch(_FETCHER_PATCH, return_value=fake_fetcher):
            result = worker_fn(task)

        # The tool saw the credential during execution
        assert result.status.name == "COMPLETED"
        assert "found:ghp_real" in str(result.output_data)

        # Credential was cleaned up from env
        assert "GITHUB_TOKEN" not in os.environ

        # Fetcher was called with the correct token and credential names
        fake_fetcher.fetch.assert_called_once_with("tok-integ-fake", ["GITHUB_TOKEN"])

    def test_extracted_tool_without_credentials_sees_empty_env(self):
        """Without credential_names, the tool sees no GITHUB_TOKEN."""
        from agentspan.agents.frameworks.serializer import serialize_agent
        from agentspan.agents.runtime._dispatch import (
            _workflow_credentials,
            _workflow_credentials_lock,
            make_tool_worker,
        )

        graph, _ = _make_lc_tool_and_graph()
        _, workers = serialize_agent(graph)

        tool_func = workers[0].func
        tool_func._agentspan_framework_callable = True

        # No credential_names, no _workflow_credentials entry
        with _workflow_credentials_lock:
            _workflow_credentials.pop("wf-integ-001", None)
        worker_fn = make_tool_worker(tool_func, workers[0].name)

        # Ensure GITHUB_TOKEN is NOT in env
        os.environ.pop("GITHUB_TOKEN", None)

        task = _real_conductor_task()

        with patch(_FETCHER_PATCH) as mock_get_fetcher:
            result = worker_fn(task)

        assert result.status.name == "COMPLETED"
        assert "NOT_FOUND" in str(result.output_data)
        mock_get_fetcher.assert_not_called()

    def test_credential_cleanup_on_tool_exception(self):
        """Credentials are cleaned up even when the tool raises."""
        from agentspan.agents.runtime._dispatch import make_tool_worker

        def failing_tool():
            """A tool that checks env then raises."""
            assert os.environ.get("SECRET_KEY") == "s3cr3t"
            raise RuntimeError("intentional failure")

        worker_fn = make_tool_worker(
            failing_tool, "failing_tool", credential_names=["SECRET_KEY"],
        )

        fake_fetcher = MagicMock()
        fake_fetcher.fetch.return_value = {"SECRET_KEY": "s3cr3t"}
        task = _real_conductor_task()

        with patch(_FETCHER_PATCH, return_value=fake_fetcher):
            result = worker_fn(task)

        assert result.status.name == "FAILED"
        assert "SECRET_KEY" not in os.environ

    def test_register_framework_workers_wires_credentials_to_make_tool_worker(self):
        """_register_framework_workers passes credentials through so the
        resulting Conductor worker has them in its closure.

        This is the exact flow that was broken: credentials were passed to
        runtime.run() but never reached the tool worker's closure."""
        from agentspan.agents.frameworks.serializer import serialize_agent
        from agentspan.agents.runtime._dispatch import make_tool_worker

        graph, _ = _make_lc_tool_and_graph()
        _, workers = serialize_agent(graph)

        # Capture what make_tool_worker is called with
        captured_calls = []
        original_make_tool_worker = make_tool_worker

        def spy_make_tool_worker(*args, **kwargs):
            captured_calls.append((args, kwargs))
            return original_make_tool_worker(*args, **kwargs)

        from agentspan.agents.runtime.runtime import AgentRuntime
        from agentspan.agents.runtime.config import AgentConfig

        config = AgentConfig(
            server_url="http://testserver:8080/api",
            auth_key="k",
            auth_secret="s",
            auto_start_workers=False,
        )
        runtime = AgentRuntime.__new__(AgentRuntime)
        runtime._config = config
        runtime._worker_start_lock = __import__("threading").Lock()
        runtime._registered_tool_names = set()
        runtime._workers_started = False

        with patch("agentspan.agents.runtime._dispatch.make_tool_worker", side_effect=spy_make_tool_worker), \
             patch("conductor.client.worker.worker_task.worker_task", return_value=lambda f: f):
            runtime._register_framework_workers(workers, credentials=["GITHUB_TOKEN"])

        assert len(captured_calls) == 1
        _, kwargs = captured_calls[0]
        assert kwargs.get("credential_names") == ["GITHUB_TOKEN"]
