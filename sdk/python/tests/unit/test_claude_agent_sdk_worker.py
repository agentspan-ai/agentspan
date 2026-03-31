"""Unit tests for the Claude Agent SDK passthrough integration."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _make_options(system_prompt="You are a reviewer"):
    """Create a mock ClaudeCodeOptions (from claude-code-sdk package)."""
    options = MagicMock()
    type(options).__name__ = "ClaudeCodeOptions"
    options.system_prompt = system_prompt
    options.hooks = {}
    return options


def _make_task(prompt="Hello", session_id="", execution_id="wf-123", cwd=""):
    from conductor.client.http.models.task import Task

    task = MagicMock(spec=Task)
    task.input_data = {"prompt": prompt, "session_id": session_id, "cwd": cwd}
    task.workflow_instance_id = execution_id
    task.task_id = "task-456"
    return task


class TestSerializeClaudeAgentSdk:
    def test_returns_single_worker_with_func_none(self):
        from agentspan.agents.frameworks.claude_agent_sdk import serialize_claude_agent_sdk

        options = _make_options()
        raw_config, workers = serialize_claude_agent_sdk(options)

        assert len(workers) == 1
        assert workers[0].func is None

    def test_raw_config_has_name_and_worker_name(self):
        from agentspan.agents.frameworks.claude_agent_sdk import serialize_claude_agent_sdk

        options = _make_options()
        raw_config, workers = serialize_claude_agent_sdk(options)

        assert "name" in raw_config
        assert raw_config["_worker_name"] == raw_config["name"]

    def test_worker_has_prompt_input_schema(self):
        from agentspan.agents.frameworks.claude_agent_sdk import serialize_claude_agent_sdk

        options = _make_options()
        _, workers = serialize_claude_agent_sdk(options)

        schema = workers[0].input_schema
        assert schema["type"] == "object"
        assert "prompt" in schema["properties"]
        assert "session_id" in schema["properties"]

    def test_default_name_when_no_system_prompt(self):
        from agentspan.agents.frameworks.claude_agent_sdk import serialize_claude_agent_sdk

        options = _make_options(system_prompt=None)
        raw_config, _ = serialize_claude_agent_sdk(options)

        assert raw_config["name"] == "claude_agent_sdk_agent"


class TestMakeClaudeAgentSdkWorker:
    def test_worker_returns_completed_on_success(self):
        from agentspan.agents.frameworks.claude_agent_sdk import make_claude_agent_sdk_worker

        options = _make_options()
        task = _make_task(prompt="Review the code")

        with (
            patch("agentspan.agents.frameworks.claude_agent_sdk.asyncio") as mock_asyncio,
            patch("agentspan.agents.frameworks.claude_agent_sdk._push_event_nonblocking"),
        ):
            mock_asyncio.run.return_value = ("The code looks good", None)
            worker_fn = make_claude_agent_sdk_worker(
                options, "test_agent", "http://localhost:8080", "key", "secret"
            )
            result = worker_fn(task)

        assert result.status == "COMPLETED"
        assert result.output_data["result"] == "The code looks good"

    def test_worker_returns_failed_on_exception(self):
        from agentspan.agents.frameworks.claude_agent_sdk import make_claude_agent_sdk_worker

        options = _make_options()
        task = _make_task()

        with (
            patch("agentspan.agents.frameworks.claude_agent_sdk.asyncio") as mock_asyncio,
            patch("agentspan.agents.frameworks.claude_agent_sdk._push_event_nonblocking"),
        ):
            mock_asyncio.run.side_effect = RuntimeError("SDK error")
            worker_fn = make_claude_agent_sdk_worker(
                options, "test_agent", "http://localhost:8080", "key", "secret"
            )
            result = worker_fn(task)

        assert result.status == "FAILED"
        assert "SDK error" in result.reason_for_incompletion

    def test_worker_includes_metadata_in_output(self):
        from agentspan.agents.frameworks.claude_agent_sdk import make_claude_agent_sdk_worker

        options = _make_options()
        task = _make_task()

        with (
            patch("agentspan.agents.frameworks.claude_agent_sdk.asyncio") as mock_asyncio,
            patch("agentspan.agents.frameworks.claude_agent_sdk._push_event_nonblocking"),
        ):
            mock_asyncio.run.return_value = ("result", {"input_tokens": 100})
            worker_fn = make_claude_agent_sdk_worker(
                options, "test_agent", "http://localhost:8080", "key", "secret"
            )
            result = worker_fn(task)

        assert result.output_data["tool_call_count"] == 0
        assert result.output_data["tool_error_count"] == 0
        assert result.output_data["subagent_count"] == 0
        assert result.output_data["tools_used"] == []
        assert result.output_data["token_usage"] == {"input_tokens": 100}

    def test_worker_uses_cwd_from_task_input(self):
        from agentspan.agents.frameworks.claude_agent_sdk import make_claude_agent_sdk_worker

        options = _make_options()
        task = _make_task(cwd="/tmp/project")

        with (
            patch("agentspan.agents.frameworks.claude_agent_sdk.asyncio") as mock_asyncio,
            patch("agentspan.agents.frameworks.claude_agent_sdk._push_event_nonblocking"),
        ):
            mock_asyncio.run.return_value = ("done", None)
            worker_fn = make_claude_agent_sdk_worker(
                options, "test_agent", "http://localhost:8080", "key", "secret"
            )
            result = worker_fn(task)

        # Verify asyncio.run was called (the merged options are passed internally)
        assert mock_asyncio.run.called
        assert result.status == "COMPLETED"


class TestAgentspanHooks:
    def test_build_hooks_returns_dict_with_expected_keys(self):
        from agentspan.agents.frameworks.claude_agent_sdk import _build_agentspan_hooks

        metadata = {
            "tool_call_count": 0,
            "tool_error_count": 0,
            "subagent_count": 0,
            "tools_used": set(),
        }
        hooks = _build_agentspan_hooks("wf-1", "http://localhost", "k", "s", metadata)

        assert "PreToolUse" in hooks
        assert "PostToolUse" in hooks
        assert "SubagentStop" in hooks
        assert "Stop" in hooks

    def test_pre_tool_use_hook_increments_metadata(self):
        from agentspan.agents.frameworks.claude_agent_sdk import _build_agentspan_hooks

        metadata = {
            "tool_call_count": 0,
            "tool_error_count": 0,
            "subagent_count": 0,
            "tools_used": set(),
        }

        with patch("agentspan.agents.frameworks.claude_agent_sdk._push_event_nonblocking"):
            hooks = _build_agentspan_hooks("wf-1", "http://localhost", "k", "s", metadata)
            # HookMatcher is a dataclass — access .hooks attribute
            pre_matchers = hooks["PreToolUse"]
            pre_hook = pre_matchers[0].hooks[0]
            result = asyncio.run(
                pre_hook(
                    {"tool_name": "Read", "tool_input": {}, "hook_event_name": "PreToolUse"},
                    "tu-1",
                    None,
                )
            )

        assert metadata["tool_call_count"] == 1
        assert "Read" in metadata["tools_used"]
        assert result == {}

    def test_hooks_push_events(self):
        from agentspan.agents.frameworks.claude_agent_sdk import _build_agentspan_hooks

        pushed = []
        metadata = {
            "tool_call_count": 0,
            "tool_error_count": 0,
            "subagent_count": 0,
            "tools_used": set(),
        }

        def capture_push(exec_id, event, *args):
            pushed.append(event)

        with patch(
            "agentspan.agents.frameworks.claude_agent_sdk._push_event_nonblocking",
            side_effect=capture_push,
        ):
            hooks = _build_agentspan_hooks("wf-1", "http://localhost", "k", "s", metadata)
            pre_hook = hooks["PreToolUse"][0].hooks[0]
            asyncio.run(
                pre_hook(
                    {"tool_name": "Edit", "tool_input": {}, "hook_event_name": "PreToolUse"},
                    "tu-3",
                    None,
                )
            )

        assert len(pushed) == 1
        assert pushed[0]["type"] == "tool_call"
        assert pushed[0]["toolName"] == "Edit"
        assert pushed[0]["toolUseId"] == "tu-3"

    def test_post_tool_use_hook_pushes_event(self):
        from agentspan.agents.frameworks.claude_agent_sdk import _build_agentspan_hooks

        pushed = []
        metadata = {
            "tool_call_count": 0,
            "tool_error_count": 0,
            "subagent_count": 0,
            "tools_used": set(),
        }

        def capture_push(exec_id, event, *args):
            pushed.append(event)

        with patch(
            "agentspan.agents.frameworks.claude_agent_sdk._push_event_nonblocking",
            side_effect=capture_push,
        ):
            hooks = _build_agentspan_hooks("wf-1", "http://localhost", "k", "s", metadata)
            post_hook = hooks["PostToolUse"][0].hooks[0]
            asyncio.run(
                post_hook(
                    {"tool_name": "Bash", "tool_input": {}, "hook_event_name": "PostToolUse"},
                    "tu-5",
                    None,
                )
            )

        assert len(pushed) == 1
        assert pushed[0]["type"] == "tool_result"
        assert pushed[0]["toolName"] == "Bash"
        assert pushed[0]["toolUseId"] == "tu-5"

    def test_subagent_stop_hook_increments_count(self):
        from agentspan.agents.frameworks.claude_agent_sdk import _build_agentspan_hooks

        metadata = {
            "tool_call_count": 0,
            "tool_error_count": 0,
            "subagent_count": 0,
            "tools_used": set(),
        }

        with patch("agentspan.agents.frameworks.claude_agent_sdk._push_event_nonblocking"):
            hooks = _build_agentspan_hooks("wf-1", "http://localhost", "k", "s", metadata)
            subagent_hook = hooks["SubagentStop"][0].hooks[0]
            asyncio.run(subagent_hook({}, None, None))

        assert metadata["subagent_count"] == 1

    def test_stop_hook_pushes_agent_stop_event(self):
        from agentspan.agents.frameworks.claude_agent_sdk import _build_agentspan_hooks

        pushed = []
        metadata = {
            "tool_call_count": 0,
            "tool_error_count": 0,
            "subagent_count": 0,
            "tools_used": set(),
        }

        def capture_push(exec_id, event, *args):
            pushed.append(event)

        with patch(
            "agentspan.agents.frameworks.claude_agent_sdk._push_event_nonblocking",
            side_effect=capture_push,
        ):
            hooks = _build_agentspan_hooks("wf-1", "http://localhost", "k", "s", metadata)
            stop_hook = hooks["Stop"][0].hooks[0]
            asyncio.run(stop_hook({}, None, None))

        assert len(pushed) == 1
        assert pushed[0]["type"] == "agent_stop"

    def test_hooks_are_defensive(self):
        from agentspan.agents.frameworks.claude_agent_sdk import _build_agentspan_hooks

        metadata = {
            "tool_call_count": 0,
            "tool_error_count": 0,
            "subagent_count": 0,
            "tools_used": set(),
        }

        with patch(
            "agentspan.agents.frameworks.claude_agent_sdk._push_event_nonblocking",
            side_effect=RuntimeError("network down"),
        ):
            hooks = _build_agentspan_hooks("wf-1", "http://localhost", "k", "s", metadata)
            pre_hook = hooks["PreToolUse"][0].hooks[0]
            result = asyncio.run(
                pre_hook(
                    {"tool_name": "Read", "tool_input": {}, "hook_event_name": "PreToolUse"},
                    "tu-4",
                    None,
                )
            )

        assert result == {}
        # Metadata should still be updated even when push fails
        assert metadata["tool_call_count"] == 1


class TestMergeHooks:
    def test_merge_with_no_user_hooks(self):
        from agentspan.agents.frameworks.claude_agent_sdk import _merge_hooks
        from claude_code_sdk.types import HookMatcher as SdkHookMatcher

        options = _make_options()
        options.hooks = None

        agentspan_hooks = {"PreToolUse": [SdkHookMatcher(hooks=[lambda d, t, c: {}])]}
        merged = _merge_hooks(options, agentspan_hooks)

        result_hooks = merged.hooks if hasattr(merged, "hooks") else merged.get("hooks", {})
        assert len(result_hooks["PreToolUse"]) == 1

    def test_merge_preserves_user_hooks_first(self):
        from agentspan.agents.frameworks.claude_agent_sdk import _merge_hooks
        from claude_code_sdk.types import HookMatcher as SdkHookMatcher

        options = _make_options()
        user_matcher = SdkHookMatcher(matcher="Bash", hooks=[lambda d, t, c: {}])
        options.hooks = {"PreToolUse": [user_matcher]}

        agentspan_matcher = SdkHookMatcher(hooks=[lambda d, t, c: {}])
        agentspan_hooks = {"PreToolUse": [agentspan_matcher]}

        merged = _merge_hooks(options, agentspan_hooks)
        result_hooks = merged.hooks if hasattr(merged, "hooks") else merged.get("hooks", {})

        assert len(result_hooks["PreToolUse"]) == 2
        assert result_hooks["PreToolUse"][0] is user_matcher
        assert result_hooks["PreToolUse"][1] is agentspan_matcher

    def test_merge_combines_different_events(self):
        from agentspan.agents.frameworks.claude_agent_sdk import _merge_hooks
        from claude_code_sdk.types import HookMatcher as SdkHookMatcher

        options = _make_options()
        user_matcher = SdkHookMatcher(hooks=[lambda d, t, c: {}])
        options.hooks = {"Stop": [user_matcher]}

        agentspan_hooks = {"PreToolUse": [SdkHookMatcher(hooks=[lambda d, t, c: {}])]}

        merged = _merge_hooks(options, agentspan_hooks)
        result_hooks = merged.hooks if hasattr(merged, "hooks") else merged.get("hooks", {})

        assert "Stop" in result_hooks
        assert "PreToolUse" in result_hooks
        assert len(result_hooks["Stop"]) == 1
        assert len(result_hooks["PreToolUse"]) == 1


class TestRunQuery:
    def _mock_sdk_with_messages(self, messages):
        """Create a mock SDK where ClaudeSDKClient.receive_response yields messages."""

        async def mock_receive_response():
            for msg in messages:
                yield msg

        mock_sdk = MagicMock()
        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.receive_response = mock_receive_response
        mock_client.disconnect = AsyncMock()
        mock_sdk.ClaudeSDKClient.return_value = mock_client
        return mock_sdk

    def test_run_query_collects_assistant_text(self):
        from agentspan.agents.frameworks.claude_agent_sdk import _run_query

        text_block = MagicMock()
        text_block.text = "Hello world"
        assistant_msg = MagicMock()
        assistant_msg.__class__.__name__ = "AssistantMessage"
        assistant_msg.content = [text_block]

        result_msg = MagicMock()
        result_msg.__class__.__name__ = "ResultMessage"
        result_msg.result = "Final result"
        result_msg.usage = {"input_tokens": 50}

        mock_sdk = self._mock_sdk_with_messages([assistant_msg, result_msg])
        mock_sdk.AssistantMessage = type(assistant_msg)
        mock_sdk.ResultMessage = type(result_msg)

        with patch(
            "agentspan.agents.frameworks.claude_agent_sdk._import_sdk", return_value=mock_sdk
        ):
            output, usage = asyncio.run(_run_query("test prompt", MagicMock()))

        assert output == "Final result"
        assert usage == {"input_tokens": 50}

    def test_run_query_falls_back_to_collected_text(self):
        from agentspan.agents.frameworks.claude_agent_sdk import _run_query

        text_block = MagicMock()
        text_block.text = "Collected text"
        assistant_msg = MagicMock()
        assistant_msg.__class__.__name__ = "AssistantMessage"
        assistant_msg.content = [text_block]

        result_msg = MagicMock()
        result_msg.__class__.__name__ = "ResultMessage"
        result_msg.result = ""
        result_msg.usage = None

        mock_sdk = self._mock_sdk_with_messages([assistant_msg, result_msg])
        mock_sdk.AssistantMessage = type(assistant_msg)
        mock_sdk.ResultMessage = type(result_msg)

        with patch(
            "agentspan.agents.frameworks.claude_agent_sdk._import_sdk", return_value=mock_sdk
        ):
            output, usage = asyncio.run(_run_query("test prompt", MagicMock()))

        assert output == "Collected text"


class TestClaudeCodeConfig:
    def test_claude_code_model_resolution(self):
        from agentspan.agents.claude_code import resolve_claude_code_model

        assert resolve_claude_code_model("opus") == "claude-opus-4-6"
        assert resolve_claude_code_model("sonnet") == "claude-sonnet-4-6"
        assert resolve_claude_code_model("haiku") == "claude-haiku-4-5"
        assert resolve_claude_code_model("") is None
        assert resolve_claude_code_model("claude-opus-4-6") == "claude-opus-4-6"

    def test_claude_code_to_model_string(self):
        from agentspan.agents.claude_code import ClaudeCode

        assert ClaudeCode("opus").to_model_string() == "claude-code/opus"
        assert ClaudeCode().to_model_string() == "claude-code"

    def test_agent_with_claude_code_model_string(self):
        from agentspan.agents import Agent

        agent = Agent(name="test", model="claude-code/opus", instructions="test", tools=["Read"])
        assert agent.is_claude_code
        assert agent.model == "claude-code/opus"

    def test_agent_with_claude_code_config(self):
        from agentspan.agents import Agent, ClaudeCode

        agent = Agent(name="test", model=ClaudeCode("opus"), instructions="test", tools=["Read"])
        assert agent.is_claude_code
        assert agent.model == "claude-code/opus"
        assert agent._claude_code_config is not None

    def test_agent_claude_code_rejects_callable_tools(self):
        import pytest

        from agentspan.agents import Agent

        def my_tool():
            pass

        with pytest.raises(ValueError, match="Claude Code agents only support"):
            Agent(name="test", model="claude-code", instructions="test", tools=[my_tool])

    def test_agent_claude_code_allows_string_tools(self):
        from agentspan.agents import Agent

        agent = Agent(
            name="test", model="claude-code", instructions="test", tools=["Read", "Edit", "Bash"]
        )
        assert agent.tools == ["Read", "Edit", "Bash"]

    def test_detect_framework_returns_none_for_claude_code_agent(self):
        """Agent(model='claude-code/...') is a native Agent — the server handles
        claude-code routing during execution, not the framework detection path."""
        from agentspan.agents import Agent
        from agentspan.agents.frameworks.serializer import detect_framework

        agent = Agent(name="test", model="claude-code/opus", instructions="test", tools=["Read"])
        assert detect_framework(agent) is None

    def test_detect_framework_returns_none_for_normal_agent(self):
        from agentspan.agents import Agent
        from agentspan.agents.frameworks.serializer import detect_framework

        agent = Agent(name="test", model="openai/gpt-4o", instructions="test")
        assert detect_framework(agent) is None

    def test_agent_to_claude_code_options(self):
        from agentspan.agents import Agent, ClaudeCode
        from agentspan.agents.frameworks.claude_agent_sdk import agent_to_claude_code_options

        agent = Agent(
            name="reviewer",
            model=ClaudeCode("opus", permission_mode=ClaudeCode.PermissionMode.BYPASS),
            instructions="Review code",
            tools=["Read", "Grep"],
            max_turns=5,
        )
        options = agent_to_claude_code_options(agent)

        assert options.system_prompt == "Review code"
        assert options.allowed_tools == ["Read", "Grep"]
        assert options.max_turns == 5
        assert options.model == "claude-opus-4-6"
        assert options.permission_mode == "bypassPermissions"

    def test_claude_code_agent_goes_through_native_path(self):
        """Agent(model='claude-code/...') uses the native serialization path,
        not the framework serializer. The server handles passthrough compilation."""
        from agentspan.agents import Agent
        from agentspan.agents.frameworks.serializer import detect_framework

        agent = Agent(name="test", model="claude-code/opus", instructions="test", tools=["Read"])
        # Native agents return None from detect_framework
        assert detect_framework(agent) is None
        # The agent is still marked as claude-code
        assert agent.is_claude_code

    def test_agent_is_not_external_when_claude_code(self):
        from agentspan.agents import Agent

        agent = Agent(name="test", model="claude-code", instructions="test")
        assert not agent.external
        assert agent.is_claude_code

    def test_agent_decorator_with_claude_code_model(self):
        from agentspan.agents import agent as agent_decorator
        from agentspan.agents.agent import _resolve_agent
        from agentspan.agents.claude_code import ClaudeCode

        @agent_decorator(model=ClaudeCode("opus"), tools=["Read"])
        def reviewer():
            """Review code quality."""

        resolved = _resolve_agent(reviewer)
        assert resolved.is_claude_code
        assert resolved.model == "claude-code/opus"

    def test_config_serializer_emits_passthrough_for_claude_code(self):
        from agentspan.agents import Agent
        from agentspan.agents.config_serializer import AgentConfigSerializer

        agent = Agent(
            name="reviewer",
            model="claude-code/opus",
            instructions="Review code",
            tools=["Read"],
        )
        serializer = AgentConfigSerializer()
        config = serializer.serialize(agent)

        assert config["name"] == "reviewer"
        assert config["model"] == "claude-code/opus"
        assert config["metadata"]["_framework_passthrough"] is True
        assert len(config["tools"]) == 1
        assert config["tools"][0]["toolType"] == "worker"

    def test_config_serializer_parent_with_claude_code_sub_agent(self):
        from agentspan.agents import Agent
        from agentspan.agents.config_serializer import AgentConfigSerializer

        sub = Agent(
            name="reviewer",
            model="claude-code/opus",
            instructions="Review code",
            tools=["Read"],
        )
        parent = Agent(
            name="pipeline",
            model="openai/gpt-4o",
            instructions="Run pipeline",
            agents=[sub],
            strategy="sequential",
        )
        serializer = AgentConfigSerializer()
        config = serializer.serialize(parent)

        # Parent should be normal
        assert config["name"] == "pipeline"
        assert "metadata" not in config or "_framework_passthrough" not in config.get(
            "metadata", {}
        )

        # Sub-agent should be passthrough
        sub_config = config["agents"][0]
        assert sub_config["metadata"]["_framework_passthrough"] is True
