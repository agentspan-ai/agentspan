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


def _make_tool_task(workflow_instance_id="wf-456"):
    """Build a minimal Conductor-like Task for full-extraction tool worker tests."""
    task = MagicMock()
    task.workflow_instance_id = workflow_instance_id
    task.task_id = "task-tool-001"
    task.input_data = {
        "__agentspan_ctx__": {"execution_token": "tok-tool-fake"},
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


class TestFullExtractionCredentialInjection:
    """Verify that make_tool_worker with credential_names injects credentials
    into os.environ for framework-extracted tools (the full extraction path)."""

    _FETCHER_PATCH = "agentspan.agents.runtime._dispatch._get_credential_fetcher"

    def test_closure_credentials_injected_into_environ(self):
        """When credential_names are passed to make_tool_worker, the worker
        resolves and injects them into os.environ before calling the tool."""
        from agentspan.agents.runtime._dispatch import make_tool_worker

        captured_env = {}

        def check_github_token():
            captured_env["GITHUB_TOKEN"] = os.environ.get("GITHUB_TOKEN")
            return "token found"

        worker_fn = make_tool_worker(
            check_github_token, "check_github_token",
            credential_names=["GITHUB_TOKEN"],
        )

        fake_fetcher = MagicMock()
        fake_fetcher.fetch.return_value = {"GITHUB_TOKEN": "ghp_test123"}
        task = _make_tool_task()

        with patch(self._FETCHER_PATCH, return_value=fake_fetcher):
            result = worker_fn(task)

        assert captured_env["GITHUB_TOKEN"] == "ghp_test123"
        assert "GITHUB_TOKEN" not in os.environ
        assert result.status.name == "COMPLETED"
        fake_fetcher.fetch.assert_called_once_with("tok-tool-fake", ["GITHUB_TOKEN"])

    def test_closure_credentials_override_workflow_credentials(self):
        """Closure credentials take priority over _workflow_credentials,
        ensuring no dependency on workflow_instance_id matching."""
        from agentspan.agents.runtime._dispatch import (
            _workflow_credentials,
            _workflow_credentials_lock,
            make_tool_worker,
        )

        # Set _workflow_credentials with a DIFFERENT credential name
        with _workflow_credentials_lock:
            _workflow_credentials["wf-456"] = ["WRONG_CRED"]

        captured_env = {}

        def my_tool():
            captured_env["GITHUB_TOKEN"] = os.environ.get("GITHUB_TOKEN")
            return "ok"

        worker_fn = make_tool_worker(
            my_tool, "my_tool",
            credential_names=["GITHUB_TOKEN"],
        )

        fake_fetcher = MagicMock()
        fake_fetcher.fetch.return_value = {"GITHUB_TOKEN": "ghp_abc"}
        task = _make_tool_task()

        with patch(self._FETCHER_PATCH, return_value=fake_fetcher):
            result = worker_fn(task)

        # Closure credentials were used, NOT _workflow_credentials
        assert captured_env["GITHUB_TOKEN"] == "ghp_abc"
        fake_fetcher.fetch.assert_called_once_with("tok-tool-fake", ["GITHUB_TOKEN"])
        assert result.status.name == "COMPLETED"

        # Clean up
        with _workflow_credentials_lock:
            _workflow_credentials.pop("wf-456", None)

    def test_no_closure_credentials_falls_back_to_workflow_credentials(self):
        """When make_tool_worker has no closure credentials, falls back to
        _workflow_credentials for backward compatibility."""
        from agentspan.agents.runtime._dispatch import (
            _workflow_credentials,
            _workflow_credentials_lock,
            make_tool_worker,
        )

        with _workflow_credentials_lock:
            _workflow_credentials["wf-456"] = ["FALLBACK_TOKEN"]

        captured_env = {}

        def my_tool():
            captured_env["FALLBACK_TOKEN"] = os.environ.get("FALLBACK_TOKEN")
            return "ok"

        worker_fn = make_tool_worker(my_tool, "my_tool")  # no credential_names

        fake_fetcher = MagicMock()
        fake_fetcher.fetch.return_value = {"FALLBACK_TOKEN": "fb_secret"}
        task = _make_tool_task()

        with patch(self._FETCHER_PATCH, return_value=fake_fetcher):
            result = worker_fn(task)

        assert captured_env["FALLBACK_TOKEN"] == "fb_secret"
        assert result.status.name == "COMPLETED"

        with _workflow_credentials_lock:
            _workflow_credentials.pop("wf-456", None)

    def test_no_credentials_means_no_fetch(self):
        """When no credential_names and no _workflow_credentials entry,
        no credential fetch is attempted."""
        from agentspan.agents.runtime._dispatch import (
            _workflow_credentials,
            _workflow_credentials_lock,
            make_tool_worker,
        )

        with _workflow_credentials_lock:
            _workflow_credentials.pop("wf-456", None)

        def my_tool():
            return "no creds needed"

        worker_fn = make_tool_worker(my_tool, "my_tool")

        task = _make_tool_task()

        with patch(self._FETCHER_PATCH) as mock_get_fetcher:
            result = worker_fn(task)

        mock_get_fetcher.assert_not_called()
        assert result.status.name == "COMPLETED"


class TestRegisterFrameworkWorkersCredentials:
    """Verify that _register_framework_workers passes credentials through."""

    def test_register_framework_workers_passes_credentials_to_make_tool_worker(self):
        """_register_framework_workers(workers, credentials=...) should forward
        credentials to make_tool_worker for each worker."""
        from agentspan.agents.runtime.runtime import AgentRuntime
        from agentspan.agents.runtime.config import AgentConfig

        config = AgentConfig(
            server_url="http://testserver:8080/api",
            auth_key="my_key",
            auth_secret="my_secret",
            auto_start_workers=False,
        )

        runtime = AgentRuntime.__new__(AgentRuntime)
        runtime._config = config
        runtime._worker_start_lock = __import__("threading").Lock()
        runtime._registered_tool_names = set()
        runtime._workers_started = False

        fake_func = MagicMock()
        workers = [MagicMock(name="my_tool", func=fake_func)]
        workers[0].name = "my_tool"
        workers[0].func = fake_func

        with patch("agentspan.agents.runtime._dispatch.make_tool_worker") as mock_mtw, \
             patch("conductor.client.worker.worker_task.worker_task") as mock_wt:
            mock_mtw.return_value = MagicMock()
            mock_wt.return_value = lambda f: f
            runtime._register_framework_workers(workers, credentials=["GITHUB_TOKEN"])

        mock_mtw.assert_called_once_with(
            fake_func, "my_tool", credential_names=["GITHUB_TOKEN"],
        )
