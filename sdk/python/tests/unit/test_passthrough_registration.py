# sdk/python/tests/unit/test_passthrough_registration.py
"""Tests for passthrough worker registration path in runtime.py."""
import os
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
        assert td.response_timeout_seconds == 120
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
            graph, "test_graph", "http://testserver:8080/api", "my_key", "my_secret",
            credential_names=None,
        )

    def test_build_passthrough_func_passes_credentials_to_langgraph_worker(self):
        """Verifies credential_names are forwarded to the worker factory."""
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
            runtime = AgentRuntime.__new__(AgentRuntime)
            runtime._config = config
            runtime._build_passthrough_func(
                graph, "langgraph", "test_graph", credentials=["GITHUB_TOKEN"],
            )

        mock_worker.assert_called_once_with(
            graph, "test_graph", "http://testserver:8080/api", "my_key", "my_secret",
            credential_names=["GITHUB_TOKEN"],
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
            options, "test_agent", "http://testserver:8080/api", "my_key", "my_secret",
            credential_names=None,
        )


def _make_fake_task(workflow_instance_id="wf-123", prompt="test prompt"):
    """Build a minimal Conductor-like Task object for passthrough worker tests."""
    task = MagicMock()
    task.workflow_instance_id = workflow_instance_id
    task.task_id = "task-abc"
    task.input_data = {
        "prompt": prompt,
        "__agentspan_ctx__": {"execution_token": "tok-fake"},
    }
    return task



class TestLangchainWorkerCredentialInjection:
    """Verify that make_langchain_worker actually injects credentials into os.environ."""

    # _get_credential_fetcher is imported from _dispatch inside the closure,
    # so we patch it at the source module.
    _FETCHER_PATCH = "agentspan.agents.runtime._dispatch._get_credential_fetcher"

    def test_closure_credentials_injected_into_environ(self):
        """When credential_names are passed, the worker resolves and injects them
        into os.environ before calling executor.invoke(), and cleans up after."""
        from agentspan.agents.frameworks.langchain import make_langchain_worker

        captured_env = {}

        def fake_invoke(input_dict, **kwargs):
            # Capture what's in os.environ when the executor runs
            captured_env["GITHUB_TOKEN"] = os.environ.get("GITHUB_TOKEN")
            return {"output": "token found"}

        executor = MagicMock()
        executor.invoke.side_effect = fake_invoke

        worker_fn = make_langchain_worker(
            executor, "test_lc", "http://s:8080", "k", "s",
            credential_names=["GITHUB_TOKEN"],
        )

        fake_fetcher = MagicMock()
        fake_fetcher.fetch.return_value = {"GITHUB_TOKEN": "ghp_test123"}

        task = _make_fake_task()

        with patch(self._FETCHER_PATCH, return_value=fake_fetcher):
            result = worker_fn(task)

        # The executor saw the credential during invocation
        assert captured_env["GITHUB_TOKEN"] == "ghp_test123"
        # Credential was cleaned up after execution
        assert "GITHUB_TOKEN" not in os.environ
        # Task completed successfully
        assert result.status.name == "COMPLETED"
        # Fetcher was called with the closure credential names
        fake_fetcher.fetch.assert_called_once_with("tok-fake", ["GITHUB_TOKEN"])

    def test_closure_credentials_used_even_when_workflow_registry_empty(self):
        """The closure path works even if _workflow_credentials has no entry for
        this execution_id — proving it avoids the race condition."""
        from agentspan.agents.frameworks.langchain import make_langchain_worker
        from agentspan.agents.runtime._dispatch import (
            _workflow_credentials,
            _workflow_credentials_lock,
        )

        # Ensure _workflow_credentials has NO entry for this workflow
        with _workflow_credentials_lock:
            _workflow_credentials.pop("wf-123", None)

        captured_env = {}

        def fake_invoke(input_dict, **kwargs):
            captured_env["MY_SECRET"] = os.environ.get("MY_SECRET")
            return {"output": "ok"}

        executor = MagicMock()
        executor.invoke.side_effect = fake_invoke

        worker_fn = make_langchain_worker(
            executor, "test_lc", "http://s:8080", "k", "s",
            credential_names=["MY_SECRET"],
        )

        fake_fetcher = MagicMock()
        fake_fetcher.fetch.return_value = {"MY_SECRET": "s3cr3t"}
        task = _make_fake_task()

        with patch(self._FETCHER_PATCH, return_value=fake_fetcher):
            result = worker_fn(task)

        # Even with empty _workflow_credentials, the closure names were used
        assert captured_env["MY_SECRET"] == "s3cr3t"
        assert "MY_SECRET" not in os.environ
        assert result.status.name == "COMPLETED"

    def test_no_credentials_means_no_fetch(self):
        """When credential_names is None/empty and _workflow_credentials is empty,
        no credential fetch is attempted."""
        from agentspan.agents.frameworks.langchain import make_langchain_worker
        from agentspan.agents.runtime._dispatch import (
            _workflow_credentials,
            _workflow_credentials_lock,
        )

        # Ensure _workflow_credentials is also empty
        with _workflow_credentials_lock:
            _workflow_credentials.pop("wf-123", None)

        executor = MagicMock()
        executor.invoke.return_value = {"output": "no creds needed"}

        worker_fn = make_langchain_worker(
            executor, "test_lc", "http://s:8080", "k", "s",
            credential_names=None,
        )

        task = _make_fake_task()

        with patch(self._FETCHER_PATCH) as mock_get_fetcher:
            result = worker_fn(task)

        # Fetcher factory should never be called — no credentials requested
        mock_get_fetcher.assert_not_called()
        assert result.status.name == "COMPLETED"


    # Full extraction path tests moved to test_credential_injection_integration.py
    # which uses real LangChain tools, real serialize_agent, real Conductor Tasks.
