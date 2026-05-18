# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for AgentRuntime.resume() and resume_async()."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentspan.agents.agent import Agent
from agentspan.agents.result import AgentHandle, AgentStatus


# ── AgentHandle.run_id ──────────────────────────────────────────────────


class TestAgentHandleRunId:
    """AgentHandle stores run_id when provided."""

    def test_run_id_defaults_to_none(self):
        handle = AgentHandle(execution_id="wf-001", runtime=None)
        assert handle.run_id is None

    def test_run_id_stored_when_provided(self):
        handle = AgentHandle(execution_id="wf-001", runtime=None, run_id="abc123")
        assert handle.run_id == "abc123"


# ── AgentHandle.resume() calls _resume_workflow ─────────────────────────


class TestAgentHandleResumePause:
    """AgentHandle.resume() delegates to _resume_workflow (renamed internal)."""

    def test_handle_resume_calls_resume_workflow(self):
        mock_runtime = MagicMock()
        handle = AgentHandle(execution_id="wf-p", runtime=mock_runtime)
        handle.resume()
        mock_runtime._resume_workflow.assert_called_once_with("wf-p")

    @pytest.mark.asyncio
    async def test_handle_resume_async_calls_resume_workflow_async(self):
        mock_runtime = MagicMock()
        mock_runtime._resume_workflow_async = AsyncMock()
        handle = AgentHandle(execution_id="wf-p", runtime=mock_runtime)
        await handle.resume_async()
        mock_runtime._resume_workflow_async.assert_called_once_with("wf-p")


# ── _extract_domain ─────────────────────────────────────────────────────


class TestExtractDomain:
    """_extract_domain reads domain from the workflow's taskToDomain map."""

    def _make_runtime(self, task_to_domain=None):
        """Create a minimal AgentRuntime with mocked workflow client."""
        from agentspan.agents.runtime.runtime import AgentRuntime

        rt = AgentRuntime.__new__(AgentRuntime)
        mock_wf = MagicMock()
        mock_wf.task_to_domain = task_to_domain
        rt._workflow_client = MagicMock()
        rt._workflow_client.get_workflow = MagicMock(return_value=mock_wf)
        return rt

    def test_returns_none_for_stateless_agent(self):
        rt = self._make_runtime(task_to_domain={})
        assert rt._extract_domain("wf-1") is None

    def test_returns_none_when_no_task_to_domain(self):
        rt = self._make_runtime(task_to_domain=None)
        assert rt._extract_domain("wf-2") is None

    def test_returns_domain_for_stateful_agent(self):
        rt = self._make_runtime(
            task_to_domain={"tool_a": "deadbeef", "tool_b": "deadbeef"}
        )
        assert rt._extract_domain("wf-3") == "deadbeef"

    def test_returns_most_common_domain_when_multiple(self):
        rt = self._make_runtime(
            task_to_domain={"tool_a": "aaa", "tool_b": "bbb", "tool_c": "aaa"}
        )
        assert rt._extract_domain("wf-4") == "aaa"

    def test_returns_none_on_exception(self):
        from agentspan.agents.runtime.runtime import AgentRuntime

        rt = AgentRuntime.__new__(AgentRuntime)
        rt._workflow_client = MagicMock()
        rt._workflow_client.get_workflow = MagicMock(side_effect=Exception("server down"))
        assert rt._extract_domain("wf-5") is None


# ── resume() ────────────────────────────────────────────────────────────


class TestResume:
    """AgentRuntime.resume() re-registers workers under the correct domain."""

    def _make_runtime(self, task_to_domain=None):
        from agentspan.agents.runtime.runtime import AgentRuntime

        rt = AgentRuntime.__new__(AgentRuntime)
        mock_wf = MagicMock()
        mock_wf.task_to_domain = task_to_domain
        rt._workflow_client = MagicMock()
        rt._workflow_client.get_workflow = MagicMock(return_value=mock_wf)
        rt._prepare_workers = MagicMock()
        return rt

    def test_resume_stateless_registers_workers_without_domain(self):
        rt = self._make_runtime(task_to_domain={})
        agent = Agent(name="bot", model="openai/gpt-4o")

        handle = rt.resume("wf-1", agent)

        rt._prepare_workers.assert_called_once_with(agent, domain=None)
        assert isinstance(handle, AgentHandle)
        assert handle.execution_id == "wf-1"
        assert handle.run_id is None

    def test_resume_stateful_registers_workers_with_domain(self):
        rt = self._make_runtime(
            task_to_domain={"my_tool": "deadbeef", "other_tool": "deadbeef"}
        )
        agent = Agent(name="bot", model="openai/gpt-4o")

        handle = rt.resume("wf-2", agent)

        rt._prepare_workers.assert_called_once_with(agent, domain="deadbeef")
        assert handle.execution_id == "wf-2"
        assert handle.run_id == "deadbeef"

    def test_resume_returns_handle_bound_to_runtime(self):
        rt = self._make_runtime(task_to_domain={})
        agent = Agent(name="bot", model="openai/gpt-4o")

        handle = rt.resume("wf-3", agent)

        assert handle._runtime is rt


class TestResumeAsync:
    """resume_async() mirrors resume() behavior."""

    @pytest.mark.asyncio
    async def test_resume_async_registers_workers_with_domain(self):
        from agentspan.agents.runtime.runtime import AgentRuntime

        rt = AgentRuntime.__new__(AgentRuntime)
        mock_wf = MagicMock()
        mock_wf.task_to_domain = {"tool_x": "cafe0123"}
        rt._workflow_client = MagicMock()
        rt._workflow_client.get_workflow = MagicMock(return_value=mock_wf)
        rt._prepare_workers = MagicMock()

        agent = Agent(name="bot", model="openai/gpt-4o")

        handle = await rt.resume_async("wf-a1", agent)

        rt._prepare_workers.assert_called_once_with(agent, domain="cafe0123")
        assert handle.run_id == "cafe0123"
        assert handle.execution_id == "wf-a1"


# ── Public exports ──────────────────────────────────────────────────────


class TestResumePublicExport:
    """resume and resume_async are exported from agentspan.agents."""

    def test_resume_importable(self):
        from agentspan.agents import resume  # noqa: F401

    def test_resume_async_importable(self):
        from agentspan.agents import resume_async  # noqa: F401


class TestResumeConvenienceFunction:
    """Top-level resume() delegates to AgentRuntime.resume()."""

    def test_resume_delegates_to_runtime(self):
        from agentspan.agents.run import resume

        mock_runtime = MagicMock()
        mock_runtime.resume.return_value = AgentHandle(
            execution_id="wf-1", runtime=mock_runtime, run_id="abc"
        )
        agent = Agent(name="bot", model="openai/gpt-4o")

        handle = resume("wf-1", agent, runtime=mock_runtime)

        mock_runtime.resume.assert_called_once_with("wf-1", agent)
        assert handle.execution_id == "wf-1"

    @pytest.mark.asyncio
    async def test_resume_async_delegates_to_runtime(self):
        from agentspan.agents.run import resume_async

        mock_runtime = MagicMock()
        mock_runtime.resume_async = AsyncMock(
            return_value=AgentHandle(execution_id="wf-2", runtime=mock_runtime)
        )
        agent = Agent(name="bot", model="openai/gpt-4o")

        handle = await resume_async("wf-2", agent, runtime=mock_runtime)

        mock_runtime.resume_async.assert_called_once_with("wf-2", agent)
