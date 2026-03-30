# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for the AgentRuntime.

Tests runtime helper methods (extract_output, extract_handoff_result, etc.)
using mock workflow objects. Does NOT require a running Conductor server.
"""

import logging
import uuid
from unittest.mock import MagicMock, patch

import pytest

from agentspan.agents.agent import Agent
from agentspan.agents.result import AgentStatus, EventType


def _mock_requests_post(response_json=None, status_code=200):
    """Create a mock for requests.post that returns a fake Response."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = response_json or {}
    mock_resp.raise_for_status.return_value = None
    return MagicMock(return_value=mock_resp)


def _mock_requests_get(response_json=None, status_code=200):
    """Create a mock for requests.get that returns a fake Response."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = response_json or {}
    mock_resp.raise_for_status.return_value = None
    return MagicMock(return_value=mock_resp)


class MockWorkflowRun:
    """Mock workflow run result."""

    def __init__(
        self, output=None, variables=None, tasks=None, status="COMPLETED", execution_id="test-wf-123"
    ):
        self.output = output
        self.variables = variables or {}
        self.tasks = tasks or []
        self.status = status
        self.execution_id = execution_id


class TestExtractOutput:
    """Test _extract_output() helper."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def test_extract_simple_output(self, runtime):
        agent = Agent(name="test", model="openai/gpt-4o")
        wf_run = MockWorkflowRun(output={"result": "Hello world"})
        output = runtime._extract_output(wf_run, agent)
        assert output == "Hello world"

    def test_extract_none_output(self, runtime):
        agent = Agent(name="test", model="openai/gpt-4o")
        wf_run = MockWorkflowRun(output=None)
        output = runtime._extract_output(wf_run, agent)
        assert output is None

    def test_extract_dict_output_without_result(self, runtime):
        agent = Agent(name="test", model="openai/gpt-4o")
        wf_run = MockWorkflowRun(output={"custom": "data"})
        output = runtime._extract_output(wf_run, agent)
        assert output == {"custom": "data"}

    def test_extract_string_output(self, runtime):
        agent = Agent(name="test", model="openai/gpt-4o")
        wf_run = MockWorkflowRun(output="plain string")
        output = runtime._extract_output(wf_run, agent)
        assert output == "plain string"


class TestExtractHandoffResult:
    """Test _extract_handoff_result() helper."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def test_simple_handoff(self, runtime):
        result = {"agent_a": "Answer from A", "agent_b": None}
        output = runtime._extract_handoff_result(result)
        assert output == "Answer from A"

    def test_nested_handoff(self, runtime):
        result = {
            "agent_a": None,
            "agent_b": {"sub_1": "Deep answer", "sub_2": None},
        }
        output = runtime._extract_handoff_result(result)
        assert output == "Deep answer"

    def test_non_dict_passthrough(self, runtime):
        output = runtime._extract_handoff_result("just a string")
        assert output == "just a string"

    def test_all_none_returns_dict(self, runtime):
        result = {"a": None, "b": None}
        output = runtime._extract_handoff_result(result)
        assert output == {"a": None, "b": None}


class TestExtractMessages:
    """Test _extract_messages() helper."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def test_extracts_from_variables(self, runtime):
        msgs = [{"role": "user", "message": "Hi"}]
        wf_run = MockWorkflowRun(variables={"messages": msgs})
        extracted = runtime._extract_messages(wf_run)
        assert extracted == msgs

    def test_empty_variables(self, runtime):
        wf_run = MockWorkflowRun(variables={})
        extracted = runtime._extract_messages(wf_run)
        assert extracted == []

    def test_no_variables_attr(self, runtime):
        wf_run = MockWorkflowRun()
        del wf_run.variables
        extracted = runtime._extract_messages(wf_run)
        assert extracted == []


class TestSingletonRuntime:
    """Test that run.py uses a singleton runtime."""

    def test_singleton_returns_same_instance(self):
        import agentspan.agents.run as run_module
        from agentspan.agents.run import _get_default_runtime

        # Reset singleton
        run_module._default_runtime = None

        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                with patch("agentspan.agents.runtime.server.ensure_server_running"):
                    rt1 = _get_default_runtime()
                    rt2 = _get_default_runtime()
                    assert rt1 is rt2

        # Cleanup
        run_module._default_runtime = None


class TestAgentRuntimeInit:
    """Test AgentRuntime constructor signature and resolution logic."""

    def test_no_args_falls_back_to_env(self):
        """AgentRuntime() with no args loads config from environment."""
        import os

        env_backup = {}
        for key in ["AGENTSPAN_SERVER_URL", "AGENTSPAN_AUTH_KEY", "AGENTSPAN_AUTH_SECRET"]:
            env_backup[key] = os.environ.pop(key, None)

        os.environ["AGENTSPAN_SERVER_URL"] = "http://env-server/api"
        os.environ["AGENTSPAN_AUTH_KEY"] = "env-key"
        os.environ["AGENTSPAN_AUTH_SECRET"] = "env-secret"

        try:
            with patch("conductor.client.orkes_clients.OrkesClients"):
                with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                    from agentspan.agents.runtime.runtime import AgentRuntime

                    rt = AgentRuntime()
                    assert rt._config.server_url == "http://env-server/api"
                    assert rt._config.auth_key == "env-key"
                    assert rt._config.auth_secret == "env-secret"
        finally:
            for key in ["AGENTSPAN_SERVER_URL", "AGENTSPAN_AUTH_KEY", "AGENTSPAN_AUTH_SECRET"]:
                os.environ.pop(key, None)
            for key, val in env_backup.items():
                if val is not None:
                    os.environ[key] = val

    def test_explicit_params(self):
        """AgentRuntime(server_url=..., api_key=..., api_secret=...) uses explicit values."""
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.runtime import AgentRuntime

                rt = AgentRuntime(
                    server_url="http://explicit/api",
                    api_key="explicit-key",
                    api_secret="explicit-secret",
                )
                assert rt._config.server_url == "http://explicit/api"
                assert rt._config.api_key == "explicit-key"
                assert rt._config.auth_secret == "explicit-secret"

    def test_config_object(self):
        """AgentRuntime(config=AgentConfig(...)) uses the config object."""
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                cfg = AgentConfig(
                    server_url="http://config/api",
                    auth_key="config-key",
                    auth_secret="config-secret",
                )
                rt = AgentRuntime(config=cfg)
                assert rt._config.server_url == "http://config/api"
                assert rt._config.auth_key == "config-key"
                assert rt._config.auth_secret == "config-secret"

    def test_explicit_overrides_config(self):
        """Explicit params take precedence over config object values."""
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                cfg = AgentConfig(
                    server_url="http://config/api",
                    auth_key="config-key",
                    auth_secret="config-secret",
                )
                rt = AgentRuntime(config=cfg, server_url="http://override/api")
                assert rt._config.server_url == "http://override/api"
                # Non-overridden values come from config
                assert rt._config.auth_key == "config-key"
                assert rt._config.auth_secret == "config-secret"

    def test_config_preserves_tuning_knobs(self):
        """Tuning knobs from config are preserved when using explicit connection params."""
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                cfg = AgentConfig(
                    server_url="http://config/api",
                    worker_thread_count=4,
                )
                rt = AgentRuntime(config=cfg, server_url="http://override/api")
                assert rt._config.server_url == "http://override/api"
                assert rt._config.worker_thread_count == 4


class TestAgentConfig:
    """Test AgentConfig dataclass loads from env via from_env()."""

    def test_defaults(self):
        from agentspan.agents.runtime.config import AgentConfig

        config = AgentConfig()
        assert config.server_url == "http://localhost:6767/api"
        assert config.llm_retry_count == 3
        assert config.worker_poll_interval_ms == 100

    def test_env_override(self):
        from unittest.mock import patch

        from agentspan.agents.runtime.config import AgentConfig

        with patch.dict(
            "os.environ", {"AGENTSPAN_SERVER_URL": "http://custom:9090/api"}, clear=True
        ):
            config = AgentConfig.from_env()
            assert config.server_url == "http://custom:9090/api"

    def test_custom_retry_count(self):
        from agentspan.agents.runtime.config import AgentConfig

        config = AgentConfig(llm_retry_count=5)
        assert config.llm_retry_count == 5


class TestCorrelationId:
    """Test that run() and start() generate a correlationId."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def test_run_generates_correlation_id(self, runtime):
        """Verify AgentResult.correlation_id is a valid UUID string."""
        agent = Agent(name="test", model="openai/gpt-4o")

        runtime._prepare_workers = MagicMock()
        runtime._start_via_server = MagicMock(return_value=("wf-123", None))
        runtime._poll_status_until_complete = MagicMock(
            return_value=AgentStatus(
                execution_id="wf-123",
                is_complete=True,
                output="Hello",
                status="COMPLETED",
            )
        )

        result = runtime.run(agent, "Hello")

        assert result.correlation_id is not None
        # Should be a valid UUID
        parsed = uuid.UUID(result.correlation_id)
        assert str(parsed) == result.correlation_id

    def test_start_generates_correlation_id(self, runtime):
        """Verify AgentHandle.correlation_id is set."""
        agent = Agent(name="test", model="openai/gpt-4o")

        runtime._prepare_workers = MagicMock()
        runtime._start_via_server = MagicMock(return_value=("wf-456", None))

        handle = runtime.start(agent, "Hello")

        assert handle.correlation_id is not None
        # Should be a valid UUID
        parsed = uuid.UUID(handle.correlation_id)
        assert str(parsed) == handle.correlation_id
        assert handle.execution_id == "wf-456"


class TestRuntimeRespond:
    """Test AgentRuntime.respond() calls update_task_sync."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def test_respond_calls_server_api(self, runtime):
        mock_post = _mock_requests_post()
        with patch("requests.post", mock_post):
            runtime.respond("wf-123", {"approved": True})

            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "/wf-123/respond" in call_args[0][0]
            assert call_args[1]["json"] == {"approved": True}

    def test_approve_delegates_to_respond(self, runtime):
        runtime.respond = MagicMock()
        runtime.approve("wf-123")
        runtime.respond.assert_called_once_with("wf-123", {"approved": True})

    def test_reject_delegates_to_respond(self, runtime):
        runtime.respond = MagicMock()
        runtime.reject("wf-123", reason="bad")
        runtime.respond.assert_called_once_with("wf-123", {"approved": False, "reason": "bad"})


class TestMediaParameter:
    """Test that the media parameter flows through runtime methods."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def test_run_passes_media_to_start_via_server(self, runtime):
        """Verify media URLs are passed to _start_via_server."""
        agent = Agent(name="test", model="openai/gpt-4o")

        runtime._prepare_workers = MagicMock()
        runtime._start_via_server = MagicMock(return_value=("wf-media", None))
        runtime._poll_status_until_complete = MagicMock(
            return_value=AgentStatus(
                execution_id="wf-media",
                is_complete=True,
                output="I see a cat",
                status="COMPLETED",
            )
        )

        result = runtime.run(
            agent,
            "Describe this image",
            media=["https://example.com/cat.jpg"],
        )

        call_kwargs = runtime._start_via_server.call_args
        assert call_kwargs[1]["media"] == ["https://example.com/cat.jpg"]
        # Output is normalized to a dict (BUG-P1-02 fix)
        assert result.output == {"result": "I see a cat"}

    def test_run_defaults_media_to_none(self, runtime):
        """Verify media defaults to None when not provided."""
        agent = Agent(name="test", model="openai/gpt-4o")

        runtime._prepare_workers = MagicMock()
        runtime._start_via_server = MagicMock(return_value=("wf-nomedia", None))
        runtime._poll_status_until_complete = MagicMock(
            return_value=AgentStatus(
                execution_id="wf-nomedia",
                is_complete=True,
                output="Hello",
                status="COMPLETED",
            )
        )

        runtime.run(agent, "Hello")

        call_kwargs = runtime._start_via_server.call_args
        assert call_kwargs[1]["media"] is None

    def test_start_passes_media_to_start_via_server(self, runtime):
        """Verify media URLs flow through start()."""
        agent = Agent(name="test", model="openai/gpt-4o")

        runtime._prepare_workers = MagicMock()
        runtime._start_via_server = MagicMock(return_value=("wf-media-start", None))

        handle = runtime.start(
            agent,
            "What's in this photo?",
            media=["https://example.com/photo.png", "https://example.com/photo2.png"],
        )

        call_kwargs = runtime._start_via_server.call_args
        assert call_kwargs[1]["media"] == [
            "https://example.com/photo.png",
            "https://example.com/photo2.png",
        ]
        assert handle.execution_id == "wf-media-start"


# ── Lifecycle methods ───────────────────────────────────────────────────


class TestRuntimeLifecycle:
    """Test shutdown, pause, resume, cancel, send_message, context manager."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def test_shutdown_stops_workers(self, runtime):
        runtime._workers_started = True
        runtime._worker_manager = MagicMock()
        runtime.shutdown()
        runtime._worker_manager.stop.assert_called_once()
        assert runtime._is_shutdown is True

    def test_shutdown_idempotent(self, runtime):
        runtime._workers_started = True
        runtime._worker_manager = MagicMock()
        runtime.shutdown()
        runtime.shutdown()  # second call is no-op
        runtime._worker_manager.stop.assert_called_once()

    def test_pause_delegates(self, runtime):
        runtime._workflow_client.pause_workflow = MagicMock()
        runtime.pause("wf-1")
        runtime._workflow_client.pause_workflow.assert_called_once_with("wf-1")

    def test_resume_delegates(self, runtime):
        runtime._workflow_client.resume_workflow = MagicMock()
        runtime.resume("wf-1")
        runtime._workflow_client.resume_workflow.assert_called_once_with("wf-1")

    def test_cancel_delegates(self, runtime):
        runtime._workflow_client.terminate_workflow = MagicMock()
        runtime.cancel("wf-1", reason="done")
        runtime._workflow_client.terminate_workflow.assert_called_once_with(
            execution_id="wf-1", reason="done"
        )

    def test_send_message_delegates(self, runtime):
        runtime.respond = MagicMock()
        runtime.send_message("wf-1", "hello")
        runtime.respond.assert_called_once_with("wf-1", {"message": "hello"})

    def test_context_manager(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                rt = AgentRuntime(config=config)
                rt._workers_started = True
                rt._worker_manager = MagicMock()

                with rt as r:
                    assert r is rt

                rt._worker_manager.stop.assert_called_once()


# ── _has_worker_tools ───────────────────────────────────────────────────


class TestHasWorkerTools:
    """Test _has_worker_tools() recursive check."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def test_no_tools_no_agents(self, runtime):
        agent = Agent(name="simple", model="openai/gpt-4o")
        assert runtime._has_worker_tools(agent) is False

    def test_with_worker_tool(self, runtime):
        from agentspan.agents.tool import tool

        @tool
        def my_tool(x: str) -> str:
            """Do something."""
            return x

        agent = Agent(name="tooled", model="openai/gpt-4o", tools=[my_tool])
        assert runtime._has_worker_tools(agent) is True

    def test_with_http_only(self, runtime):
        from agentspan.agents.tool import http_tool

        ht = http_tool(name="api", description="Call API", url="http://example.com", method="GET")
        agent = Agent(name="http_agent", model="openai/gpt-4o", tools=[ht])
        assert runtime._has_worker_tools(agent) is False

    def test_with_guardrails(self, runtime):
        from agentspan.agents.guardrail import Guardrail, GuardrailResult

        guard = Guardrail(func=lambda c: GuardrailResult(passed=True))
        agent = Agent(name="guarded", model="openai/gpt-4o", guardrails=[guard])
        assert runtime._has_worker_tools(agent) is True

    def test_recursive_subagent(self, runtime):
        from agentspan.agents.tool import tool

        @tool
        def inner_tool(x: str) -> str:
            """Inner."""
            return x

        sub = Agent(name="sub", model="openai/gpt-4o", tools=[inner_tool])
        parent = Agent(name="parent", model="openai/gpt-4o", agents=[sub])
        assert runtime._has_worker_tools(parent) is True


# ── _extract_token_usage ────────────────────────────────────────────────


class TestExtractTokenUsage:
    """Test _extract_token_usage() aggregation."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def test_single_llm_task(self, runtime):
        with patch.object(
            runtime,
            "_fetch_agent_workflow",
            return_value={
                "tokenUsage": {"promptTokens": 100, "completionTokens": 50, "totalTokens": 150}
            },
        ):
            usage = runtime._extract_token_usage("wf-123")
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150

    def test_multiple_llm_tasks(self, runtime):
        # Server pre-computes tokenUsage across all tasks; we return aggregated totals.
        with patch.object(
            runtime,
            "_fetch_agent_workflow",
            return_value={
                "tokenUsage": {"promptTokens": 300, "completionTokens": 150, "totalTokens": 450}
            },
        ):
            usage = runtime._extract_token_usage("wf-123")
        assert usage.prompt_tokens == 300
        assert usage.completion_tokens == 150
        assert usage.total_tokens == 450

    def test_no_llm_tasks(self, runtime):
        task = MagicMock()
        task.task_type = "SIMPLE"
        task.output_data = {}
        wf_run = MockWorkflowRun(tasks=[task])

        assert runtime._extract_token_usage(wf_run) is None

    def test_no_tasks(self, runtime):
        wf_run = MockWorkflowRun(tasks=[])
        assert runtime._extract_token_usage(wf_run) is None

    def test_computes_total_when_missing(self, runtime):
        with patch.object(
            runtime,
            "_fetch_agent_workflow",
            return_value={"tokenUsage": {"promptTokens": 100, "completionTokens": 50}},
        ):
            usage = runtime._extract_token_usage("wf-123")
        assert usage.total_tokens == 150


# ── _extract_tool_calls ─────────────────────────────────────────────────


class TestExtractToolCalls:
    """Test _extract_tool_calls() extraction."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def test_extracts_tool_tasks(self, runtime):
        task = MagicMock()
        task.task_type = "get_weather"
        task.reference_task_name = "call_abc123__0"
        task.input_data = {"city": "NYC"}
        task.output_data = {"temp": 72}
        wf_run = MockWorkflowRun(tasks=[task])

        calls = runtime._extract_tool_calls(wf_run)
        assert len(calls) == 1
        assert calls[0]["name"] == "get_weather"
        assert calls[0]["args"] == {"city": "NYC"}

    def test_empty_tasks(self, runtime):
        wf_run = MockWorkflowRun(tasks=[])
        assert runtime._extract_tool_calls(wf_run) == []

    def test_non_tool_tasks_ignored(self, runtime):
        task = MagicMock()
        task.task_type = "SIMPLE"
        wf_run = MockWorkflowRun(tasks=[task])
        assert runtime._extract_tool_calls(wf_run) == []


# ── get_status ──────────────────────────────────────────────────────────


class TestGetStatus:
    """Test get_status() method."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def _mock_status_response(self, runtime, response_json):
        """Patch requests.get to return a mock status response."""
        return patch(
            "requests.get",
            _mock_requests_get(response_json),
        )

    def test_completed(self, runtime):
        resp = {
            "status": "COMPLETED",
            "isComplete": True,
            "isRunning": False,
            "isWaiting": False,
            "output": "Done",
        }
        with self._mock_status_response(runtime, resp):
            status = runtime.get_status("wf-1")
        assert status.is_complete is True
        assert status.output == "Done"

    def test_running(self, runtime):
        resp = {
            "status": "RUNNING",
            "isComplete": False,
            "isRunning": True,
            "isWaiting": False,
            "output": None,
        }
        with self._mock_status_response(runtime, resp):
            status = runtime.get_status("wf-1")
        assert status.is_running is True
        assert status.is_complete is False

    def test_paused(self, runtime):
        resp = {
            "status": "PAUSED",
            "isComplete": False,
            "isRunning": False,
            "isWaiting": True,
            "output": None,
        }
        with self._mock_status_response(runtime, resp):
            status = runtime.get_status("wf-1")
        assert status.is_waiting is True

    def test_with_human_task(self, runtime):
        resp = {
            "status": "RUNNING",
            "isComplete": False,
            "isRunning": False,
            "isWaiting": True,
            "output": None,
            "pendingTool": {"tool_name": "approve_action", "parameters": {"x": 1}},
        }
        with self._mock_status_response(runtime, resp):
            status = runtime.get_status("wf-1")
        assert status.is_waiting is True
        assert status.pending_tool["tool_name"] == "approve_action"

    def test_failed(self, runtime):
        resp = {
            "status": "FAILED",
            "isComplete": True,
            "isRunning": False,
            "isWaiting": False,
            "output": None,
        }
        with self._mock_status_response(runtime, resp):
            status = runtime.get_status("wf-1")
        assert status.is_complete is True
        assert status.status == "FAILED"


# ── plan() ──────────────────────────────────────────────────────────────


class TestRuntimePlan:
    """Test plan() method."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def test_plan_returns_workflow_def(self, runtime):
        agent = Agent(name="test", model="openai/gpt-4o")
        mock_wf = MagicMock()
        mock_wf.to_workflow_def.return_value = {"name": "test_wf", "tasks": []}

        # plan() calls _compile_agent() which calls _compile_via_server() (HTTP)
        runtime._compile_agent = MagicMock(return_value=mock_wf)
        result = runtime.plan(agent)

        mock_wf.to_workflow_def.assert_called_once()
        runtime._compile_agent.assert_called_once_with(agent)

    def test_compile_via_server_wraps_config_in_start_request(self, runtime):
        """_compile_via_server sends agentConfig wrapped in a StartRequest payload."""
        agent = Agent(name="test", model="openai/gpt-4o", instructions="Be helpful.")

        mock_post = _mock_requests_post({"workflowDef": {"name": "test", "tasks": []}})
        with patch("requests.post", mock_post):
            runtime._compile_via_server(agent)

        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"]
        # The payload must wrap the config in {"agentConfig": ...}
        assert "agentConfig" in payload
        assert payload["agentConfig"]["name"] == "test"
        assert payload["agentConfig"]["model"] == "openai/gpt-4o"


# ── run() with guardrails ──────────────────────────────────────────────


class TestRuntimeRunGuardrails:
    """Test run() method guardrail paths."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def _setup_run(self, runtime, output="Hello", status="COMPLETED"):
        runtime._prepare_workers = MagicMock()
        runtime._start_via_server = MagicMock(return_value=("wf-guard", None))
        runtime._poll_status_until_complete = MagicMock(
            return_value=AgentStatus(
                execution_id="wf-guard",
                is_complete=True,
                output=output,
                status=status,
            )
        )

    def test_input_guardrail_raises(self, runtime):
        from agentspan.agents.guardrail import Guardrail, GuardrailResult

        guard = Guardrail(
            func=lambda c: GuardrailResult(passed=False, message="Bad input"),
            position="input",
            on_fail="raise",
        )
        agent = Agent(name="test", model="openai/gpt-4o", guardrails=[guard])
        self._setup_run(runtime)

        with pytest.raises(ValueError, match="Input guardrail"):
            runtime.run(agent, "bad prompt")

    def test_input_guardrail_passes(self, runtime):
        from agentspan.agents.guardrail import Guardrail, GuardrailResult

        guard = Guardrail(
            func=lambda c: GuardrailResult(passed=True),
            position="input",
            on_fail="raise",
        )
        agent = Agent(name="test", model="openai/gpt-4o", guardrails=[guard])
        self._setup_run(runtime)

        result = runtime.run(agent, "good prompt")
        assert result.output == {"result": "Hello"}

    def test_output_guardrail_compiled_single_execution(self, runtime):
        """All output guardrails now use compiled path (single workflow execution).

        Guardrail behavior (fix, retry, raise) happens inside the Conductor
        DoWhile loop, not client-side.  The runtime runs the workflow once.
        """
        from agentspan.agents.guardrail import Guardrail, GuardrailResult

        guard = Guardrail(
            func=lambda c: GuardrailResult(passed=False, message="PII", fixed_output="REDACTED"),
            position="output",
            on_fail="fix",
        )
        agent = Agent(name="test", model="openai/gpt-4o", guardrails=[guard])
        self._setup_run(runtime, output="workflow handled fix")

        result = runtime.run(agent, "show data")
        # Compiled path: workflow runs once, guardrails handled server-side
        assert result.output == {"result": "workflow handled fix"}
        runtime._start_via_server.assert_called_once()

    def test_output_guardrail_compiled_raise_returns_failed(self, runtime):
        """Output guardrail raise terminates workflow with FAILED status."""
        from agentspan.agents.guardrail import Guardrail, GuardrailResult

        guard = Guardrail(
            func=lambda c: GuardrailResult(passed=False, message="unsafe"),
            position="output",
            on_fail="raise",
        )
        agent = Agent(name="test", model="openai/gpt-4o", guardrails=[guard])
        self._setup_run(runtime, output="answer", status="FAILED")

        result = runtime.run(agent, "test")
        # Compiled raise -> workflow FAILED, single execution
        assert result.status == "FAILED"
        runtime._start_via_server.assert_called_once()

    def test_output_guardrail_retry_compiled_single_execution(self, runtime):
        """Output guardrail retry happens inside workflow (single execution)."""
        from agentspan.agents.guardrail import Guardrail, GuardrailResult

        guard = Guardrail(
            func=lambda c: GuardrailResult(passed=False, message="bad"),
            position="output",
            on_fail="retry",
            max_retries=3,
        )
        agent = Agent(name="test", model="openai/gpt-4o", guardrails=[guard])
        self._setup_run(runtime, output="retried answer")

        result = runtime.run(agent, "test")
        # Retries happen inside the workflow's DoWhile loop
        assert result.output == {"result": "retried answer"}
        runtime._start_via_server.assert_called_once()

    def test_run_with_compiled_output_guardrails(self, runtime):
        """Agent with tools + output guardrails uses compiled path (single execution)."""
        from agentspan.agents.guardrail import Guardrail, GuardrailResult
        from agentspan.agents.tool import tool

        @tool
        def my_tool(x: str) -> str:
            """A tool."""
            return x

        guard = Guardrail(
            func=lambda c: GuardrailResult(passed=True),
            position="output",
            on_fail="retry",
        )
        agent = Agent(
            name="test",
            model="openai/gpt-4o",
            tools=[my_tool],
            guardrails=[guard],
        )
        self._setup_run(runtime, output="tool answer")

        result = runtime.run(agent, "test")
        assert result.output == {"result": "tool answer"}
        # Compiled path: single execution (no retry loop)
        runtime._start_via_server.assert_called_once()

    def test_run_compiled_guardrail_failed_workflow(self, runtime):
        """Compiled guardrail path handles FAILED workflow status."""
        from agentspan.agents.guardrail import Guardrail, GuardrailResult
        from agentspan.agents.tool import tool

        @tool
        def my_tool(x: str) -> str:
            """A tool."""
            return x

        guard = Guardrail(
            func=lambda c: GuardrailResult(passed=True),
            position="output",
            on_fail="raise",
        )
        agent = Agent(
            name="test",
            model="openai/gpt-4o",
            tools=[my_tool],
            guardrails=[guard],
        )
        self._setup_run(runtime, output="partial", status="FAILED")

        result = runtime.run(agent, "test")
        assert result.status == "FAILED"

    def test_input_guardrail_fix_modifies_prompt(self, runtime):
        """Input guardrail with on_fail='fix' replaces the prompt."""
        from agentspan.agents.guardrail import Guardrail, GuardrailResult

        def sanitize_input(content):
            if "DROP TABLE" in content:
                return GuardrailResult(
                    passed=False,
                    message="SQL injection",
                    fixed_output="sanitized prompt",
                )
            return GuardrailResult(passed=True)

        guard = Guardrail(func=sanitize_input, position="input", on_fail="fix")
        agent = Agent(name="test", model="openai/gpt-4o", guardrails=[guard])
        self._setup_run(runtime, output="answer")

        result = runtime.run(agent, "SELECT * FROM users; DROP TABLE users")
        assert result.output == {"result": "answer"}
        # Verify the sanitized prompt was passed to _start_via_server
        call_args = runtime._start_via_server.call_args
        assert call_args is not None
        # The first positional arg after agent is the prompt
        assert call_args[0][1] == "sanitized prompt"

    def test_input_guardrail_retry_treated_as_raise(self, runtime):
        """Input guardrail with on_fail='retry' raises (retry not meaningful for input)."""
        from agentspan.agents.guardrail import Guardrail, GuardrailResult

        guard = Guardrail(
            func=lambda c: GuardrailResult(passed=False, message="bad"),
            position="input",
            on_fail="retry",
        )
        agent = Agent(name="test", model="openai/gpt-4o", guardrails=[guard])
        self._setup_run(runtime)

        with pytest.raises(ValueError, match="Input guardrail"):
            runtime.run(agent, "bad prompt")

    def test_input_guardrail_in_start(self, runtime):
        """Input guardrails also run in start() (async mode)."""
        from agentspan.agents.guardrail import Guardrail, GuardrailResult

        guard = Guardrail(
            func=lambda c: GuardrailResult(passed=False, message="Blocked"),
            position="input",
            on_fail="raise",
        )
        agent = Agent(name="test", model="openai/gpt-4o", guardrails=[guard])

        runtime._prepare_workers = MagicMock()
        runtime._start_via_server = MagicMock(return_value=("wf-123", None))

        with pytest.raises(ValueError, match="Input guardrail"):
            runtime.start(agent, "bad prompt")


class TestRunPopulatesToolCalls:
    """Regression tests for BUG-P1-01: run() must populate tool_calls, messages, token_usage."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def test_run_populates_tool_calls(self, runtime):
        """run() fetches workflow execution and populates tool_calls."""
        agent = Agent(name="test", model="openai/gpt-4o")

        runtime._prepare_workers = MagicMock()
        runtime._start_via_server = MagicMock(return_value=("wf-tools", None))
        runtime._poll_status_until_complete = MagicMock(
            return_value=AgentStatus(
                execution_id="wf-tools",
                is_complete=True,
                output={"result": "done", "finishReason": "STOP"},
                status="COMPLETED",
            )
        )

        # Mock workflow with tool tasks (for _extract_tool_calls via _workflow_client)
        tool_task = MagicMock()
        tool_task.task_type = "get_weather"
        tool_task.reference_task_name = "call_abc123__0"
        tool_task.input_data = {"city": "NYC"}
        tool_task.output_data = {"temp": 72}

        wf = MagicMock()
        wf.tasks = [tool_task]
        wf.variables = {"messages": [{"role": "user", "content": "hi"}]}
        runtime._workflow_client.get_workflow = MagicMock(return_value=wf)

        # Mock _fetch_agent_workflow for _extract_token_usage (new HTTP-based API)
        with patch.object(
            runtime,
            "_fetch_agent_workflow",
            return_value={
                "tokenUsage": {"promptTokens": 100, "completionTokens": 50, "totalTokens": 150},
                "tasks": [],
            },
        ):
            result = runtime.run(agent, "What's the weather?")

        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "get_weather"
        assert result.token_usage is not None
        assert result.token_usage.total_tokens == 150
        assert len(result.messages) > 0

    def test_run_without_tool_calls(self, runtime):
        """run() works when workflow has no tool tasks."""
        agent = Agent(name="test", model="openai/gpt-4o")

        runtime._prepare_workers = MagicMock()
        runtime._start_via_server = MagicMock(return_value=("wf-notool", None))
        runtime._poll_status_until_complete = MagicMock(
            return_value=AgentStatus(
                execution_id="wf-notool",
                is_complete=True,
                output={"result": "Hello!", "finishReason": "STOP"},
                status="COMPLETED",
            )
        )

        wf = MagicMock()
        wf.tasks = []
        wf.variables = {}
        runtime._workflow_client.get_workflow = MagicMock(return_value=wf)

        result = runtime.run(agent, "Hi")

        assert result.tool_calls == []
        assert result.token_usage is None


class TestHasWorkerTools:
    """Test _has_worker_tools with different guardrail types."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                rt = AgentRuntime(config=config)
                yield rt

    def test_regex_guardrail_only_no_workers(self, runtime):
        """RegexGuardrail compiles to InlineTask — no workers needed."""
        from agentspan.agents.guardrail import RegexGuardrail

        agent = Agent(
            name="test",
            model="openai/gpt-4o",
            guardrails=[RegexGuardrail(patterns=[r"\d+"], name="digits")],
        )
        assert runtime._has_worker_tools(agent) is False

    def test_external_guardrail_only_no_workers(self, runtime):
        """External guardrails compile to SimpleTask — no local workers needed."""
        from agentspan.agents.guardrail import Guardrail

        agent = Agent(
            name="test",
            model="openai/gpt-4o",
            guardrails=[Guardrail(name="remote_check", on_fail="retry")],
        )
        assert runtime._has_worker_tools(agent) is False

    def test_custom_guardrail_needs_workers(self, runtime):
        """Custom function guardrails compile to worker tasks — workers needed."""
        from agentspan.agents.guardrail import Guardrail, GuardrailResult

        agent = Agent(
            name="test",
            model="openai/gpt-4o",
            guardrails=[
                Guardrail(
                    func=lambda c: GuardrailResult(passed=True),
                    on_fail="retry",
                )
            ],
        )
        assert runtime._has_worker_tools(agent) is True

    def test_llm_guardrail_no_workers(self, runtime):
        """LLMGuardrail compiles to server-side LlmChatComplete — no workers needed."""
        from agentspan.agents.guardrail import LLMGuardrail

        agent = Agent(
            name="test",
            model="openai/gpt-4o",
            guardrails=[LLMGuardrail(model="openai/gpt-4o-mini", policy="be safe")],
        )
        assert runtime._has_worker_tools(agent) is False

    def test_mixed_regex_and_custom_needs_workers(self, runtime):
        """Mix of regex + custom guardrails — needs workers for the custom one."""
        from agentspan.agents.guardrail import Guardrail, GuardrailResult, RegexGuardrail

        agent = Agent(
            name="test",
            model="openai/gpt-4o",
            guardrails=[
                RegexGuardrail(patterns=[r"\d+"], name="digits"),
                Guardrail(func=lambda c: GuardrailResult(passed=True), on_fail="retry"),
            ],
        )
        assert runtime._has_worker_tools(agent) is True

    def test_no_guardrails_no_tools_no_workers(self, runtime):
        """Agent with no guardrails and no tools doesn't need workers."""
        agent = Agent(name="test", model="openai/gpt-4o")
        assert runtime._has_worker_tools(agent) is False


# ── stream() ────────────────────────────────────────────────────────────


class TestRuntimeStream:
    """Test stream() method event generation."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def test_stream_yields_done_on_completion(self, runtime):
        agent = Agent(name="test", model="openai/gpt-4o")

        # Mock start() internals
        runtime._prepare_workers = MagicMock()
        runtime._start_via_server = MagicMock(return_value=("wf-stream-1", None))

        # Mock get_workflow to return completed on first poll
        completed_wf = MagicMock()
        completed_wf.status = "COMPLETED"
        completed_wf.tasks = []
        completed_wf.output = {"result": "Final answer"}
        runtime._workflow_client.get_workflow = MagicMock(return_value=completed_wf)

        events = list(runtime.stream(agent, "Hello"))
        done_events = [e for e in events if e.type == EventType.DONE]
        assert len(done_events) == 1
        assert done_events[0].output == "Final answer"

    def test_stream_yields_thinking_event(self, runtime):
        agent = Agent(name="test", model="openai/gpt-4o")

        runtime._prepare_workers = MagicMock()
        runtime._start_via_server = MagicMock(return_value=("wf-stream-2", None))

        # First poll: LLM task running
        running_wf = MagicMock()
        running_wf.status = "RUNNING"
        llm_task = MagicMock()
        llm_task.task_id = "t1"
        llm_task.task_type = "LLM_CHAT_COMPLETE"
        llm_task.reference_task_name = "test_llm"
        llm_task.status = "IN_PROGRESS"
        llm_task.output_data = {}
        running_wf.tasks = [llm_task]

        # Second poll: completed
        completed_wf = MagicMock()
        completed_wf.status = "COMPLETED"
        completed_wf.tasks = [llm_task]
        completed_wf.output = {"result": "done"}

        runtime._workflow_client.get_workflow = MagicMock(side_effect=[running_wf, completed_wf])

        with patch("time.sleep"):
            events = list(runtime.stream(agent, "Hello"))

        thinking = [e for e in events if e.type == EventType.THINKING]
        assert len(thinking) == 1

    def test_stream_yields_error_on_failure(self, runtime):
        agent = Agent(name="test", model="openai/gpt-4o")

        runtime._prepare_workers = MagicMock()
        runtime._start_via_server = MagicMock(return_value=("wf-stream-err", None))

        failed_wf = MagicMock()
        failed_wf.status = "FAILED"
        failed_wf.tasks = []
        failed_wf.output = None
        runtime._workflow_client.get_workflow = MagicMock(return_value=failed_wf)

        events = list(runtime.stream(agent, "Hello"))
        error_events = [e for e in events if e.type == EventType.ERROR]
        assert len(error_events) == 1
        assert "FAILED" in error_events[0].content

    def test_stream_yields_waiting_on_paused(self, runtime):
        agent = Agent(name="test", model="openai/gpt-4o")

        runtime._prepare_workers = MagicMock()
        runtime._start_via_server = MagicMock(return_value=("wf-stream-wait", None))

        # First poll: paused
        paused_wf = MagicMock()
        paused_wf.status = "PAUSED"
        paused_wf.tasks = []

        # Second poll: completed
        completed_wf = MagicMock()
        completed_wf.status = "COMPLETED"
        completed_wf.tasks = []
        completed_wf.output = {"result": "resumed"}

        runtime._workflow_client.get_workflow = MagicMock(side_effect=[paused_wf, completed_wf])

        with patch("time.sleep"):
            events = list(runtime.stream(agent, "Hello"))

        waiting = [e for e in events if e.type == EventType.WAITING]
        assert len(waiting) == 1

    def test_stream_yields_error_on_fetch_exception(self, runtime):
        agent = Agent(name="test", model="openai/gpt-4o")

        runtime._prepare_workers = MagicMock()
        runtime._start_via_server = MagicMock(return_value=("wf-stream-exc", None))

        runtime._workflow_client.get_workflow = MagicMock(
            side_effect=RuntimeError("connection lost")
        )

        events = list(runtime.stream(agent, "Hello"))
        error_events = [e for e in events if e.type == EventType.ERROR]
        assert len(error_events) == 1
        assert "connection lost" in error_events[0].content

    def test_stream_yields_tool_call_and_result(self, runtime):
        agent = Agent(name="test", model="openai/gpt-4o")

        runtime._prepare_workers = MagicMock()
        runtime._start_via_server = MagicMock(return_value=("wf-stream-tool", None))

        # Create a dispatch task with function field
        dispatch_task = MagicMock()
        dispatch_task.task_id = "t-dispatch"
        dispatch_task.task_type = "SIMPLE"
        dispatch_task.reference_task_name = "test_dispatch"
        dispatch_task.status = "COMPLETED"
        dispatch_task.output_data = {
            "function": "get_weather",
            "parameters": {"city": "NYC"},
            "result": "72F",
        }

        completed_wf = MagicMock()
        completed_wf.status = "COMPLETED"
        completed_wf.tasks = [dispatch_task]
        completed_wf.output = {"result": "It's 72F in NYC"}

        runtime._workflow_client.get_workflow = MagicMock(return_value=completed_wf)

        events = list(runtime.stream(agent, "Hello"))
        tool_calls = [e for e in events if e.type == EventType.TOOL_CALL]
        tool_results = [e for e in events if e.type == EventType.TOOL_RESULT]
        assert len(tool_calls) == 1
        assert tool_calls[0].tool_name == "get_weather"
        assert len(tool_results) == 1

    def test_stream_yields_handoff(self, runtime):
        agent = Agent(name="test", model="openai/gpt-4o")

        runtime._prepare_workers = MagicMock()
        runtime._start_via_server = MagicMock(return_value=("wf-stream-handoff", None))

        sub_task = MagicMock()
        sub_task.task_id = "t-sub"
        sub_task.task_type = "SUB_WORKFLOW"
        sub_task.reference_task_name = "test_handoff_agent_b"
        sub_task.status = "IN_PROGRESS"
        sub_task.output_data = {}

        completed_wf = MagicMock()
        completed_wf.status = "COMPLETED"
        completed_wf.tasks = [sub_task]
        completed_wf.output = {"result": "answer from b"}

        runtime._workflow_client.get_workflow = MagicMock(return_value=completed_wf)

        events = list(runtime.stream(agent, "Hello"))
        handoffs = [e for e in events if e.type == EventType.HANDOFF]
        assert len(handoffs) == 1
        assert handoffs[0].target == "agent_b"


# ── Structured output extraction ──────────────────────────────────────


class TestExtractStructuredOutput:
    """Test _extract_output with output_type parsing."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def test_extract_output_with_output_type_from_dict(self, runtime):
        from dataclasses import dataclass

        @dataclass
        class Weather:
            city: str
            temp: int

        agent = Agent(name="test", model="openai/gpt-4o", output_type=Weather)
        wf_run = MockWorkflowRun(output={"result": {"city": "NYC", "temp": 72}})

        output = runtime._extract_output(wf_run, agent)
        assert isinstance(output, Weather)
        assert output.city == "NYC"
        assert output.temp == 72

    def test_extract_output_with_output_type_from_json_string(self, runtime):
        import json
        from dataclasses import dataclass

        @dataclass
        class Weather:
            city: str
            temp: int

        agent = Agent(name="test", model="openai/gpt-4o", output_type=Weather)
        wf_run = MockWorkflowRun(output={"result": json.dumps({"city": "LA", "temp": 85})})

        output = runtime._extract_output(wf_run, agent)
        assert isinstance(output, Weather)
        assert output.city == "LA"

    def test_extract_output_with_output_type_fallback(self, runtime):
        """When structured parsing fails, returns raw result."""
        from dataclasses import dataclass

        @dataclass
        class Strict:
            x: int
            y: int

        agent = Agent(name="test", model="openai/gpt-4o", output_type=Strict)
        wf_run = MockWorkflowRun(output={"result": "not valid json or dict"})

        output = runtime._extract_output(wf_run, agent)
        assert output == "not valid json or dict"

    def test_extract_output_non_dict_output(self, runtime):
        """Non-dict workflow output is returned as-is."""
        agent = Agent(name="test", model="openai/gpt-4o")
        wf_run = MockWorkflowRun(output="raw string output")
        output = runtime._extract_output(wf_run, agent)
        assert output == "raw string output"


# ── Token usage edge cases ────────────────────────────────────────────


class TestExtractTokenUsageEdgeCases:
    """Additional token usage edge cases."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def test_non_dict_token_usage_skipped(self, runtime):
        """Non-dict tokenUsed value should be skipped."""
        task = MagicMock()
        task.task_type = "LLM_CHAT_COMPLETE"
        task.output_data = {"tokenUsed": "not a dict"}
        wf_run = MockWorkflowRun(tasks=[task])

        assert runtime._extract_token_usage(wf_run) is None


# ── get_status edge cases ─────────────────────────────────────────────


class TestGetStatusEdgeCases:
    """Additional get_status edge cases."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def test_completed_non_dict_output(self, runtime):
        """Non-dict output in completed workflow is returned as-is."""
        resp = {
            "status": "COMPLETED",
            "isComplete": True,
            "isRunning": False,
            "isWaiting": False,
            "output": "raw output",
        }
        with patch(
            "requests.get",
            _mock_requests_get(resp),
        ):
            status = runtime.get_status("wf-1")
        assert status.is_complete is True
        assert status.output == "raw output"


# ── _has_worker_tools edge cases ──────────────────────────────────────


class TestHasWorkerToolsEdgeCases:
    """Additional _has_worker_tools edge cases."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def test_with_handoffs(self, runtime):
        from agentspan.agents.handoff import OnTextMention

        handoff = OnTextMention(target=Agent(name="sub", model="openai/gpt-4o"), text="help")
        agent = Agent(name="parent", model="openai/gpt-4o", handoffs=[handoff])
        assert runtime._has_worker_tools(agent) is True

    def test_manual_strategy(self, runtime):
        sub = Agent(name="sub", model="openai/gpt-4o")
        agent = Agent(name="parent", model="openai/gpt-4o", agents=[sub], strategy="manual")
        assert runtime._has_worker_tools(agent) is True

    def test_malformed_tool_skipped(self, runtime):
        """A non-tool object in tools list is skipped without crashing."""
        agent = Agent(name="test", model="openai/gpt-4o", tools=["not_a_tool"])
        # Should not crash — returns False since no valid worker tools
        assert runtime._has_worker_tools(agent) is False


# ── Workflow execution fallback ──────────────────────────────────────


class TestStartViaServer:
    """Test _start_via_server() sends correct payload to the server API."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080")
                return AgentRuntime(config=config)

    def test_start_via_server_returns_execution_id(self, runtime):
        """_start_via_server returns (executionId, requiredWorkers) tuple."""
        agent = Agent(name="test", model="openai/gpt-4o")

        with patch("requests.post", _mock_requests_post({"executionId": "wf-server-1"})):
            exec_id, required_workers = runtime._start_via_server(agent, "hello")

        assert exec_id == "wf-server-1"
        assert required_workers is None

    def test_start_via_server_returns_required_workers(self, runtime):
        """_start_via_server extracts requiredWorkers from server response."""
        agent = Agent(name="test", model="openai/gpt-4o")

        resp = {"executionId": "wf-server-2", "requiredWorkers": ["agent_termination", "my_tool"]}
        with patch("requests.post", _mock_requests_post(resp)):
            exec_id, required_workers = runtime._start_via_server(agent, "hello")

        assert exec_id == "wf-server-2"
        assert required_workers == {"agent_termination", "my_tool"}

    def test_start_via_server_sends_prompt(self, runtime):
        """_start_via_server includes the prompt in the payload."""
        agent = Agent(name="test", model="openai/gpt-4o")

        mock_post = _mock_requests_post({"executionId": "wf-1"})
        with patch("requests.post", mock_post):
            runtime._start_via_server(agent, "test prompt")

        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"]
        assert payload["prompt"] == "test prompt"

    def test_start_via_server_passes_media(self, runtime):
        """_start_via_server includes media in the payload."""
        agent = Agent(name="test", model="openai/gpt-4o")

        mock_post = _mock_requests_post({"executionId": "wf-1"})
        with patch("requests.post", mock_post):
            runtime._start_via_server(agent, "describe", media=["https://img.png"])

        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"]
        assert payload["media"] == ["https://img.png"]

    def test_start_via_server_passes_idempotency_key(self, runtime):
        """Idempotency key is included in the payload when provided."""
        agent = Agent(name="test", model="openai/gpt-4o")

        mock_post = _mock_requests_post({"executionId": "wf-1"})
        with patch("requests.post", mock_post):
            runtime._start_via_server(agent, "hi", idempotency_key="idem-123")

        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"]
        assert payload["idempotencyKey"] == "idem-123"

    def test_start_via_server_omits_idempotency_key_when_none(self, runtime):
        """Idempotency key is not in the payload when not provided."""
        agent = Agent(name="test", model="openai/gpt-4o")

        mock_post = _mock_requests_post({"executionId": "wf-1"})
        with patch("requests.post", mock_post):
            runtime._start_via_server(agent, "hi")

        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"]
        assert "idempotencyKey" not in payload


class TestStartFrameworkViaServer:
    """Test _start_framework_via_server() sends correct framework payloads."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080")
                return AgentRuntime(config=config)

    def test_start_framework_via_server_passes_credentials(self, runtime):
        """Framework start payload includes request-level credentials."""
        mock_post = _mock_requests_post({"executionId": "wf-fw-1"})
        with patch("requests.post", mock_post):
            runtime._start_framework_via_server(
                framework="openai",
                raw_config={"name": "fw_agent"},
                prompt="hello",
                credentials=["OPENAI_API_KEY"],
            )

        payload = mock_post.call_args[1]["json"]
        assert payload["credentials"] == ["OPENAI_API_KEY"]


class TestFrameworkCredentials:
    """Test request-scoped credential handling for framework agents."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080")
                return AgentRuntime(config=config)

    def test_run_framework_registers_and_clears_workflow_credentials(self, runtime):
        """Framework run() exposes request credentials to extracted tools for the run lifetime."""
        from agentspan.agents.runtime._dispatch import (
            _workflow_credentials,
            _workflow_credentials_lock,
        )

        fake_framework_agent = object()

        def _status_with_registry_check(execution_id, timeout=None):
            with _workflow_credentials_lock:
                assert _workflow_credentials[execution_id] == ["FW_API_KEY"]
            return AgentStatus(
                execution_id=execution_id,
                is_complete=True,
                status="COMPLETED",
                output={"result": "ok"},
            )

        with patch("agentspan.agents.frameworks.serializer.detect_framework", return_value="openai"):
            with patch(
                "agentspan.agents.frameworks.serializer.serialize_agent",
                return_value=({"name": "fw_agent"}, []),
            ):
                with patch.object(
                    runtime, "_start_framework_via_server", return_value="wf-framework-1"
                ) as mock_start:
                    with patch.object(
                        runtime,
                        "_poll_status_until_complete",
                        side_effect=_status_with_registry_check,
                    ):
                        with patch.object(runtime, "_extract_token_usage", return_value=None):
                            result = runtime.run(
                                fake_framework_agent,
                                "hello",
                                credentials=["FW_API_KEY"],
                            )

        assert result.execution_id == "wf-framework-1"
        assert mock_start.call_args.kwargs["credentials"] == ["FW_API_KEY"]
        with _workflow_credentials_lock:
            assert "wf-framework-1" not in _workflow_credentials


class TestPollStatusUntilComplete:
    """Test _poll_status_until_complete() polling logic."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080")
                return AgentRuntime(config=config)

    @patch("agentspan.agents.runtime.runtime.time.sleep", return_value=None)
    def test_returns_on_completed(self, mock_sleep, runtime):
        """Returns immediately when workflow is COMPLETED."""
        completed = AgentStatus(
            execution_id="wf-1",
            is_complete=True,
            status="COMPLETED",
            output="done",
        )
        runtime.get_status = MagicMock(return_value=completed)

        result = runtime._poll_status_until_complete("wf-1")

        assert result.is_complete is True
        assert result.status == "COMPLETED"
        mock_sleep.assert_not_called()

    @patch("agentspan.agents.runtime.runtime.time.sleep", return_value=None)
    def test_returns_on_failed(self, mock_sleep, runtime):
        """Returns immediately when workflow is FAILED."""
        failed = AgentStatus(
            execution_id="wf-1",
            is_complete=True,
            status="FAILED",
        )
        runtime.get_status = MagicMock(return_value=failed)

        result = runtime._poll_status_until_complete("wf-1")

        assert result.status == "FAILED"
        assert result.is_complete is True

    @patch("agentspan.agents.runtime.runtime.time.sleep", return_value=None)
    def test_returns_on_terminated(self, mock_sleep, runtime):
        """Returns when workflow is TERMINATED."""
        terminated = AgentStatus(
            execution_id="wf-1",
            is_complete=True,
            status="TERMINATED",
        )
        runtime.get_status = MagicMock(return_value=terminated)

        result = runtime._poll_status_until_complete("wf-1")
        assert result.status == "TERMINATED"

    @patch("agentspan.agents.runtime.runtime.time.sleep", return_value=None)
    def test_polls_until_complete(self, mock_sleep, runtime):
        """Polls multiple times until workflow reaches terminal state."""
        running = AgentStatus(
            execution_id="wf-1",
            is_complete=False,
            is_running=True,
            status="RUNNING",
        )
        completed = AgentStatus(
            execution_id="wf-1",
            is_complete=True,
            status="COMPLETED",
            output="done",
        )

        runtime.get_status = MagicMock(
            side_effect=[running, running, completed],
        )

        result = runtime._poll_status_until_complete("wf-1")

        assert result.is_complete is True
        assert runtime.get_status.call_count == 3
        assert mock_sleep.call_count == 2  # slept twice while RUNNING

    @patch("agentspan.agents.runtime.runtime.time.sleep", return_value=None)
    def test_timeout_returns_current_state(self, mock_sleep, runtime):
        """When poll times out, returns current workflow state."""
        running = AgentStatus(
            execution_id="wf-1",
            is_complete=False,
            is_running=True,
            status="RUNNING",
        )
        runtime.get_status = MagicMock(return_value=running)

        result = runtime._poll_status_until_complete("wf-1", timeout=5)

        # Should have polled for ~5 iterations (timeout=5s, interval=1s)
        assert runtime.get_status.call_count >= 5
        assert result.status == "RUNNING"  # returned incomplete

    @patch("agentspan.agents.runtime.runtime.time.sleep", return_value=None)
    def test_returns_on_timed_out_status(self, mock_sleep, runtime):
        """TIMED_OUT is a terminal state."""
        timed_out = AgentStatus(
            execution_id="wf-1",
            is_complete=True,
            status="TIMED_OUT",
        )
        runtime.get_status = MagicMock(return_value=timed_out)

        result = runtime._poll_status_until_complete("wf-1")
        assert result.status == "TIMED_OUT"
        mock_sleep.assert_not_called()


# ── Prompt template resolution ───────────────────────────────────────


class TestResolvePrompt:
    """Test _resolve_prompt() for PromptTemplate and string prompts."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients") as MockClients:
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                mock_clients = MagicMock()
                MockClients.return_value = mock_clients

                mock_prompt_client = MagicMock()
                mock_clients.get_prompt_client.return_value = mock_prompt_client

                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                rt = AgentRuntime(config=config)
                return rt, mock_prompt_client

    def test_string_passthrough(self, runtime):
        """Plain string prompt is returned as-is."""
        rt, _ = runtime
        assert rt._resolve_prompt("Hello world") == "Hello world"

    def test_template_resolved(self, runtime):
        """PromptTemplate fetches and substitutes variables."""
        from agentspan.agents.agent import PromptTemplate

        rt, mock_prompt = runtime

        mock_template = MagicMock()
        mock_template.template = "Analyze ${topic} for ${company}"
        mock_prompt.get_prompt.return_value = mock_template

        result = rt._resolve_prompt(
            PromptTemplate("analysis-prompt", variables={"topic": "revenue", "company": "Acme"})
        )

        assert result == "Analyze revenue for Acme"
        mock_prompt.get_prompt.assert_called_once_with("analysis-prompt")

    def test_template_not_found_raises(self, runtime):
        """Missing template raises ValueError."""
        from agentspan.agents.agent import PromptTemplate

        rt, mock_prompt = runtime
        mock_prompt.get_prompt.return_value = None

        with pytest.raises(ValueError, match="not found"):
            rt._resolve_prompt(PromptTemplate("nonexistent"))

    def test_template_no_variables(self, runtime):
        """Template with no variables returns template text as-is."""
        from agentspan.agents.agent import PromptTemplate

        rt, mock_prompt = runtime

        mock_template = MagicMock()
        mock_template.template = "You are a helpful assistant."
        mock_prompt.get_prompt.return_value = mock_template

        result = rt._resolve_prompt(PromptTemplate("simple-prompt"))
        assert result == "You are a helpful assistant."

    def test_prompt_client_lazy_init(self, runtime):
        """Prompt client is lazily initialized on first template use."""
        from agentspan.agents.agent import PromptTemplate

        rt, mock_prompt = runtime
        assert rt._prompt_client_instance is None

        mock_template = MagicMock()
        mock_template.template = "test"
        mock_prompt.get_prompt.return_value = mock_template

        rt._resolve_prompt(PromptTemplate("test"))
        assert rt._prompt_client_instance is not None


class TestAssociateTemplatesWithModels:
    """Test _associate_templates_with_models() auto-association."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients") as MockClients:
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                mock_clients = MagicMock()
                MockClients.return_value = mock_clients

                mock_prompt_client = MagicMock()
                mock_clients.get_prompt_client.return_value = mock_prompt_client

                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                rt = AgentRuntime(config=config)
                return rt, mock_prompt_client

    def test_associates_template_with_model(self, runtime):
        """Template is re-saved with model association."""
        from agentspan.agents.agent import PromptTemplate

        rt, mock_prompt = runtime

        mock_template = MagicMock()
        mock_template.template = "You are helpful."
        mock_template.integrations = []
        mock_template.description = "Test prompt"
        mock_prompt.get_prompt.return_value = mock_template

        agent = Agent(
            name="test",
            model="openai/gpt-4o",
            instructions=PromptTemplate("my-prompt"),
        )
        rt._associate_templates_with_models(agent)

        mock_prompt.save_prompt.assert_called_once()
        call_kwargs = mock_prompt.save_prompt.call_args
        assert "openai:gpt-4o" in call_kwargs[1]["models"]

    def test_skips_already_associated(self, runtime):
        """Does not re-save if model is already associated."""
        from agentspan.agents.agent import PromptTemplate

        rt, mock_prompt = runtime

        mock_template = MagicMock()
        mock_template.template = "Hello"
        mock_template.integrations = ["openai:gpt-4o"]
        mock_prompt.get_prompt.return_value = mock_template

        agent = Agent(
            name="test",
            model="openai/gpt-4o",
            instructions=PromptTemplate("my-prompt"),
        )
        rt._associate_templates_with_models(agent)

        mock_prompt.save_prompt.assert_not_called()

    def test_skips_inline_instructions(self, runtime):
        """Agents with string instructions are ignored."""
        rt, mock_prompt = runtime

        agent = Agent(name="test", model="openai/gpt-4o", instructions="You are helpful.")
        rt._associate_templates_with_models(agent)

        mock_prompt.get_prompt.assert_not_called()

    def test_walks_agent_tree(self, runtime):
        """Templates from sub-agents are also associated."""
        from agentspan.agents.agent import PromptTemplate

        rt, mock_prompt = runtime

        mock_template = MagicMock()
        mock_template.template = "Template text"
        mock_template.integrations = []
        mock_template.description = "Desc"
        mock_prompt.get_prompt.return_value = mock_template

        sub = Agent(
            name="sub",
            model="anthropic/claude-sonnet-4-20250514",
            instructions=PromptTemplate("sub-prompt"),
        )
        parent = Agent(
            name="parent",
            model="openai/gpt-4o",
            instructions=PromptTemplate("parent-prompt"),
            agents=[sub],
            strategy="handoff",
        )
        rt._associate_templates_with_models(parent)

        # Both templates should be fetched
        assert mock_prompt.get_prompt.call_count == 2

    def test_handles_exception_gracefully(self, runtime):
        """Exceptions during association are logged, not raised."""
        from agentspan.agents.agent import PromptTemplate

        rt, mock_prompt = runtime
        mock_prompt.get_prompt.side_effect = Exception("Connection error")

        agent = Agent(
            name="test",
            model="openai/gpt-4o",
            instructions=PromptTemplate("my-prompt"),
        )
        # Should not raise
        rt._associate_templates_with_models(agent)


class TestDeriveFinishReason:
    """Test _derive_finish_reason static method."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients") as MockClients:
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                mock_clients = MagicMock()
                MockClients.return_value = mock_clients
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def test_rejected_finish_reason(self, runtime):
        """COMPLETED with finishReason=rejected maps to FinishReason.REJECTED."""
        from agentspan.agents.result import FinishReason

        result = runtime._derive_finish_reason("COMPLETED", {"finishReason": "rejected"})
        assert result == FinishReason.REJECTED

    def test_stop_finish_reason(self, runtime):
        from agentspan.agents.result import FinishReason

        result = runtime._derive_finish_reason("COMPLETED", {"finishReason": "STOP"})
        assert result == FinishReason.STOP

    def test_length_finish_reason(self, runtime):
        from agentspan.agents.result import FinishReason

        result = runtime._derive_finish_reason("COMPLETED", {"finishReason": "LENGTH"})
        assert result == FinishReason.LENGTH


class TestNormalizeOutput:
    """Test _normalize_output static method."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients") as MockClients:
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                mock_clients = MagicMock()
                MockClients.return_value = mock_clients
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def test_rejected_output_preserved(self, runtime):
        """Rejection output with finishReason=rejected is kept as-is."""
        output = {"finishReason": "rejected", "rejectionReason": "Not allowed"}
        result = runtime._normalize_output(output, "COMPLETED")
        assert result == output
        assert result["finishReason"] == "rejected"

    def test_dict_output_preserved(self, runtime):
        result = runtime._normalize_output({"result": "ok"}, "COMPLETED")
        assert result == {"result": "ok"}

    def test_string_output_wrapped(self, runtime):
        result = runtime._normalize_output("hello", "COMPLETED")
        assert result == {"result": "hello"}

    def test_server_normalized_parallel_output_passthrough(self, runtime):
        """Server-normalized parallel output is passed through as-is."""
        output = {
            "result": "[agent_a]: Answer A\n\n[agent_b]: Answer B",
            "subResults": {"agent_a": "Answer A", "agent_b": "Answer B"},
        }
        result = runtime._normalize_output(output, "COMPLETED")
        assert result == output  # no SDK-side transformation


class TestExtractSubResults:
    """Test _extract_sub_results static method."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients") as MockClients:
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                mock_clients = MagicMock()
                MockClients.return_value = mock_clients
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def test_extracts_sub_results_from_server_output(self, runtime):
        output = {"result": "joined text", "subResults": {"a": "X", "b": "Y"}}
        assert runtime._extract_sub_results(output) == {"a": "X", "b": "Y"}

    def test_returns_empty_dict_when_no_sub_results(self, runtime):
        output = {"result": "simple text"}
        assert runtime._extract_sub_results(output) == {}

    def test_returns_empty_dict_for_non_dict(self, runtime):
        assert runtime._extract_sub_results("not a dict") == {}


class TestInjectSessionMemory:
    """Test _inject_session_memory static method."""

    def test_injects_messages_into_empty_memory(self):
        from agentspan.agents.runtime.runtime import AgentRuntime

        agent = Agent(name="test", model="openai/gpt-4o")
        prior = [{"role": "user", "message": "Hi"}, {"role": "assistant", "message": "Hello"}]

        result = AgentRuntime._inject_session_memory(agent, prior)

        assert result is not agent  # shallow copy
        assert result.memory is not None
        assert len(result.memory.messages) == 2
        assert result.memory.messages[0]["message"] == "Hi"

    def test_prepends_to_existing_memory(self):
        from agentspan.agents.memory import ConversationMemory
        from agentspan.agents.runtime.runtime import AgentRuntime

        existing_messages = [{"role": "system", "message": "You are helpful"}]
        agent = Agent(
            name="test",
            model="openai/gpt-4o",
            memory=ConversationMemory(messages=existing_messages),
        )
        prior = [{"role": "user", "message": "Hi"}]

        result = AgentRuntime._inject_session_memory(agent, prior)

        assert len(result.memory.messages) == 2
        assert result.memory.messages[0]["role"] == "user"
        assert result.memory.messages[1]["role"] == "system"


class TestRequiredToolsAgent:
    """Test that required_tools parameter works on Agent."""

    def test_required_tools_default_empty(self):
        agent = Agent(name="test", model="openai/gpt-4o")
        assert agent.required_tools == []

    def test_required_tools_set(self):
        agent = Agent(name="test", model="openai/gpt-4o", required_tools=["submit_filing"])
        assert agent.required_tools == ["submit_filing"]

    def test_required_tools_serialized(self):
        from agentspan.agents.config_serializer import AgentConfigSerializer

        agent = Agent(name="test", model="openai/gpt-4o", required_tools=["submit", "approve"])
        serializer = AgentConfigSerializer()
        config = serializer.serialize(agent)
        assert config["requiredTools"] == ["submit", "approve"]

    def test_required_tools_not_serialized_when_empty(self):
        from agentspan.agents.config_serializer import AgentConfigSerializer

        agent = Agent(name="test", model="openai/gpt-4o")
        serializer = AgentConfigSerializer()
        config = serializer.serialize(agent)
        assert "requiredTools" not in config


class TestNormalizeHandoffTarget:
    """Test _normalize_handoff_target() strips strategy prefixes correctly."""

    def test_indexed_handoff(self):
        """Standard handoff: {parent}_handoff_{idx}_{child}."""
        from agentspan.agents.runtime.runtime import _normalize_handoff_target

        assert _normalize_handoff_target("support_handoff_0_billing") == "billing"

    def test_indexed_agent(self):
        """Round-robin/swarm: {parent}_agent_{idx}_{child}."""
        from agentspan.agents.runtime.runtime import _normalize_handoff_target

        assert _normalize_handoff_target("panel_agent_1_expert") == "expert"

    def test_indexed_step(self):
        """Sequential: {parent}_step_{idx}_{child}."""
        from agentspan.agents.runtime.runtime import _normalize_handoff_target

        assert _normalize_handoff_target("pipeline_step_0_researcher") == "researcher"

    def test_indexed_parallel(self):
        """Parallel: {parent}_parallel_{idx}_{child}."""
        from agentspan.agents.runtime.runtime import _normalize_handoff_target

        assert _normalize_handoff_target("analysis_parallel_0_pros_analyst") == "pros_analyst"

    def test_no_index_handoff(self):
        """Handoff without index: {parent}_handoff_{child}."""
        from agentspan.agents.runtime.runtime import _normalize_handoff_target

        assert _normalize_handoff_target("test_handoff_agent_b") == "agent_b"

    def test_no_index_transfer(self):
        """Transfer without index: {parent}_transfer_{child}."""
        from agentspan.agents.runtime.runtime import _normalize_handoff_target

        assert _normalize_handoff_target("test_transfer_agent_b") == "agent_b"

    def test_trailing_turn_counter(self):
        """Strips trailing __N turn counter."""
        from agentspan.agents.runtime.runtime import _normalize_handoff_target

        assert _normalize_handoff_target("0_billing__1") == "billing"

    def test_round_robin_with_turn_counter(self):
        """Round-robin with trailing turn counter."""
        from agentspan.agents.runtime.runtime import _normalize_handoff_target

        assert _normalize_handoff_target("debate_round_robin_1_optimist__1") == "optimist"

    def test_leading_digit_prefix(self):
        """Fallback: strips leading digit_ prefix."""
        from agentspan.agents.runtime.runtime import _normalize_handoff_target

        assert _normalize_handoff_target("0_billing") == "billing"

    def test_already_clean(self):
        """Already clean name returned as-is."""
        from agentspan.agents.runtime.runtime import _normalize_handoff_target

        assert _normalize_handoff_target("billing") == "billing"


class TestTimeoutParameter:
    """Test run(timeout=N) threading through to start payload and polling."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080")
                return AgentRuntime(config=config)

    def test_timeout_included_in_start_payload(self, runtime):
        """run(timeout=5) sends timeoutSeconds: 5 in the start payload."""
        agent = Agent(name="test", model="openai/gpt-4o")

        mock_post = _mock_requests_post({"executionId": "wf-1"})
        with patch("requests.post", mock_post):
            runtime._start_via_server(agent, "hello", timeout=5)

        payload = mock_post.call_args[1]["json"]
        assert payload["timeoutSeconds"] == 5

    def test_no_timeout_omits_field(self, runtime):
        """run() with no timeout does not include timeoutSeconds in payload."""
        agent = Agent(name="test", model="openai/gpt-4o")

        mock_post = _mock_requests_post({"executionId": "wf-1"})
        with patch("requests.post", mock_post):
            runtime._start_via_server(agent, "hello")

        payload = mock_post.call_args[1]["json"]
        assert "timeoutSeconds" not in payload

    @patch("agentspan.agents.runtime.runtime.time.sleep", return_value=None)
    def test_poll_uses_agent_timeout_seconds(self, mock_sleep, runtime):
        """Agent(timeout_seconds=60) + run() → polling uses 60s."""
        running = AgentStatus(
            execution_id="wf-1",
            is_complete=False,
            is_running=True,
            status="RUNNING",
        )
        runtime.get_status = MagicMock(return_value=running)

        runtime._poll_status_until_complete("wf-1", timeout=3)

        # Should have polled for ~3 iterations (timeout=3s, interval=1s)
        assert runtime.get_status.call_count >= 3
        assert runtime.get_status.call_count <= 4

    @patch("agentspan.agents.runtime.runtime.time.sleep", return_value=None)
    def test_poll_defaults_to_300s_without_timeout(self, mock_sleep, runtime):
        """Polling defaults to 300s when no timeout is specified."""
        completed = AgentStatus(
            execution_id="wf-1",
            is_complete=True,
            status="COMPLETED",
            output="done",
        )
        runtime.get_status = MagicMock(return_value=completed)

        result = runtime._poll_status_until_complete("wf-1")

        assert result.is_complete is True


class TestUnrecognizedKwargs:
    """Test that unrecognized kwargs produce a warning."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080")
                return AgentRuntime(config=config)

    def test_warns_on_unrecognized_kwargs(self, runtime, caplog):
        """run(agent, prompt, foo=1) logs a warning."""
        import logging

        agent = Agent(name="test", model="openai/gpt-4o")

        # Patch the framework detection to return None (native agent)
        with patch("agentspan.agents.frameworks.serializer.detect_framework", return_value=None):
            with patch.object(runtime, "_prepare_workers"):
                with patch.object(runtime, "_start_via_server", return_value=("wf-1", None)):
                    with patch.object(runtime, "_poll_status_until_complete") as mock_poll:
                        mock_poll.return_value = AgentStatus(
                            execution_id="wf-1",
                            is_complete=True,
                            status="COMPLETED",
                            output={"result": "ok"},
                        )
                        with patch.object(runtime, "_workflow_client") as mock_wf:
                            mock_wf.get_workflow.side_effect = Exception("skip")
                            with caplog.at_level(
                                logging.WARNING, logger="agentspan.agents.runtime"
                            ):
                                runtime.run(agent, "hello", foo=1)

        assert "Unrecognized keyword arguments: foo" in caplog.text


class TestExceptionWrapping:
    """Test BUG-P3-05: HTTP errors are wrapped in SDK exceptions."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def test_get_status_404_raises_agent_not_found(self, runtime):
        """get_status with a 404 response raises AgentNotFoundError."""
        import requests

        from agentspan.agents.exceptions import AgentNotFoundError

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_resp)

        with patch("requests.get", return_value=mock_resp):
            with pytest.raises(AgentNotFoundError) as exc_info:
                runtime.get_status("nonexistent-id")
            assert exc_info.value.status_code == 404

    def test_get_status_500_raises_agent_api_error(self, runtime):
        """get_status with a 500 response raises AgentAPIError (not AgentNotFoundError)."""
        import requests

        from agentspan.agents.exceptions import AgentAPIError, AgentNotFoundError

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_resp)

        with patch("requests.get", return_value=mock_resp):
            with pytest.raises(AgentAPIError) as exc_info:
                runtime.get_status("some-id")
            assert exc_info.value.status_code == 500
            assert not isinstance(exc_info.value, AgentNotFoundError)

    def test_respond_error_wrapped(self, runtime):
        """respond() wraps HTTPError in AgentAPIError."""
        import requests

        from agentspan.agents.exceptions import AgentAPIError

        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request"
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_resp)

        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(AgentAPIError) as exc_info:
                runtime.respond("wf-id", "some output")
            assert exc_info.value.status_code == 400


class TestSSEFallbackWarnsOnce:
    """Test BUG-P3-03: SSE fallback warning fires only once."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.config import AgentConfig
                from agentspan.agents.runtime.runtime import AgentRuntime

                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def test_sse_fallback_logs_once(self, runtime, caplog):
        """SSE fallback message should be logged only on the first failure."""
        from agentspan.agents.runtime.http_client import SSEUnavailableError

        call_count = 0

        def mock_stream_sse(execution_id):
            raise SSEUnavailableError("no SSE")

        def mock_stream_polling(execution_id):
            yield from []

        with patch.object(runtime, "_stream_sse", side_effect=mock_stream_sse):
            with patch.object(runtime, "_stream_polling", side_effect=mock_stream_polling):
                with caplog.at_level(logging.INFO, logger="agentspan.agents.runtime"):
                    # First call — should log
                    list(runtime._stream_workflow("wf-1"))
                    # Second call — should NOT log again
                    list(runtime._stream_workflow("wf-2"))

        fallback_messages = [r for r in caplog.records if "SSE unavailable" in r.message]
        assert len(fallback_messages) == 1


class TestHandoffIndexing:
    """Verify that _register_handoff_worker uses parent-inclusive indexing.

    The compiler produces SWITCH cases with the parent as Case 0 and
    sub-agents as Case 1, 2, etc. The SDK's handoff_check_worker must match.
    """

    def test_name_to_idx_is_parent_inclusive(self):
        """Parent should be '0'; sub-agents should be '1', '2', etc."""
        from agentspan.agents import Strategy

        parent = Agent(
            name="parent",
            model="openai/gpt-4o",
            agents=[
                Agent(name="child_a", model="openai/gpt-4o"),
                Agent(name="child_b", model="openai/gpt-4o"),
                Agent(name="child_c", model="openai/gpt-4o"),
            ],
            strategy=Strategy.SWARM,
        )

        # Build name_to_idx the same way as _register_handoff_worker
        name_to_idx = {parent.name: "0"}
        name_to_idx.update({sub.name: str(i + 1) for i, sub in enumerate(parent.agents)})

        assert name_to_idx == {
            "parent": "0",
            "child_a": "1",
            "child_b": "2",
            "child_c": "3",
        }

    def test_handoff_worker_routes_transfer_correctly(self):
        """Simulate handoff_check_worker logic with parent-inclusive indexing."""
        # Mimic the 3-agent setup: coding_team(parent=0), coder(1), qa_tester(2)
        name_to_idx = {"coding_team": "0", "coder": "1", "qa_tester": "2"}

        def handoff_check(transfer_to, active_agent, is_transfer=True):
            if is_transfer:
                target_idx = name_to_idx.get(transfer_to, active_agent)
                if target_idx != active_agent:
                    return {"active_agent": target_idx, "handoff": True}
            return {"active_agent": active_agent, "handoff": False}

        # coding_team ("0") → coder ("1")
        result = handoff_check("coder", "0")
        assert result == {"active_agent": "1", "handoff": True}

        # coder ("1") → qa_tester ("2")
        result = handoff_check("qa_tester", "1")
        assert result == {"active_agent": "2", "handoff": True}

        # qa_tester ("2") → coder ("1")
        result = handoff_check("coder", "2")
        assert result == {"active_agent": "1", "handoff": True}

        # coder done, no transfer → stays on coder
        result = handoff_check("", "1", is_transfer=False)
        assert result == {"active_agent": "1", "handoff": False}

        # Transfer to unknown agent → no-op
        result = handoff_check("nonexistent", "1")
        assert result == {"active_agent": "1", "handoff": False}

    def test_handoff_no_transfer_returns_active(self):
        """When is_transfer is False, active_agent should be unchanged."""
        name_to_idx = {"parent": "0", "child": "1"}
        active = "1"
        # No transfer → should return active unchanged
        target_idx = name_to_idx.get("", active)
        assert target_idx == active

    def test_allowed_transitions_blocks_disallowed_transfer(self):
        """When allowed_transitions is set, disallowed transfers are rejected."""
        name_to_idx = {
            "coding_team": "0",
            "github_agent": "1",
            "coder": "2",
            "qa_tester": "3",
        }
        idx_to_name = {v: k for k, v in name_to_idx.items()}
        allowed = {
            "coding_team": ["github_agent"],
            "github_agent": ["coder"],
            "coder": ["qa_tester"],
            "qa_tester": ["coder", "github_agent"],
        }

        def handoff_check(transfer_to, active_agent, is_transfer=True):
            if is_transfer:
                current_name = idx_to_name.get(active_agent, "")
                if transfer_to not in allowed.get(current_name, []):
                    return {"active_agent": active_agent, "handoff": False}
                target_idx = name_to_idx.get(transfer_to, active_agent)
                if target_idx != active_agent:
                    return {"active_agent": target_idx, "handoff": True}
            return {"active_agent": active_agent, "handoff": False}

        # Allowed: qa_tester → coder
        result = handoff_check("coder", "3")
        assert result == {"active_agent": "2", "handoff": True}

        # Allowed: qa_tester → github_agent
        result = handoff_check("github_agent", "3")
        assert result == {"active_agent": "1", "handoff": True}

        # BLOCKED: qa_tester → coding_team (not in allowed list)
        result = handoff_check("coding_team", "3")
        assert result == {"active_agent": "3", "handoff": False}

        # BLOCKED: coder → github_agent (coder can only go to qa_tester)
        result = handoff_check("github_agent", "2")
        assert result == {"active_agent": "2", "handoff": False}

        # Allowed: coder → qa_tester
        result = handoff_check("qa_tester", "2")
        assert result == {"active_agent": "3", "handoff": True}
