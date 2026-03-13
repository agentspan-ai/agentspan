# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for the AgentRuntime.

Tests runtime helper methods (extract_output, extract_handoff_result, etc.)
using mock workflow objects. Does NOT require a running Conductor server.
"""

import uuid

import pytest
from unittest.mock import MagicMock, patch

from agentspan.agents.agent import Agent
from agentspan.agents.result import AgentResult, AgentHandle, AgentStatus, EventType


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

    def __init__(self, output=None, variables=None, tasks=None, status="COMPLETED",
                 workflow_id="test-wf-123"):
        self.output = output
        self.variables = variables or {}
        self.tasks = tasks or []
        self.status = status
        self.workflow_id = workflow_id


class TestExtractOutput:
    """Test _extract_output() helper."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.runtime import AgentRuntime
                from agentspan.agents.runtime.config import AgentConfig
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
                from agentspan.agents.runtime.runtime import AgentRuntime
                from agentspan.agents.runtime.config import AgentConfig
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
                from agentspan.agents.runtime.runtime import AgentRuntime
                from agentspan.agents.runtime.config import AgentConfig
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
        from agentspan.agents.run import _get_default_runtime
        import agentspan.agents.run as run_module

        # Reset singleton
        run_module._default_runtime = None

        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
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
                assert rt._config.auth_key == "explicit-key"
                assert rt._config.auth_secret == "explicit-secret"

    def test_config_object(self):
        """AgentRuntime(config=AgentConfig(...)) uses the config object."""
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.runtime import AgentRuntime
                from agentspan.agents.runtime.config import AgentConfig
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
                from agentspan.agents.runtime.runtime import AgentRuntime
                from agentspan.agents.runtime.config import AgentConfig
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
                from agentspan.agents.runtime.runtime import AgentRuntime
                from agentspan.agents.runtime.config import AgentConfig
                cfg = AgentConfig(
                    server_url="http://config/api",
                    default_timeout_seconds=600,
                    worker_thread_count=4,
                )
                rt = AgentRuntime(config=cfg, server_url="http://override/api")
                assert rt._config.server_url == "http://override/api"
                assert rt._config.default_timeout_seconds == 600
                assert rt._config.worker_thread_count == 4


class TestAgentConfig:
    """Test AgentConfig BaseSettings loads from env."""

    def test_defaults(self):
        from agentspan.agents.runtime.config import AgentConfig
        from unittest.mock import patch

        with patch.dict("os.environ", {}, clear=True):
            config = AgentConfig()
            assert config.server_url == "http://localhost:8080/api"
            assert config.default_timeout_seconds == 0
            assert config.llm_retry_count == 3
            assert config.worker_poll_interval_ms == 100

    def test_env_override(self):
        from agentspan.agents.runtime.config import AgentConfig
        from unittest.mock import patch

        with patch.dict("os.environ", {"AGENTSPAN_SERVER_URL": "http://custom:9090/api"}, clear=True):
            config = AgentConfig()
            assert config.server_url == "http://custom:9090/api"

    def test_custom_timeout(self):
        from agentspan.agents.runtime.config import AgentConfig
        config = AgentConfig(default_timeout_seconds=600, llm_retry_count=5)
        assert config.default_timeout_seconds == 600
        assert config.llm_retry_count == 5


class TestCorrelationId:
    """Test that run() and start() generate a correlationId."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.runtime import AgentRuntime
                from agentspan.agents.runtime.config import AgentConfig
                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def test_run_generates_correlation_id(self, runtime):
        """Verify AgentResult.correlation_id is a valid UUID string."""
        agent = Agent(name="test", model="openai/gpt-4o")

        runtime._prepare_workers = MagicMock()
        runtime._start_via_server = MagicMock(return_value="wf-123")
        runtime._poll_status_until_complete = MagicMock(return_value=AgentStatus(
            workflow_id="wf-123", is_complete=True, output="Hello", status="COMPLETED",
        ))

        result = runtime.run(agent, "Hello")

        assert result.correlation_id is not None
        # Should be a valid UUID
        parsed = uuid.UUID(result.correlation_id)
        assert str(parsed) == result.correlation_id

    def test_start_generates_correlation_id(self, runtime):
        """Verify AgentHandle.correlation_id is set."""
        agent = Agent(name="test", model="openai/gpt-4o")

        runtime._prepare_workers = MagicMock()
        runtime._start_via_server = MagicMock(return_value="wf-456")

        handle = runtime.start(agent, "Hello")

        assert handle.correlation_id is not None
        # Should be a valid UUID
        parsed = uuid.UUID(handle.correlation_id)
        assert str(parsed) == handle.correlation_id
        assert handle.workflow_id == "wf-456"


class TestRuntimeRespond:
    """Test AgentRuntime.respond() calls update_task_sync."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.runtime import AgentRuntime
                from agentspan.agents.runtime.config import AgentConfig
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
                from agentspan.agents.runtime.runtime import AgentRuntime
                from agentspan.agents.runtime.config import AgentConfig
                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def test_run_passes_media_to_start_via_server(self, runtime):
        """Verify media URLs are passed to _start_via_server."""
        agent = Agent(name="test", model="openai/gpt-4o")

        runtime._prepare_workers = MagicMock()
        runtime._start_via_server = MagicMock(return_value="wf-media")
        runtime._poll_status_until_complete = MagicMock(return_value=AgentStatus(
            workflow_id="wf-media", is_complete=True, output="I see a cat", status="COMPLETED",
        ))

        result = runtime.run(
            agent, "Describe this image",
            media=["https://example.com/cat.jpg"],
        )

        call_kwargs = runtime._start_via_server.call_args
        assert call_kwargs[1]["media"] == ["https://example.com/cat.jpg"]
        assert result.output == "I see a cat"

    def test_run_defaults_media_to_none(self, runtime):
        """Verify media defaults to None when not provided."""
        agent = Agent(name="test", model="openai/gpt-4o")

        runtime._prepare_workers = MagicMock()
        runtime._start_via_server = MagicMock(return_value="wf-nomedia")
        runtime._poll_status_until_complete = MagicMock(return_value=AgentStatus(
            workflow_id="wf-nomedia", is_complete=True, output="Hello", status="COMPLETED",
        ))

        runtime.run(agent, "Hello")

        call_kwargs = runtime._start_via_server.call_args
        assert call_kwargs[1]["media"] is None

    def test_start_passes_media_to_start_via_server(self, runtime):
        """Verify media URLs flow through start()."""
        agent = Agent(name="test", model="openai/gpt-4o")

        runtime._prepare_workers = MagicMock()
        runtime._start_via_server = MagicMock(return_value="wf-media-start")

        handle = runtime.start(
            agent, "What's in this photo?",
            media=["https://example.com/photo.png", "https://example.com/photo2.png"],
        )

        call_kwargs = runtime._start_via_server.call_args
        assert call_kwargs[1]["media"] == [
            "https://example.com/photo.png",
            "https://example.com/photo2.png",
        ]
        assert handle.workflow_id == "wf-media-start"


# ── Lifecycle methods ───────────────────────────────────────────────────


class TestRuntimeLifecycle:
    """Test shutdown, pause, resume, cancel, send_message, context manager."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.runtime import AgentRuntime
                from agentspan.agents.runtime.config import AgentConfig
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
            workflow_id="wf-1", reason="done"
        )

    def test_send_message_delegates(self, runtime):
        runtime.respond = MagicMock()
        runtime.send_message("wf-1", "hello")
        runtime.respond.assert_called_once_with("wf-1", {"message": "hello"})

    def test_context_manager(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.runtime import AgentRuntime
                from agentspan.agents.runtime.config import AgentConfig
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
                from agentspan.agents.runtime.runtime import AgentRuntime
                from agentspan.agents.runtime.config import AgentConfig
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
                from agentspan.agents.runtime.runtime import AgentRuntime
                from agentspan.agents.runtime.config import AgentConfig
                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def test_single_llm_task(self, runtime):
        task = MagicMock()
        task.task_type = "LLM_CHAT_COMPLETE"
        task.output_data = {"tokenUsed": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}}
        wf_run = MockWorkflowRun(tasks=[task])

        usage = runtime._extract_token_usage(wf_run)
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150

    def test_multiple_llm_tasks(self, runtime):
        task1 = MagicMock()
        task1.task_type = "LLM_CHAT_COMPLETE"
        task1.output_data = {"tokenUsed": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}}

        task2 = MagicMock()
        task2.task_type = "LLM_CHAT_COMPLETE"
        task2.output_data = {"tokenUsed": {"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300}}

        wf_run = MockWorkflowRun(tasks=[task1, task2])
        usage = runtime._extract_token_usage(wf_run)
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
        task = MagicMock()
        task.task_type = "LLM_CHAT_COMPLETE"
        task.output_data = {"tokenUsed": {"prompt_tokens": 100, "completion_tokens": 50}}
        wf_run = MockWorkflowRun(tasks=[task])

        usage = runtime._extract_token_usage(wf_run)
        assert usage.total_tokens == 150


# ── _extract_tool_calls ─────────────────────────────────────────────────


class TestExtractToolCalls:
    """Test _extract_tool_calls() extraction."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.runtime import AgentRuntime
                from agentspan.agents.runtime.config import AgentConfig
                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def test_extracts_tool_tasks(self, runtime):
        task = MagicMock()
        task.task_type = "tool_execution"
        task.reference_task_name = "get_weather"
        task.input_data = {"city": "NYC"}
        task.output_data = {"temp": 72}
        wf_run = MockWorkflowRun(tasks=[task])

        calls = runtime._extract_tool_calls(wf_run)
        assert len(calls) == 1
        assert calls[0]["name"] == "get_weather"
        assert calls[0]["input"] == {"city": "NYC"}

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
                from agentspan.agents.runtime.runtime import AgentRuntime
                from agentspan.agents.runtime.config import AgentConfig
                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def _mock_status_response(self, runtime, response_json):
        """Patch requests.get to return a mock status response."""
        return patch(
            "requests.get",
            _mock_requests_get(response_json),
        )

    def test_completed(self, runtime):
        resp = {"status": "COMPLETED", "isComplete": True, "isRunning": False,
                "isWaiting": False, "output": "Done"}
        with self._mock_status_response(runtime, resp):
            status = runtime.get_status("wf-1")
        assert status.is_complete is True
        assert status.output == "Done"

    def test_running(self, runtime):
        resp = {"status": "RUNNING", "isComplete": False, "isRunning": True,
                "isWaiting": False, "output": None}
        with self._mock_status_response(runtime, resp):
            status = runtime.get_status("wf-1")
        assert status.is_running is True
        assert status.is_complete is False

    def test_paused(self, runtime):
        resp = {"status": "PAUSED", "isComplete": False, "isRunning": False,
                "isWaiting": True, "output": None}
        with self._mock_status_response(runtime, resp):
            status = runtime.get_status("wf-1")
        assert status.is_waiting is True

    def test_with_human_task(self, runtime):
        resp = {"status": "RUNNING", "isComplete": False, "isRunning": False,
                "isWaiting": True, "output": None,
                "pendingTool": {"tool_name": "approve_action", "parameters": {"x": 1}}}
        with self._mock_status_response(runtime, resp):
            status = runtime.get_status("wf-1")
        assert status.is_waiting is True
        assert status.pending_tool["tool_name"] == "approve_action"

    def test_failed(self, runtime):
        resp = {"status": "FAILED", "isComplete": True, "isRunning": False,
                "isWaiting": False, "output": None}
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
                from agentspan.agents.runtime.runtime import AgentRuntime
                from agentspan.agents.runtime.config import AgentConfig
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


# ── run() with guardrails ──────────────────────────────────────────────


class TestRuntimeRunGuardrails:
    """Test run() method guardrail paths."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.runtime import AgentRuntime
                from agentspan.agents.runtime.config import AgentConfig
                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def _setup_run(self, runtime, output="Hello", status="COMPLETED"):
        runtime._prepare_workers = MagicMock()
        runtime._start_via_server = MagicMock(return_value="wf-guard")
        runtime._poll_status_until_complete = MagicMock(return_value=AgentStatus(
            workflow_id="wf-guard", is_complete=True, output=output, status=status,
        ))

    def test_input_guardrail_raises(self, runtime):
        from agentspan.agents.guardrail import Guardrail, GuardrailResult
        guard = Guardrail(
            func=lambda c: GuardrailResult(passed=False, message="Bad input"),
            position="input", on_fail="raise",
        )
        agent = Agent(name="test", model="openai/gpt-4o", guardrails=[guard])
        self._setup_run(runtime)

        with pytest.raises(ValueError, match="Input guardrail"):
            runtime.run(agent, "bad prompt")

    def test_input_guardrail_passes(self, runtime):
        from agentspan.agents.guardrail import Guardrail, GuardrailResult
        guard = Guardrail(
            func=lambda c: GuardrailResult(passed=True),
            position="input", on_fail="raise",
        )
        agent = Agent(name="test", model="openai/gpt-4o", guardrails=[guard])
        self._setup_run(runtime)

        result = runtime.run(agent, "good prompt")
        assert result.output == "Hello"

    def test_output_guardrail_compiled_single_execution(self, runtime):
        """All output guardrails now use compiled path (single workflow execution).

        Guardrail behavior (fix, retry, raise) happens inside the Conductor
        DoWhile loop, not client-side.  The runtime runs the workflow once.
        """
        from agentspan.agents.guardrail import Guardrail, GuardrailResult
        guard = Guardrail(
            func=lambda c: GuardrailResult(passed=False, message="PII", fixed_output="REDACTED"),
            position="output", on_fail="fix",
        )
        agent = Agent(name="test", model="openai/gpt-4o", guardrails=[guard])
        self._setup_run(runtime, output="workflow handled fix")

        result = runtime.run(agent, "show data")
        # Compiled path: workflow runs once, guardrails handled server-side
        assert result.output == "workflow handled fix"
        runtime._start_via_server.assert_called_once()

    def test_output_guardrail_compiled_raise_returns_failed(self, runtime):
        """Output guardrail raise terminates workflow with FAILED status."""
        from agentspan.agents.guardrail import Guardrail, GuardrailResult
        guard = Guardrail(
            func=lambda c: GuardrailResult(passed=False, message="unsafe"),
            position="output", on_fail="raise",
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
            position="output", on_fail="retry", max_retries=3,
        )
        agent = Agent(name="test", model="openai/gpt-4o", guardrails=[guard])
        self._setup_run(runtime, output="retried answer")

        result = runtime.run(agent, "test")
        # Retries happen inside the workflow's DoWhile loop
        assert result.output == "retried answer"
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
            position="output", on_fail="retry",
        )
        agent = Agent(
            name="test", model="openai/gpt-4o",
            tools=[my_tool], guardrails=[guard],
        )
        self._setup_run(runtime, output="tool answer")

        result = runtime.run(agent, "test")
        assert result.output == "tool answer"
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
            position="output", on_fail="raise",
        )
        agent = Agent(
            name="test", model="openai/gpt-4o",
            tools=[my_tool], guardrails=[guard],
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
        assert result.output == "answer"
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
            position="input", on_fail="retry",
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
            position="input", on_fail="raise",
        )
        agent = Agent(name="test", model="openai/gpt-4o", guardrails=[guard])

        runtime._prepare_workers = MagicMock()
        runtime._start_via_server = MagicMock(return_value="wf-123")

        with pytest.raises(ValueError, match="Input guardrail"):
            runtime.start(agent, "bad prompt")


class TestHasWorkerTools:
    """Test _has_worker_tools with different guardrail types."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.runtime import AgentRuntime
                from agentspan.agents.runtime.config import AgentConfig
                rt = AgentRuntime(config=AgentConfig(auto_start_workers=False))
                yield rt

    def test_regex_guardrail_only_no_workers(self, runtime):
        """RegexGuardrail compiles to InlineTask — no workers needed."""
        from agentspan.agents.guardrail import RegexGuardrail
        agent = Agent(
            name="test", model="openai/gpt-4o",
            guardrails=[RegexGuardrail(patterns=[r"\d+"], name="digits")],
        )
        assert runtime._has_worker_tools(agent) is False

    def test_external_guardrail_only_no_workers(self, runtime):
        """External guardrails compile to SimpleTask — no local workers needed."""
        from agentspan.agents.guardrail import Guardrail
        agent = Agent(
            name="test", model="openai/gpt-4o",
            guardrails=[Guardrail(name="remote_check", on_fail="retry")],
        )
        assert runtime._has_worker_tools(agent) is False

    def test_custom_guardrail_needs_workers(self, runtime):
        """Custom function guardrails compile to worker tasks — workers needed."""
        from agentspan.agents.guardrail import Guardrail, GuardrailResult
        agent = Agent(
            name="test", model="openai/gpt-4o",
            guardrails=[Guardrail(
                func=lambda c: GuardrailResult(passed=True),
                on_fail="retry",
            )],
        )
        assert runtime._has_worker_tools(agent) is True

    def test_llm_guardrail_no_workers(self, runtime):
        """LLMGuardrail compiles to server-side LlmChatComplete — no workers needed."""
        from agentspan.agents.guardrail import LLMGuardrail
        agent = Agent(
            name="test", model="openai/gpt-4o",
            guardrails=[LLMGuardrail(model="openai/gpt-4o-mini", policy="be safe")],
        )
        assert runtime._has_worker_tools(agent) is False

    def test_mixed_regex_and_custom_needs_workers(self, runtime):
        """Mix of regex + custom guardrails — needs workers for the custom one."""
        from agentspan.agents.guardrail import Guardrail, GuardrailResult, RegexGuardrail
        agent = Agent(
            name="test", model="openai/gpt-4o",
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
                from agentspan.agents.runtime.runtime import AgentRuntime
                from agentspan.agents.runtime.config import AgentConfig
                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def test_stream_yields_done_on_completion(self, runtime):
        agent = Agent(name="test", model="openai/gpt-4o")

        # Mock start() internals
        runtime._prepare_workers = MagicMock()
        runtime._start_via_server = MagicMock(return_value="wf-stream-1")

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
        runtime._start_via_server = MagicMock(return_value="wf-stream-2")

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

        runtime._workflow_client.get_workflow = MagicMock(
            side_effect=[running_wf, completed_wf]
        )

        with patch("time.sleep"):
            events = list(runtime.stream(agent, "Hello"))

        thinking = [e for e in events if e.type == EventType.THINKING]
        assert len(thinking) == 1

    def test_stream_yields_error_on_failure(self, runtime):
        agent = Agent(name="test", model="openai/gpt-4o")

        runtime._prepare_workers = MagicMock()
        runtime._start_via_server = MagicMock(return_value="wf-stream-err")

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
        runtime._start_via_server = MagicMock(return_value="wf-stream-wait")

        # First poll: paused
        paused_wf = MagicMock()
        paused_wf.status = "PAUSED"
        paused_wf.tasks = []

        # Second poll: completed
        completed_wf = MagicMock()
        completed_wf.status = "COMPLETED"
        completed_wf.tasks = []
        completed_wf.output = {"result": "resumed"}

        runtime._workflow_client.get_workflow = MagicMock(
            side_effect=[paused_wf, completed_wf]
        )

        with patch("time.sleep"):
            events = list(runtime.stream(agent, "Hello"))

        waiting = [e for e in events if e.type == EventType.WAITING]
        assert len(waiting) == 1

    def test_stream_yields_error_on_fetch_exception(self, runtime):
        agent = Agent(name="test", model="openai/gpt-4o")

        runtime._prepare_workers = MagicMock()
        runtime._start_via_server = MagicMock(return_value="wf-stream-exc")

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
        runtime._start_via_server = MagicMock(return_value="wf-stream-tool")

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
        runtime._start_via_server = MagicMock(return_value="wf-stream-handoff")

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
                from agentspan.agents.runtime.runtime import AgentRuntime
                from agentspan.agents.runtime.config import AgentConfig
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
        from dataclasses import dataclass
        import json

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
                from agentspan.agents.runtime.runtime import AgentRuntime
                from agentspan.agents.runtime.config import AgentConfig
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
                from agentspan.agents.runtime.runtime import AgentRuntime
                from agentspan.agents.runtime.config import AgentConfig
                config = AgentConfig(server_url="http://fake:8080", auto_start_workers=False)
                return AgentRuntime(config=config)

    def test_completed_non_dict_output(self, runtime):
        """Non-dict output in completed workflow is returned as-is."""
        resp = {"status": "COMPLETED", "isComplete": True, "isRunning": False,
                "isWaiting": False, "output": "raw output"}
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
                from agentspan.agents.runtime.runtime import AgentRuntime
                from agentspan.agents.runtime.config import AgentConfig
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
                from agentspan.agents.runtime.runtime import AgentRuntime
                from agentspan.agents.runtime.config import AgentConfig
                config = AgentConfig(server_url="http://fake:8080", default_timeout_seconds=10)
                return AgentRuntime(config=config)

    def test_start_via_server_returns_workflow_id(self, runtime):
        """_start_via_server returns the workflowId from the server response."""
        agent = Agent(name="test", model="openai/gpt-4o")

        with patch("requests.post",
                    _mock_requests_post({"workflowId": "wf-server-1"})):
            wf_id = runtime._start_via_server(agent, "hello")

        assert wf_id == "wf-server-1"

    def test_start_via_server_sends_prompt(self, runtime):
        """_start_via_server includes the prompt in the payload."""
        agent = Agent(name="test", model="openai/gpt-4o")

        mock_post = _mock_requests_post({"workflowId": "wf-1"})
        with patch("requests.post", mock_post):
            runtime._start_via_server(agent, "test prompt")

        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"]
        assert payload["prompt"] == "test prompt"

    def test_start_via_server_passes_media(self, runtime):
        """_start_via_server includes media in the payload."""
        agent = Agent(name="test", model="openai/gpt-4o")

        mock_post = _mock_requests_post({"workflowId": "wf-1"})
        with patch("requests.post", mock_post):
            runtime._start_via_server(agent, "describe", media=["https://img.png"])

        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"]
        assert payload["media"] == ["https://img.png"]

    def test_start_via_server_passes_idempotency_key(self, runtime):
        """Idempotency key is included in the payload when provided."""
        agent = Agent(name="test", model="openai/gpt-4o")

        mock_post = _mock_requests_post({"workflowId": "wf-1"})
        with patch("requests.post", mock_post):
            runtime._start_via_server(agent, "hi", idempotency_key="idem-123")

        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"]
        assert payload["idempotencyKey"] == "idem-123"


class TestPollStatusUntilComplete:
    """Test _poll_status_until_complete() polling logic."""

    @pytest.fixture()
    def runtime(self):
        with patch("conductor.client.orkes_clients.OrkesClients"):
            with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
                from agentspan.agents.runtime.runtime import AgentRuntime
                from agentspan.agents.runtime.config import AgentConfig
                config = AgentConfig(server_url="http://fake:8080", default_timeout_seconds=5)
                return AgentRuntime(config=config)

    @patch("agentspan.agents.runtime.runtime.time.sleep", return_value=None)
    def test_returns_on_completed(self, mock_sleep, runtime):
        """Returns immediately when workflow is COMPLETED."""
        completed = AgentStatus(
            workflow_id="wf-1", is_complete=True, status="COMPLETED", output="done",
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
            workflow_id="wf-1", is_complete=True, status="FAILED",
        )
        runtime.get_status = MagicMock(return_value=failed)

        result = runtime._poll_status_until_complete("wf-1")

        assert result.status == "FAILED"
        assert result.is_complete is True

    @patch("agentspan.agents.runtime.runtime.time.sleep", return_value=None)
    def test_returns_on_terminated(self, mock_sleep, runtime):
        """Returns when workflow is TERMINATED."""
        terminated = AgentStatus(
            workflow_id="wf-1", is_complete=True, status="TERMINATED",
        )
        runtime.get_status = MagicMock(return_value=terminated)

        result = runtime._poll_status_until_complete("wf-1")
        assert result.status == "TERMINATED"

    @patch("agentspan.agents.runtime.runtime.time.sleep", return_value=None)
    def test_polls_until_complete(self, mock_sleep, runtime):
        """Polls multiple times until workflow reaches terminal state."""
        running = AgentStatus(
            workflow_id="wf-1", is_complete=False, is_running=True, status="RUNNING",
        )
        completed = AgentStatus(
            workflow_id="wf-1", is_complete=True, status="COMPLETED", output="done",
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
            workflow_id="wf-1", is_complete=False, is_running=True, status="RUNNING",
        )
        runtime.get_status = MagicMock(return_value=running)

        result = runtime._poll_status_until_complete("wf-1")

        # Should have polled for ~5 iterations (timeout=5s, interval=1s)
        assert runtime.get_status.call_count >= 5
        assert result.status == "RUNNING"  # returned incomplete

    @patch("agentspan.agents.runtime.runtime.time.sleep", return_value=None)
    def test_returns_on_timed_out_status(self, mock_sleep, runtime):
        """TIMED_OUT is a terminal state."""
        timed_out = AgentStatus(
            workflow_id="wf-1", is_complete=True, status="TIMED_OUT",
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

                from agentspan.agents.runtime.runtime import AgentRuntime
                from agentspan.agents.runtime.config import AgentConfig
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

                from agentspan.agents.runtime.runtime import AgentRuntime
                from agentspan.agents.runtime.config import AgentConfig
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
