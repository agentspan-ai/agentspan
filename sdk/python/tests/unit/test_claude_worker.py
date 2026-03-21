# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

# sdk/python/tests/unit/test_claude_worker.py
"""Tests for make_claude_worker — the Tier 1/2/3 passthrough worker factory."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from agentspan.agents.frameworks.claude import (
    ClaudeCodeAgent,
    make_claude_worker,
)
from agentspan.agents.runtime.runtime import AgentRuntime


def _make_task(prompt="hello", cwd=".", workflow_id="wf-123"):
    task = MagicMock()
    task.workflow_instance_id = workflow_id
    task.task_id = "task-1"
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

    def test_pre_tool_hook_injects_dag_task(self):
        """PreToolUse hook calls inject_task on the DAG client for each tool call."""
        agent = ClaudeCodeAgent(name="test", allowed_tools=["Bash"])
        worker = make_claude_worker(agent, "_fw_claude_test", "http://localhost:8080", "", "")

        mock_dag = AsyncMock()
        mock_dag.inject_task = AsyncMock(return_value="task-id-1")

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

        with (
            patch("agentspan.agents.frameworks.claude.query", fake_query),
            patch("agentspan.agents.frameworks.claude._restore_session", return_value=None),
            patch("agentspan.agents.frameworks.claude._checkpoint_session"),
            patch("agentspan.agents.frameworks.claude._AgentDagClient", return_value=mock_dag),
        ):
            worker(_make_task())

        mock_dag.inject_task.assert_called_once()
        call_args = mock_dag.inject_task.call_args[0]
        assert call_args[1] == "Bash"
        assert call_args[3] == {"command": "ls"}

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

        mock_dag = AsyncMock()
        mock_dag.complete_task = AsyncMock()

        with (
            patch("agentspan.agents.frameworks.claude.query", fake_query),
            patch(
                "agentspan.agents.frameworks.claude._restore_session",
                return_value="restored-session-id",
            ),
            patch("agentspan.agents.frameworks.claude._checkpoint_session", fake_checkpoint),
            patch("agentspan.agents.frameworks.claude._AgentDagClient", return_value=mock_dag),
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


# ── ClaudeCodeAgent API tests ──────────────────────────────────────────────────


class TestClaudeCodeAgentFields:
    def test_mcp_tools_defaults_to_empty_list(self):
        """mcp_tools defaults to []."""
        from agentspan.agents.frameworks.claude import ClaudeCodeAgent

        agent = ClaudeCodeAgent(name="test")
        assert agent.mcp_tools == []

    def test_disallowed_tools_defaults_to_empty_list(self):
        """disallowed_tools defaults to []."""
        from agentspan.agents.frameworks.claude import ClaudeCodeAgent

        agent = ClaudeCodeAgent(name="test")
        assert agent.disallowed_tools == []

    def test_permission_mode_defaults_to_none(self):
        """permission_mode defaults to None."""
        from agentspan.agents.frameworks.claude import ClaudeCodeAgent

        agent = ClaudeCodeAgent(name="test")
        assert agent.permission_mode is None

    def test_accepts_mcp_tools_list(self):
        """mcp_tools accepts a list of callables."""
        from agentspan.agents.frameworks.claude import ClaudeCodeAgent

        def my_tool():
            pass

        my_tool._tool_def = object()

        agent = ClaudeCodeAgent(name="test", mcp_tools=[my_tool])
        assert agent.mcp_tools == [my_tool]


class TestMakeClaudeWorkerMcpWiring:
    """Tests that make_claude_worker wires AgentspanMcpServer correctly."""

    def _make_task(self, prompt="test", cwd="/tmp", workflow_id="wf-123", is_subagent=False):
        task = MagicMock()
        task.workflow_instance_id = workflow_id
        task.task_id = "task-1"
        task.input_data = {"prompt": prompt, "cwd": cwd}
        if is_subagent:
            task.input_data["_is_subagent"] = True
        return task

    def _fake_query(self, result="done"):
        async def _gen(*args, **kwargs):
            init = MagicMock()
            init.__class__.__name__ = "SystemMessage"
            init.subtype = "init"
            init.data = {"session_id": "sess-abc"}
            yield init

            rm = MagicMock()
            rm.__class__.__name__ = "ResultMessage"
            rm.result = result
            yield rm

        return _gen

    def test_mcp_server_built_when_mcp_tools_provided(self):
        """AgentspanMcpServer.build() called when agent has mcp_tools."""
        from agentspan.agents.frameworks.claude import ClaudeCodeAgent, make_claude_worker

        def dummy_tool(x: str) -> str:
            """Dummy."""
            return x

        td = MagicMock()
        td.name = "dummy_tool"
        td.description = "Dummy."
        td.input_schema = {
            "type": "object",
            "properties": {"x": {"type": "string"}},
            "required": ["x"],
        }
        dummy_tool._tool_def = td

        agent = ClaudeCodeAgent(name="test", mcp_tools=[dummy_tool])
        worker = make_claude_worker(agent, "_fw_claude_test", "http://localhost:8080/api", "", "")

        with (
            patch("agentspan.agents.frameworks.claude.query", self._fake_query()),
            patch("agentspan.agents.frameworks.claude._restore_session", return_value=None),
            patch("agentspan.agents.frameworks.claude._checkpoint_session"),
            patch(
                "agentspan.agents.frameworks.claude_mcp_server.AgentspanMcpServer.build"
            ) as mock_build,
        ):
            mock_build.return_value = {"type": "sdk", "name": "agentspan", "instance": MagicMock()}
            worker(self._make_task())
            mock_build.assert_called_once()

    def test_mcp_server_not_built_when_no_mcp_tools(self):
        """No MCP server built for plain Tier 1 agent (no mcp_tools)."""
        from agentspan.agents.frameworks.claude import ClaudeCodeAgent, make_claude_worker

        agent = ClaudeCodeAgent(name="test")  # no mcp_tools
        worker = make_claude_worker(agent, "_fw_claude_test", "http://localhost:8080/api", "", "")

        with (
            patch("agentspan.agents.frameworks.claude.query", self._fake_query()),
            patch("agentspan.agents.frameworks.claude._restore_session", return_value=None),
            patch("agentspan.agents.frameworks.claude._checkpoint_session"),
            patch("agentspan.agents.frameworks.claude_mcp_server.AgentspanMcpServer") as MockServer,
        ):
            worker(self._make_task())
            MockServer.assert_not_called()

    def test_no_mcp_server_when_no_mcp_tools(self):
        """No MCP server built when mcp_tools is empty."""
        from agentspan.agents.frameworks.claude import ClaudeCodeAgent, make_claude_worker

        agent = ClaudeCodeAgent(name="test")  # no mcp_tools
        worker = make_claude_worker(agent, "_fw_claude_test", "http://localhost:8080/api", "", "")

        with (
            patch("agentspan.agents.frameworks.claude.query", self._fake_query()),
            patch("agentspan.agents.frameworks.claude._restore_session", return_value=None),
            patch("agentspan.agents.frameworks.claude._checkpoint_session"),
            patch("agentspan.agents.frameworks.claude_mcp_server.AgentspanMcpServer") as MockServer,
        ):
            worker(self._make_task())
            MockServer.assert_not_called()

    def test_mcp_tool_executes_locally(self):
        """_mcp_wrapper calls tool_fn directly via asyncio.to_thread, not Conductor."""
        import agentspan.agents.frameworks.claude_mcp_server as mcp_mod

        call_log = []

        def echo_tool(msg: str) -> str:
            """Echo."""
            call_log.append(msg)
            return f"echo:{msg}"

        td = MagicMock()
        td.name = "echo_tool"
        td.description = "Echo."
        echo_tool._tool_def = td

        # Build without conductor/event clients (new simplified signature)
        server = mcp_mod.AgentspanMcpServer(tools=[echo_tool])
        config = server.build()

        # Call the registered MCP tool directly
        mcp_instance = config["instance"]
        # Get the wrapper via FastMCP internals
        tool_fn = None
        for tool in mcp_instance._tool_manager._tools.values():
            if tool.name == "echo_tool":
                tool_fn = tool.fn
                break

        assert tool_fn is not None
        result = asyncio.run(tool_fn(msg="hello"))
        assert result == "echo:hello"
        assert call_log == ["hello"]

    def test_mcp_servers_in_options_when_mcp_needed(self):
        """mcp_servers kwarg passed to ClaudeAgentOptions when MCP server built."""
        from agentspan.agents.frameworks.claude import ClaudeCodeAgent, make_claude_worker

        def dummy_tool(x: str) -> str:
            """Dummy."""
            return x

        td = MagicMock()
        td.name = "dummy_tool"
        td.description = "Dummy."
        dummy_tool._tool_def = td

        agent = ClaudeCodeAgent(name="test", mcp_tools=[dummy_tool])
        worker = make_claude_worker(agent, "_fw_claude_test", "http://localhost:8080/api", "", "")

        captured_options = {}

        async def fake_query(prompt, options, **kwargs):
            captured_options["options"] = options
            init = MagicMock()
            init.__class__.__name__ = "SystemMessage"
            init.subtype = "init"
            init.data = {"session_id": "sess-abc"}
            yield init
            rm = MagicMock()
            rm.__class__.__name__ = "ResultMessage"
            rm.result = "done"
            yield rm

        import agentspan.agents.frameworks.claude_mcp_server as mcp_mod

        with (
            patch("agentspan.agents.frameworks.claude.query", fake_query),
            patch("agentspan.agents.frameworks.claude._restore_session", return_value=None),
            patch("agentspan.agents.frameworks.claude._checkpoint_session"),
            patch.object(
                mcp_mod.AgentspanMcpServer,
                "build",
                return_value={"type": "sdk", "name": "agentspan", "instance": MagicMock()},
            ),
        ):
            task = MagicMock()
            task.workflow_instance_id = "wf-test"
            task.task_id = "t-1"
            task.input_data = {"prompt": "hello", "cwd": "/tmp"}
            worker(task)

        assert hasattr(captured_options["options"], "mcp_servers")
        assert "agentspan" in captured_options["options"].mcp_servers


# ── Dynamic DAG hook tests ─────────────────────────────────────────────────────


def _make_dag_task(workflow_id="wf-dag-1"):
    task = MagicMock()
    task.workflow_instance_id = workflow_id
    task.task_id = "dag-task-1"
    task.input_data = {"prompt": "hello", "cwd": "."}
    return task


class TestDagHooks:
    """Tests for hook-driven dynamic DAG construction."""

    def test_pre_tool_use_injects_simple_task(self):
        """PreToolUse hook calls inject_task and stores tool_use_id → task_id mapping."""
        from agentspan.agents.frameworks.claude import ClaudeCodeAgent, make_claude_worker

        agent = ClaudeCodeAgent(name="dag_test")
        worker = make_claude_worker(agent, "_fw_claude_dag_test", "http://localhost:8080", "", "")

        async def fake_query(prompt, options, **kwargs):
            hooks = options.hooks or {}
            pre_hook = hooks["PreToolUse"][0].hooks[0]
            input_data = {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "ls"},
                "session_id": "sess-001",
                "transcript_path": "/tmp/sess.jsonl",
                "cwd": ".",
            }
            await pre_hook(input_data, "tu-001", {})

            init = MagicMock()
            init.__class__.__name__ = "SystemMessage"
            init.subtype = "init"
            init.data = {"session_id": "sess-001"}
            yield init
            rm = MagicMock()
            rm.__class__.__name__ = "ResultMessage"
            rm.result = "done"
            yield rm

        mock_dag = AsyncMock()
        mock_dag.inject_task = AsyncMock(return_value="cond-t-1")

        with (
            patch("agentspan.agents.frameworks.claude.query", fake_query),
            patch("agentspan.agents.frameworks.claude._restore_session", return_value=None),
            patch("agentspan.agents.frameworks.claude._checkpoint_session"),
            patch("agentspan.agents.frameworks.claude._AgentDagClient", return_value=mock_dag),
        ):
            worker(_make_dag_task())

        mock_dag.inject_task.assert_called_once()
        call_args = mock_dag.inject_task.call_args
        assert call_args[0][0] == "wf-dag-1"  # workflow_id
        assert call_args[0][1] == "Bash"  # task_def_name
        assert call_args[0][2] == "tu-001"  # reference_name
        assert call_args[0][3] == {"command": "ls"}  # input_data

    def test_post_tool_use_completes_task(self):
        """PostToolUse hook calls complete_task with the stored task_id."""
        from agentspan.agents.frameworks.claude import ClaudeCodeAgent, make_claude_worker

        agent = ClaudeCodeAgent(name="dag_test")
        worker = make_claude_worker(agent, "_fw_claude_dag_test", "http://localhost:8080", "", "")

        mock_dag = AsyncMock()
        mock_dag.inject_task = AsyncMock(return_value="cond-t-1")
        mock_dag.complete_task = AsyncMock()

        async def fake_query(prompt, options, **kwargs):
            hooks = options.hooks or {}
            pre_hook = hooks["PreToolUse"][0].hooks[0]
            post_hook = hooks["PostToolUse"][0].hooks[0]

            input_data_pre = {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "ls"},
                "session_id": "sess-001",
                "transcript_path": "/tmp/sess.jsonl",
                "cwd": ".",
            }
            await pre_hook(input_data_pre, "tu-001", {})

            input_data_post = {
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "ls"},
                "tool_response": "file.txt",
                "session_id": "sess-001",
                "transcript_path": "/tmp/sess.jsonl",
                "cwd": ".",
            }
            await post_hook(input_data_post, "tu-001", {})

            init = MagicMock()
            init.__class__.__name__ = "SystemMessage"
            init.subtype = "init"
            init.data = {"session_id": "sess-001"}
            yield init
            rm = MagicMock()
            rm.__class__.__name__ = "ResultMessage"
            rm.result = "done"
            yield rm

        with (
            patch("agentspan.agents.frameworks.claude.query", fake_query),
            patch("agentspan.agents.frameworks.claude._restore_session", return_value=None),
            patch("agentspan.agents.frameworks.claude._checkpoint_session"),
            patch("agentspan.agents.frameworks.claude._AgentDagClient", return_value=mock_dag),
        ):
            worker(_make_dag_task())

        mock_dag.complete_task.assert_called_once()
        call_args = mock_dag.complete_task.call_args[0]
        assert call_args[0] == "wf-dag-1"  # workflow_id
        assert call_args[1] == "cond-t-1"  # task_id (from inject_task)
        assert call_args[2] == {"result": "file.txt"}

    def test_post_tool_use_failure_fails_task(self):
        """PostToolUseFailure hook calls fail_task with the error."""
        from agentspan.agents.frameworks.claude import ClaudeCodeAgent, make_claude_worker

        agent = ClaudeCodeAgent(name="dag_test")
        worker = make_claude_worker(agent, "_fw_claude_dag_test", "http://localhost:8080", "", "")

        mock_dag = AsyncMock()
        mock_dag.inject_task = AsyncMock(return_value="cond-t-1")
        mock_dag.fail_task = AsyncMock()

        async def fake_query(prompt, options, **kwargs):
            hooks = options.hooks or {}
            pre_hook = hooks["PreToolUse"][0].hooks[0]
            failure_hook = hooks["PostToolUseFailure"][0].hooks[0]

            await pre_hook(
                {
                    "hook_event_name": "PreToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "boom"},
                    "session_id": "sess-001",
                    "transcript_path": "/tmp/sess.jsonl",
                    "cwd": ".",
                },
                "tu-fail",
                {},
            )

            await failure_hook(
                {
                    "hook_event_name": "PostToolUseFailure",
                    "tool_name": "Bash",
                    "tool_input": {"command": "boom"},
                    "tool_use_id": "tu-fail",
                    "error": "exit code 1",
                    "session_id": "sess-001",
                    "transcript_path": "/tmp/sess.jsonl",
                    "cwd": ".",
                },
                "tu-fail",
                {},
            )

            init = MagicMock()
            init.__class__.__name__ = "SystemMessage"
            init.subtype = "init"
            init.data = {"session_id": "sess-001"}
            yield init
            rm = MagicMock()
            rm.__class__.__name__ = "ResultMessage"
            rm.result = "done"
            yield rm

        with (
            patch("agentspan.agents.frameworks.claude.query", fake_query),
            patch("agentspan.agents.frameworks.claude._restore_session", return_value=None),
            patch("agentspan.agents.frameworks.claude._checkpoint_session"),
            patch("agentspan.agents.frameworks.claude._AgentDagClient", return_value=mock_dag),
        ):
            worker(_make_dag_task())

        mock_dag.fail_task.assert_called_once()
        call_args = mock_dag.fail_task.call_args[0]
        assert call_args[0] == "wf-dag-1"
        assert call_args[1] == "cond-t-1"
        assert "exit code 1" in call_args[2]

    def test_agent_tool_creates_sub_workflow(self):
        """PreToolUse for Agent tool creates tracking workflow and injects SUB_WORKFLOW task."""
        from agentspan.agents.frameworks.claude import ClaudeCodeAgent, make_claude_worker

        agent = ClaudeCodeAgent(name="dag_test")
        worker = make_claude_worker(agent, "_fw_claude_dag_test", "http://localhost:8080", "", "")

        mock_dag = AsyncMock()
        mock_dag.create_tracking_workflow = AsyncMock(return_value="child-wf-1")
        mock_dag.inject_task = AsyncMock(return_value="sub-task-1")

        async def fake_query(prompt, options, **kwargs):
            hooks = options.hooks or {}
            pre_hook = hooks["PreToolUse"][0].hooks[0]

            await pre_hook(
                {
                    "hook_event_name": "PreToolUse",
                    "tool_name": "Agent",
                    "tool_input": {"prompt": "do something"},
                    "session_id": "sess-001",
                    "transcript_path": "/tmp/sess.jsonl",
                    "cwd": ".",
                },
                "tu-agent-1",
                {},
            )

            init = MagicMock()
            init.__class__.__name__ = "SystemMessage"
            init.subtype = "init"
            init.data = {"session_id": "sess-001"}
            yield init
            rm = MagicMock()
            rm.__class__.__name__ = "ResultMessage"
            rm.result = "done"
            yield rm

        with (
            patch("agentspan.agents.frameworks.claude.query", fake_query),
            patch("agentspan.agents.frameworks.claude._restore_session", return_value=None),
            patch("agentspan.agents.frameworks.claude._checkpoint_session"),
            patch("agentspan.agents.frameworks.claude._AgentDagClient", return_value=mock_dag),
        ):
            worker(_make_dag_task())

        mock_dag.create_tracking_workflow.assert_called_once()
        wf_name = mock_dag.create_tracking_workflow.call_args[0][0]
        assert "_fw_claude" in wf_name

        mock_dag.inject_task.assert_called_once()
        inj_args = mock_dag.inject_task.call_args
        assert inj_args[0][4] == "SUB_WORKFLOW"  # task_type
        sub_param = inj_args[1].get("sub_workflow_param")
        assert sub_param is not None, "sub_workflow_param must be passed as keyword arg"
        assert sub_param["workflowId"] == "child-wf-1"

    def test_subagent_stop_completes_sub_workflow_task(self):
        """SubagentStop with matching tool_use_id completes the SUB_WORKFLOW task."""
        from agentspan.agents.frameworks.claude import ClaudeCodeAgent, make_claude_worker

        agent = ClaudeCodeAgent(name="dag_test")
        worker = make_claude_worker(agent, "_fw_claude_dag_test", "http://localhost:8080", "", "")

        mock_dag = AsyncMock()
        mock_dag.create_tracking_workflow = AsyncMock(return_value="child-wf-1")
        mock_dag.inject_task = AsyncMock(return_value="sub-task-1")
        mock_dag.complete_task = AsyncMock()

        async def fake_query(prompt, options, **kwargs):
            hooks = options.hooks or {}
            pre_hook = hooks["PreToolUse"][0].hooks[0]
            stop_hook = hooks["SubagentStop"][0].hooks[0]

            # Subagent spawns via Agent tool
            await pre_hook(
                {
                    "hook_event_name": "PreToolUse",
                    "tool_name": "Agent",
                    "tool_input": {"prompt": "do something"},
                    "session_id": "sess-001",
                    "transcript_path": "/tmp/sess.jsonl",
                    "cwd": ".",
                },
                "tu-agent-sub",
                {},
            )

            # SubagentStop fires with same tool_use_id
            await stop_hook(
                {
                    "hook_event_name": "SubagentStop",
                    "stop_hook_active": False,
                    "session_id": "sess-sub-001",
                    "transcript_path": "/tmp/sub-sess.jsonl",
                    "cwd": ".",
                },
                "tu-agent-sub",
                {},
            )

            init = MagicMock()
            init.__class__.__name__ = "SystemMessage"
            init.subtype = "init"
            init.data = {"session_id": "sess-001"}
            yield init
            rm = MagicMock()
            rm.__class__.__name__ = "ResultMessage"
            rm.result = "done"
            yield rm

        with (
            patch("agentspan.agents.frameworks.claude.query", fake_query),
            patch("agentspan.agents.frameworks.claude._restore_session", return_value=None),
            patch("agentspan.agents.frameworks.claude._checkpoint_session"),
            patch("agentspan.agents.frameworks.claude._AgentDagClient", return_value=mock_dag),
            patch(
                "agentspan.agents.frameworks.claude._read_last_result_from_transcript",
                return_value="subagent result",
            ),
        ):
            worker(_make_dag_task())

        # complete_task should be called for the sub-workflow task
        mock_dag.complete_task.assert_called_once()
        call_args = mock_dag.complete_task.call_args[0]
        assert call_args[0] == "wf-dag-1"  # correct workflow
        assert call_args[1] == "sub-task-1"
        assert call_args[2] == {"result": "subagent result"}

    def test_hook_failure_is_non_fatal(self):
        """If inject_task raises, Claude continues normally (hook failure is swallowed)."""
        from agentspan.agents.frameworks.claude import ClaudeCodeAgent, make_claude_worker

        agent = ClaudeCodeAgent(name="dag_test")
        worker = make_claude_worker(agent, "_fw_claude_dag_test", "http://localhost:8080", "", "")

        mock_dag = AsyncMock()
        mock_dag.inject_task = AsyncMock(side_effect=Exception("DAG server down"))

        async def fake_query(prompt, options, **kwargs):
            hooks = options.hooks or {}
            pre_hook = hooks["PreToolUse"][0].hooks[0]

            await pre_hook(
                {
                    "hook_event_name": "PreToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "ls"},
                    "session_id": "sess-001",
                    "transcript_path": "/tmp/sess.jsonl",
                    "cwd": ".",
                },
                "tu-001",
                {},
            )

            init = MagicMock()
            init.__class__.__name__ = "SystemMessage"
            init.subtype = "init"
            init.data = {"session_id": "sess-001"}
            yield init
            rm = MagicMock()
            rm.__class__.__name__ = "ResultMessage"
            rm.result = "done"
            yield rm

        with (
            patch("agentspan.agents.frameworks.claude.query", fake_query),
            patch("agentspan.agents.frameworks.claude._restore_session", return_value=None),
            patch("agentspan.agents.frameworks.claude._checkpoint_session"),
            patch("agentspan.agents.frameworks.claude._AgentDagClient", return_value=mock_dag),
        ):
            task_result = worker(_make_dag_task())

        # Worker must complete, not raise
        assert task_result.status.name == "COMPLETED"

    def test_post_tool_hook_failure_is_non_fatal(self):
        """complete_task raising must not propagate — worker still completes."""
        from agentspan.agents.frameworks.claude import ClaudeCodeAgent, make_claude_worker

        agent = ClaudeCodeAgent(name="dag_test")
        worker = make_claude_worker(agent, "_fw_claude_dag_test", "http://localhost:8080", "", "")

        mock_dag = AsyncMock()
        mock_dag.inject_task = AsyncMock(return_value="t-99")
        mock_dag.complete_task = AsyncMock(side_effect=RuntimeError("server down"))

        async def fake_query(prompt, options, **kwargs):
            hooks = options.hooks or {}
            pre_hook = hooks["PreToolUse"][0].hooks[0]
            post_hook = hooks["PostToolUse"][0].hooks[0]

            await pre_hook(
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": "ls"},
                },
                "tu-post-99",
                {},
            )
            await post_hook(
                {
                    "tool_response": "file.txt",
                },
                "tu-post-99",
                {},
            )

            init = MagicMock()
            init.__class__.__name__ = "SystemMessage"
            init.subtype = "init"
            init.data = {"session_id": "sess-001"}
            yield init
            rm = MagicMock()
            rm.__class__.__name__ = "ResultMessage"
            rm.result = "done"
            yield rm

        with (
            patch("agentspan.agents.frameworks.claude.query", fake_query),
            patch("agentspan.agents.frameworks.claude._restore_session", return_value=None),
            patch("agentspan.agents.frameworks.claude._checkpoint_session"),
            patch("agentspan.agents.frameworks.claude._AgentDagClient", return_value=mock_dag),
        ):
            task_result = worker(_make_dag_task())

        assert task_result.status.name == "COMPLETED"
