# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tests for AgentRuntime.deploy(), serve(), and run/start/stream by name."""

import pytest
from unittest.mock import patch, MagicMock

from agentspan.agents.agent import Agent
from agentspan.agents.result import DeploymentInfo


def _make_runtime():
    """Create an AgentRuntime with mocked Conductor clients."""
    with patch("conductor.client.orkes_clients.OrkesClients"):
        with patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):
            from agentspan.agents.runtime.runtime import AgentRuntime
            from agentspan.agents.runtime.config import AgentConfig

            config = AgentConfig(
                server_url="http://fake:8080",
                auto_start_workers=False,
            )
            return AgentRuntime(config=config)


# ── Deploy tests ──────────────────────────────────────────────────────


class TestDeploy:
    def test_deploy_single_agent(self):
        rt = _make_runtime()
        agent = Agent(name="bot", model="openai/gpt-4o")
        with patch.object(rt, "_deploy_via_server", return_value="bot_wf") as mock:
            results = rt.deploy(agent)
        assert len(results) == 1
        assert results[0].workflow_name == "bot_wf"
        assert results[0].agent_name == "bot"
        mock.assert_called_once()

    def test_deploy_multiple_agents(self):
        rt = _make_runtime()
        a1 = Agent(name="a1", model="openai/gpt-4o")
        a2 = Agent(name="a2", model="openai/gpt-4o")
        a3 = Agent(name="a3", model="openai/gpt-4o")
        with patch.object(
            rt, "_deploy_via_server", side_effect=["a1_wf", "a2_wf", "a3_wf"]
        ):
            results = rt.deploy(a1, a2, a3)
        assert len(results) == 3
        assert [r.workflow_name for r in results] == ["a1_wf", "a2_wf", "a3_wf"]

    def test_deploy_with_packages(self):
        rt = _make_runtime()
        discovered = Agent(name="discovered", model="openai/gpt-4o")
        with patch(
            "agentspan.agents.runtime.discovery.discover_agents",
            return_value=[discovered],
        ):
            with patch.object(rt, "_deploy_via_server", return_value="disc_wf"):
                results = rt.deploy(packages=["myapp.agents"])
        assert len(results) == 1
        assert results[0].agent_name == "discovered"

    def test_deploy_mixed_agents_and_packages(self):
        rt = _make_runtime()
        explicit = Agent(name="explicit", model="openai/gpt-4o")
        discovered = Agent(name="discovered", model="openai/gpt-4o")
        with patch(
            "agentspan.agents.runtime.discovery.discover_agents",
            return_value=[discovered],
        ):
            with patch.object(
                rt, "_deploy_via_server", side_effect=["ex_wf", "disc_wf"]
            ):
                results = rt.deploy(explicit, packages=["myapp"])
        assert len(results) == 2

    def test_deploy_no_agents_raises(self):
        rt = _make_runtime()
        with pytest.raises(ValueError, match="at least one agent"):
            rt.deploy()

    def test_deploy_returns_deployment_info_type(self):
        rt = _make_runtime()
        agent = Agent(name="bot", model="openai/gpt-4o")
        with patch.object(rt, "_deploy_via_server", return_value="bot_wf"):
            results = rt.deploy(agent)
        assert isinstance(results[0], DeploymentInfo)


# ── Serve tests ──────────────────────────────────────────────────────


class TestServe:
    def test_serve_single_agent_nonblocking(self):
        rt = _make_runtime()
        agent = Agent(name="bot", model="openai/gpt-4o")
        with patch.object(rt, "_register_workers") as mock_reg:
            with patch.object(
                rt, "_collect_worker_names", return_value={"bot_tool"}
            ):
                rt.serve(agent, blocking=False)
        mock_reg.assert_called_once_with(agent)

    def test_serve_multiple_agents(self):
        rt = _make_runtime()
        a1 = Agent(name="a1", model="openai/gpt-4o")
        a2 = Agent(name="a2", model="openai/gpt-4o")
        with patch.object(rt, "_register_workers") as mock_reg:
            with patch.object(rt, "_collect_worker_names", return_value=set()):
                rt.serve(a1, a2, blocking=False)
        assert mock_reg.call_count == 2

    def test_serve_with_packages(self):
        rt = _make_runtime()
        discovered = Agent(name="disc", model="openai/gpt-4o")
        with patch(
            "agentspan.agents.runtime.discovery.discover_agents",
            return_value=[discovered],
        ):
            with patch.object(rt, "_register_workers"):
                with patch.object(rt, "_collect_worker_names", return_value=set()):
                    rt.serve(packages=["myapp.agents"], blocking=False)

    def test_serve_no_agents_raises(self):
        rt = _make_runtime()
        with pytest.raises(ValueError, match="at least one Agent"):
            rt.serve()

    def test_serve_starts_worker_manager(self):
        rt = _make_runtime()
        agent = Agent(name="bot", model="openai/gpt-4o")
        with patch.object(rt, "_register_workers"):
            with patch.object(rt, "_collect_worker_names", return_value={"t"}):
                rt.serve(agent, blocking=False)
        assert rt._workers_started


# ── Run/Start/Stream by name tests ──────────────────────────────────


class TestRunByName:
    def test_run_with_string_dispatches_to_run_by_name(self):
        rt = _make_runtime()
        mock_result = MagicMock()
        with patch.object(rt, "_run_by_name", return_value=mock_result) as mock:
            result = rt.run("my_workflow", "hello")
        mock.assert_called_once()
        assert mock.call_args[0] == ("my_workflow", "hello")
        assert result is mock_result

    def test_run_with_agent_object_does_not_call_run_by_name(self):
        rt = _make_runtime()
        agent = Agent(name="bot", model="openai/gpt-4o")
        with patch.object(rt, "_run_by_name") as mock_name:
            with patch.object(rt, "_prepare_workers"):
                with patch.object(rt, "_start_via_server", return_value="wf-id"):
                    with patch.object(rt, "_poll_status_until_complete") as mock_poll:
                        mock_poll.return_value = MagicMock(
                            output={"result": "ok"},
                            status="COMPLETED",
                            reason=None,
                        )
                        with patch.object(
                            rt, "_normalize_output", return_value={"result": "ok"}
                        ):
                            try:
                                rt.run(agent, "hello")
                            except Exception:
                                pass
        mock_name.assert_not_called()

    def test_start_with_string(self):
        rt = _make_runtime()
        mock_handle = MagicMock()
        with patch.object(rt, "_start_by_name", return_value=mock_handle) as mock:
            result = rt.start("my_workflow", "hello")
        mock.assert_called_once()
        assert result is mock_handle

    def test_stream_with_string(self):
        rt = _make_runtime()
        mock_handle = MagicMock(workflow_id="wf-123")
        mock_stream_iter = iter([])
        with patch.object(rt, "_start_by_name", return_value=mock_handle):
            with patch.object(
                rt, "_stream_workflow", return_value=mock_stream_iter
            ):
                result = rt.stream("my_workflow", "hello")
        assert result.handle is mock_handle

    def test_run_by_name_passes_version(self):
        rt = _make_runtime()
        with patch.object(rt, "_run_by_name") as mock:
            mock.return_value = MagicMock()
            rt.run("wf_name", "prompt", version=3)
        assert mock.call_args[1].get("version") == 3

    def test_start_by_name_passes_version(self):
        rt = _make_runtime()
        with patch.object(rt, "_start_by_name") as mock:
            mock.return_value = MagicMock()
            rt.start("wf_name", "prompt", version=5)
        assert mock.call_args[1].get("version") == 5
