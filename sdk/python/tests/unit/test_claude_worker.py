# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

# sdk/python/tests/unit/test_claude_worker.py
"""Tests for make_claude_worker — the Tier 1/2/3 passthrough worker factory."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from agentspan.agents.frameworks.claude import (
    ClaudeCodeAgent,
    _AgentspanEventClient,
    _ConductorSubagentClient,
    make_claude_worker,
    make_subagent_hook,
)
from agentspan.agents.runtime.runtime import AgentRuntime


def _make_task(prompt="hello", cwd=".", workflow_id="wf-123"):
    task = MagicMock()
    task.workflow_instance_id = workflow_id
    task.input_data = {"prompt": prompt, "cwd": cwd}
    return task


class TestMakeClaudeWorker:
    def test_returns_callable(self):
        agent = ClaudeCodeAgent(name="test", allowed_tools=["Read"])
        worker = make_claude_worker(agent, "_fw_claude_test", "http://localhost", "", "")
        assert callable(worker)

    def test_worker_uses_prompt_from_task(self):
        """Worker passes task prompt to query()."""
        agent = ClaudeCodeAgent(name="test", allowed_tools=["Read"])
        worker = make_claude_worker(agent, "_fw_claude_test", "http://localhost", "", "")

        captured_prompts = []

        async def fake_query(prompt, options):
            captured_prompts.append(prompt)
            yield MagicMock(subtype="init", session_id="sess-001")
            result = MagicMock()
            result.__class__.__name__ = "ResultMessage"
            result.result = "done"
            yield result

        with (
            patch("agentspan.agents.frameworks.claude.query", fake_query),
            patch("agentspan.agents.frameworks.claude._restore_session", return_value=None),
            patch("agentspan.agents.frameworks.claude._checkpoint_session"),
        ):
            task = _make_task(prompt="fix the bug", cwd="/workspace")
            worker(task)

        assert captured_prompts == ["fix the bug"]

    def test_worker_returns_completed_on_success(self):
        agent = ClaudeCodeAgent(name="test")
        worker = make_claude_worker(agent, "_fw_claude_test", "http://localhost", "", "")

        async def fake_query(prompt, options):
            yield MagicMock(subtype="init", session_id="sess-001")
            result = MagicMock()
            result.__class__.__name__ = "ResultMessage"
            result.result = "task result"
            yield result

        with (
            patch("agentspan.agents.frameworks.claude.query", fake_query),
            patch("agentspan.agents.frameworks.claude._restore_session", return_value=None),
            patch("agentspan.agents.frameworks.claude._checkpoint_session"),
        ):
            task = _make_task()
            task_result = worker(task)

        assert task_result.status.name == "COMPLETED"
        assert task_result.output_data["result"] == "task result"

    def test_worker_returns_failed_on_exception(self):
        agent = ClaudeCodeAgent(name="test")
        worker = make_claude_worker(agent, "_fw_claude_test", "http://localhost", "", "")

        async def fake_query(prompt, options):
            raise RuntimeError("SDK crashed")
            yield  # make it a generator

        with (
            patch("agentspan.agents.frameworks.claude.query", fake_query),
            patch("agentspan.agents.frameworks.claude._restore_session", return_value=None),
        ):
            task = _make_task()
            task_result = worker(task)

        assert task_result.status.name == "FAILED"

    def test_pre_tool_hook_pushes_tool_call_event(self):
        """PreToolUse hook calls _push_event_nonblocking with tool_call type."""
        agent = ClaudeCodeAgent(name="test", allowed_tools=["Bash"])
        worker = make_claude_worker(agent, "_fw_claude_test", "http://localhost:8080", "", "")

        captured_events = []

        async def fake_query(prompt, options):
            # Simulate PreToolUse hook firing
            hook = options.hooks["PreToolUse"][0].hooks[0]
            input_data = {"tool_name": "Bash", "tool_input": {"command": "ls"}}
            await hook(input_data, "tu-001", {})

            yield MagicMock(subtype="init", session_id="sess-001")
            result = MagicMock()
            result.__class__.__name__ = "ResultMessage"
            result.result = "done"
            yield result

        def fake_push(workflow_id, event_type, payload, server_url, headers):
            captured_events.append((event_type, payload))

        with (
            patch("agentspan.agents.frameworks.claude.query", fake_query),
            patch("agentspan.agents.frameworks.claude._restore_session", return_value=None),
            patch("agentspan.agents.frameworks.claude._checkpoint_session"),
            patch("agentspan.agents.frameworks.claude._push_event_nonblocking", fake_push),
        ):
            worker(_make_task())

        assert any(e[0] == "tool_call" and e[1]["toolName"] == "Bash" for e in captured_events)

    def test_session_id_pre_populated_from_restore(self):
        """session_id_ref is pre-populated from restored session so first PostToolUse
        checkpoint works even if SDK skips re-emitting SystemMessage(init)."""
        agent = ClaudeCodeAgent(name="test")
        worker = make_claude_worker(agent, "_fw_claude_test", "http://localhost:8080", "", "")

        checkpointed_with = []

        async def fake_query(prompt, options):
            # Simulate PostToolUse without prior init message (resume scenario)
            hook = options.hooks["PostToolUse"][0].hooks[0]
            input_data = {
                "tool_name": "Read",
                "tool_input": {"file_path": "a.py"},
                "tool_response": "content",
            }
            await hook(input_data, "tu-002", {})

            result = MagicMock()
            result.__class__.__name__ = "ResultMessage"
            result.result = "done"
            yield result

        def fake_checkpoint(wf_id, session_id, cwd, server_url, headers):
            checkpointed_with.append(session_id)

        with (
            patch("agentspan.agents.frameworks.claude.query", fake_query),
            patch(
                "agentspan.agents.frameworks.claude._restore_session",
                return_value="restored-session-id",
            ),
            patch("agentspan.agents.frameworks.claude._checkpoint_session", fake_checkpoint),
            patch("agentspan.agents.frameworks.claude._push_event_nonblocking"),
        ):
            worker(_make_task())

        # Must checkpoint with the restored session ID, not None
        assert all(s == "restored-session-id" for s in checkpointed_with)
        assert len(checkpointed_with) >= 1


class TestRuntimePassthroughDispatch:
    def test_build_passthrough_func_handles_claude(self):
        """_build_passthrough_func must not raise ValueError for 'claude'."""
        agent = ClaudeCodeAgent(name="rt_test", allowed_tools=["Read"])
        runtime = AgentRuntime.__new__(AgentRuntime)
        runtime._config = MagicMock()
        runtime._config.server_url = "http://localhost:8080"
        runtime._config.auth_key = ""
        runtime._config.auth_secret = ""

        func = runtime._build_passthrough_func(agent, "claude", "_fw_claude_rt_test")
        assert callable(func)


# ── Tier 2/3 helper client tests ───────────────────────────────────────────────


def _mock_httpx_cm(mock_client):
    """Return a mock that acts as `async with httpx.AsyncClient(...) as client:`."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


class TestConductorSubagentClient:
    def test_start_workflow_posts_to_correct_url_and_returns_id(self):
        conductor = _ConductorSubagentClient("http://server:8080", "k", "s")

        mock_resp = MagicMock()
        mock_resp.text = '"wf-abc-123"'
        mock_resp.raise_for_status = MagicMock()
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", _mock_httpx_cm(mock_http)):
            result = asyncio.run(conductor.start_workflow("my_wf", {"prompt": "go"}))

        mock_http.post.assert_called_once()
        url = mock_http.post.call_args[0][0]
        assert "my_wf" in url
        assert result == "wf-abc-123"  # JSON-quotes stripped

    def test_poll_until_done_returns_output_on_completed(self):
        conductor = _ConductorSubagentClient("http://server:8080", "k", "s")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "COMPLETED", "output": {"result": "done!"}}
        mock_resp.raise_for_status = MagicMock()
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", _mock_httpx_cm(mock_http)):
            result = asyncio.run(conductor.poll_until_done("wf-abc"))

        assert result == "done!"

    def test_poll_until_done_raises_on_failed_status(self):
        import pytest

        conductor = _ConductorSubagentClient("http://server:8080", "k", "s")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "FAILED"}
        mock_resp.raise_for_status = MagicMock()
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", _mock_httpx_cm(mock_http)):
            with pytest.raises(RuntimeError, match="FAILED"):
                asyncio.run(conductor.poll_until_done("wf-abc"))


class TestAgentspanEventClient:
    def test_push_posts_to_correct_url_with_payload(self):
        events = _AgentspanEventClient("http://server:8080", "k", "s")

        mock_http = AsyncMock()
        mock_http.post = AsyncMock()

        with patch("httpx.AsyncClient", _mock_httpx_cm(mock_http)):
            asyncio.run(events.push("wf-123", "tool_call", {"toolName": "Bash"}))

        mock_http.post.assert_called_once()
        url = mock_http.post.call_args[0][0]
        body = mock_http.post.call_args[1]["json"]
        assert "wf-123" in url
        assert body["type"] == "tool_call"
        assert body["toolName"] == "Bash"

    def test_push_silently_swallows_exceptions(self):
        events = _AgentspanEventClient("http://server:8080", "k", "s")

        bad_cm = MagicMock()
        bad_cm.__aenter__ = AsyncMock(side_effect=Exception("network error"))
        bad_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", MagicMock(return_value=bad_cm)):
            asyncio.run(events.push("wf-123", "tool_call", {}))  # must not raise


# ── Tier 2 subagent hook tests ─────────────────────────────────────────────────


class TestMakeSubagentHook:
    def test_non_agent_tool_passes_through(self):
        conductor = AsyncMock()
        events = AsyncMock()
        hook = make_subagent_hook("my_wf", "wf-1", conductor, events)

        result = asyncio.run(hook({"tool_name": "Read"}, "tu-1", {}))

        assert result == {}
        conductor.start_workflow.assert_not_called()

    def test_agent_tool_starts_workflow_and_returns_deny(self):
        conductor = AsyncMock()
        conductor.start_workflow = AsyncMock(return_value="sub-wf-001")
        conductor.poll_until_done = AsyncMock(return_value="subagent result")
        events = AsyncMock()
        events.push = AsyncMock()

        hook = make_subagent_hook("my_wf", "wf-1", conductor, events)
        result = asyncio.run(
            hook({"tool_name": "Agent", "tool_input": {"prompt": "do something"}}, "tu-2", {})
        )

        conductor.start_workflow.assert_called_once_with("my_wf", {"prompt": "do something"})
        conductor.poll_until_done.assert_called_once_with("sub-wf-001")
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert result["hookSpecificOutput"]["permissionDecisionReason"] == "subagent result"

    def test_agent_tool_pushes_subagent_start_and_stop_events(self):
        conductor = AsyncMock()
        conductor.start_workflow = AsyncMock(return_value="sub-wf-001")
        conductor.poll_until_done = AsyncMock(return_value="done")
        events = AsyncMock()
        events.push = AsyncMock()

        hook = make_subagent_hook("my_wf", "wf-1", conductor, events)
        asyncio.run(hook({"tool_name": "Agent", "tool_input": {"prompt": "do it"}}, "tu-3", {}))

        push_calls = events.push.call_args_list
        event_types = [call.args[1] for call in push_calls]
        assert "subagent_start" in event_types
        assert "subagent_stop" in event_types

    def test_agent_tool_handles_conductor_exception_gracefully(self):
        conductor = AsyncMock()
        conductor.start_workflow = AsyncMock(side_effect=RuntimeError("conductor down"))
        events = AsyncMock()

        hook = make_subagent_hook("my_wf", "wf-1", conductor, events)
        result = asyncio.run(
            hook({"tool_name": "Agent", "tool_input": {"prompt": "fail"}}, "tu-4", {})
        )

        # Must return deny with error message, not raise
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "conductor down" in result["hookSpecificOutput"]["permissionDecisionReason"]


# ── Tier 2 worker integration tests ───────────────────────────────────────────


class TestTier2ConductorSubagents:
    def test_pretooluse_has_two_matchers_including_agent(self):
        """conductor_subagents=True adds Agent-specific matcher to PreToolUse."""
        agent = ClaudeCodeAgent(name="t2", conductor_subagents=True)
        worker = make_claude_worker(agent, "_fw_claude_t2", "http://localhost", "k", "s")

        captured_hooks = {}

        async def fake_query(prompt, options, **kwargs):
            captured_hooks.update(options.hooks)
            yield MagicMock(subtype="init", session_id="s1")
            result = MagicMock()
            result.__class__.__name__ = "ResultMessage"
            result.result = "done"
            yield result

        with (
            patch("agentspan.agents.frameworks.claude.query", fake_query),
            patch("agentspan.agents.frameworks.claude._restore_session", return_value=None),
            patch("agentspan.agents.frameworks.claude._checkpoint_session"),
        ):
            worker(_make_task())

        assert len(captured_hooks["PreToolUse"]) == 2
        matchers = [m.matcher for m in captured_hooks["PreToolUse"]]
        assert "Agent" in matchers

    def test_no_transport_passed_when_only_tier2(self):
        """conductor_subagents=True alone does not pass transport= to query()."""
        agent = ClaudeCodeAgent(name="t2", conductor_subagents=True)
        worker = make_claude_worker(agent, "_fw_claude_t2", "http://localhost", "k", "s")

        captured_kwargs = {}

        async def fake_query(prompt, options, **kwargs):
            captured_kwargs.update(kwargs)
            yield MagicMock(subtype="init", session_id="s1")
            result = MagicMock()
            result.__class__.__name__ = "ResultMessage"
            result.result = "done"
            yield result

        with (
            patch("agentspan.agents.frameworks.claude.query", fake_query),
            patch("agentspan.agents.frameworks.claude._restore_session", return_value=None),
            patch("agentspan.agents.frameworks.claude._checkpoint_session"),
        ):
            worker(_make_task())

        assert "transport" not in captured_kwargs


# ── Tier 3 worker integration tests ───────────────────────────────────────────


class TestTier3AgentspanRouting:
    def test_transport_passed_to_query(self):
        """agentspan_routing=True passes AgentspanTransport as transport= to query()."""
        agent = ClaudeCodeAgent(name="t3", agentspan_routing=True)
        worker = make_claude_worker(agent, "_fw_claude_t3", "http://localhost", "k", "s")

        captured_kwargs = {}
        mock_transport = MagicMock()

        async def fake_query(prompt, options, **kwargs):
            captured_kwargs.update(kwargs)
            yield MagicMock(subtype="init", session_id="s1")
            result = MagicMock()
            result.__class__.__name__ = "ResultMessage"
            result.result = "done"
            yield result

        with (
            patch("agentspan.agents.frameworks.claude.query", fake_query),
            patch("agentspan.agents.frameworks.claude._restore_session", return_value=None),
            patch("agentspan.agents.frameworks.claude._checkpoint_session"),
            patch(
                "agentspan.agents.frameworks.claude_transport.AgentspanTransport",
                return_value=mock_transport,
            ),
        ):
            worker(_make_task())

        assert captured_kwargs.get("transport") is mock_transport

    def test_only_one_pretooluse_matcher_no_agent_hook(self):
        """agentspan_routing=True: transport handles Agent tool, so no extra hook."""
        agent = ClaudeCodeAgent(name="t3", agentspan_routing=True)
        worker = make_claude_worker(agent, "_fw_claude_t3", "http://localhost", "k", "s")

        captured_hooks = {}

        async def fake_query(prompt, options, **kwargs):
            captured_hooks.update(options.hooks)
            yield MagicMock(subtype="init", session_id="s1")
            result = MagicMock()
            result.__class__.__name__ = "ResultMessage"
            result.result = "done"
            yield result

        with (
            patch("agentspan.agents.frameworks.claude.query", fake_query),
            patch("agentspan.agents.frameworks.claude._restore_session", return_value=None),
            patch("agentspan.agents.frameworks.claude._checkpoint_session"),
            patch("agentspan.agents.frameworks.claude_transport.AgentspanTransport"),
        ):
            worker(_make_task())

        assert len(captured_hooks["PreToolUse"]) == 1

    def test_transport_receives_worker_name_as_workflow_name(self):
        """AgentspanTransport is constructed with _worker_name=name."""
        agent = ClaudeCodeAgent(name="t3", agentspan_routing=True)
        worker = make_claude_worker(agent, "_fw_claude_t3", "http://localhost", "k", "s")

        captured_config = {}

        def fake_transport(agent_config, **kwargs):
            captured_config.update(agent_config)
            return MagicMock()

        async def fake_query(prompt, options, **kwargs):
            yield MagicMock(subtype="init", session_id="s1")
            result = MagicMock()
            result.__class__.__name__ = "ResultMessage"
            result.result = "done"
            yield result

        with (
            patch("agentspan.agents.frameworks.claude.query", fake_query),
            patch("agentspan.agents.frameworks.claude._restore_session", return_value=None),
            patch("agentspan.agents.frameworks.claude._checkpoint_session"),
            patch(
                "agentspan.agents.frameworks.claude_transport.AgentspanTransport",
                side_effect=fake_transport,
            ),
        ):
            worker(_make_task())

        assert captured_config["_worker_name"] == "_fw_claude_t3"
