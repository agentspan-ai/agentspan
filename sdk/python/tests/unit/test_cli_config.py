# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tests for CLI command execution configuration and tool."""
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from agentspan.agents.cli_config import CliConfig, TerminalToolError, _make_cli_tool, _validate_cli_command


class TestCliConfig:
    """Test CliConfig dataclass."""

    def test_defaults(self):
        cfg = CliConfig()
        assert cfg.enabled is True
        assert cfg.allowed_commands == []
        assert cfg.timeout == 30
        assert cfg.working_dir is None
        assert cfg.allow_shell is False

    def test_custom_values(self):
        cfg = CliConfig(
            enabled=True,
            allowed_commands=["git", "gh"],
            timeout=60,
            working_dir="/tmp",
            allow_shell=True,
        )
        assert cfg.allowed_commands == ["git", "gh"]
        assert cfg.timeout == 60
        assert cfg.working_dir == "/tmp"
        assert cfg.allow_shell is True

    def test_disabled(self):
        cfg = CliConfig(enabled=False)
        assert cfg.enabled is False


class TestValidateCliCommand:
    """Test _validate_cli_command whitelist checker."""

    def test_allowed_command_passes(self):
        _validate_cli_command("git", ["git", "gh"])  # no exception

    def test_disallowed_command_raises(self):
        with pytest.raises(ValueError, match="not allowed"):
            _validate_cli_command("rm", ["git", "gh"])

    def test_path_normalization(self):
        _validate_cli_command("/usr/bin/git", ["git", "gh"])  # no exception

    def test_empty_whitelist_permits_all(self):
        _validate_cli_command("anything", [])  # no exception

    def test_error_message_lists_allowed(self):
        with pytest.raises(ValueError, match="gh, git"):
            _validate_cli_command("curl", ["git", "gh"])


class TestMakeCliTool:
    """Test _make_cli_tool factory."""

    def test_tool_has_correct_name(self):
        tool_fn = _make_cli_tool(allowed_commands=[])
        assert tool_fn._tool_def.name == "run_command"  # No agent prefix when agent_name=""

    def test_tool_has_agent_prefixed_name(self):
        tool_fn = _make_cli_tool(allowed_commands=["git"], agent_name="my_agent")
        assert tool_fn._tool_def.name == "my_agent_run_command"

    def test_tool_has_description(self):
        tool_fn = _make_cli_tool(allowed_commands=["git"])
        assert "run_command" in tool_fn._tool_def.name
        assert "git" in tool_fn._tool_def.description

    def test_disallowed_command_rejected(self):
        tool_fn = _make_cli_tool(allowed_commands=["git"])
        with pytest.raises(ValueError, match="not allowed"):
            tool_fn.__wrapped__(command="rm", args=["-rf", "/"])

    def test_shell_blocked_when_disabled(self):
        tool_fn = _make_cli_tool(allowed_commands=[], allow_shell=False)
        with pytest.raises(ValueError, match="Shell mode is disabled"):
            tool_fn.__wrapped__(command="echo", args=["hello"], shell=True)

    def test_shell_allowed_when_enabled(self):
        tool_fn = _make_cli_tool(allowed_commands=[], allow_shell=True)
        with patch("agentspan.agents.cli_config.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="hello\n", stderr=""
            )
            result = tool_fn.__wrapped__(command="echo", args=["hello"], shell=True)
            assert result["status"] == "success"
            mock_run.assert_called_once()
            # Should have been called with shell=True
            assert mock_run.call_args.kwargs.get("shell") is True

    def test_basic_execution(self):
        tool_fn = _make_cli_tool(allowed_commands=[])
        with patch("agentspan.agents.cli_config.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="output\n", stderr=""
            )
            result = tool_fn.__wrapped__(command="echo", args=["hello"])
            assert result == {
                "status": "success",
                "exit_code": 0,
                "stdout": "output\n",
                "stderr": "",
            }
            mock_run.assert_called_once_with(
                ["echo", "hello"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=None,
            )

    def test_nonzero_exit_code_returns_error_with_output(self):
        tool_fn = _make_cli_tool(allowed_commands=[])
        with patch("agentspan.agents.cli_config.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="partial output", stderr="error msg"
            )
            result = tool_fn.__wrapped__(command="false")
            assert result == {
                "status": "error",
                "exit_code": 1,
                "stdout": "partial output",
                "stderr": "error msg",
            }

    def test_nonzero_exit_code_preserves_stdout(self):
        """Verify the LLM sees stdout even when the command fails."""
        tool_fn = _make_cli_tool(allowed_commands=[])
        with patch("agentspan.agents.cli_config.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128,
                stdout="remote: Repository not found.\n",
                stderr="fatal: repository not found",
            )
            result = tool_fn.__wrapped__(command="git", args=["push"])
            assert result["status"] == "error"
            assert result["exit_code"] == 128
            assert "Repository not found" in result["stdout"]
            assert "fatal" in result["stderr"]

    def test_timeout_raises_terminal_error(self):
        tool_fn = _make_cli_tool(allowed_commands=[], timeout=5)
        with patch("agentspan.agents.cli_config.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="sleep", timeout=5)
            with pytest.raises(TerminalToolError, match="timed out"):
                tool_fn.__wrapped__(command="sleep", args=["100"])

    def test_command_not_found_raises_terminal_error(self):
        tool_fn = _make_cli_tool(allowed_commands=[])
        with patch("agentspan.agents.cli_config.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            with pytest.raises(TerminalToolError, match="not found"):
                tool_fn.__wrapped__(command="nonexistent")

    def test_cwd_override(self):
        tool_fn = _make_cli_tool(allowed_commands=[], working_dir="/default")
        with patch("agentspan.agents.cli_config.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="", stderr=""
            )
            # With cwd override
            tool_fn.__wrapped__(command="ls", cwd="/override")
            assert mock_run.call_args.kwargs["cwd"] == "/override"

            # Without cwd override, uses config working_dir
            tool_fn.__wrapped__(command="ls")
            assert mock_run.call_args.kwargs["cwd"] == "/default"

    def test_empty_command(self):
        tool_fn = _make_cli_tool(allowed_commands=[])
        result = tool_fn.__wrapped__(command="")
        assert result["status"] == "error"
        assert "No command" in result["stderr"]

    def test_custom_timeout_in_description(self):
        tool_fn = _make_cli_tool(allowed_commands=[], timeout=120)
        assert "120s" in tool_fn._tool_def.description

    def test_context_key_saves_stdout_on_success(self):
        from agentspan.agents.tool import ToolContext
        tool_fn = _make_cli_tool(allowed_commands=[])
        with patch("agentspan.agents.cli_config.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="/tmp/abc123\n", stderr=""
            )
            ctx = ToolContext(execution_id="test", agent_name="test", state={})
            result = tool_fn.__wrapped__(command="mktemp", args=["-d"], context_key="working_dir", context=ctx)
            assert result["status"] == "success"
            assert ctx.state["working_dir"] == "/tmp/abc123"

    def test_context_key_not_saved_on_failure(self):
        from agentspan.agents.tool import ToolContext
        tool_fn = _make_cli_tool(allowed_commands=[])
        with patch("agentspan.agents.cli_config.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="partial output", stderr="error"
            )
            ctx = ToolContext(execution_id="test", agent_name="test", state={})
            result = tool_fn.__wrapped__(command="false", context_key="result", context=ctx)
            assert result["status"] == "error"
            assert "result" not in ctx.state

    def test_context_key_with_internal_key_name(self):
        """context_key='_agent_state' should work without corrupting internals."""
        from agentspan.agents.tool import ToolContext
        tool_fn = _make_cli_tool(allowed_commands=[])
        with patch("agentspan.agents.cli_config.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="val\n", stderr="")
            ctx = ToolContext(execution_id="test", agent_name="test", state={})
            result = tool_fn.__wrapped__(command="echo", args=["val"], context_key="_agent_state", context=ctx)
            assert result["status"] == "success"
            assert ctx.state["_agent_state"] == "val"

    def test_context_key_falls_back_to_stderr(self):
        """When stdout is empty, context_key should fall back to stderr."""
        from agentspan.agents.tool import ToolContext
        tool_fn = _make_cli_tool(allowed_commands=[])
        with patch("agentspan.agents.cli_config.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="", stderr="Cloning into '/tmp/repo'...\n"
            )
            ctx = ToolContext(execution_id="test", agent_name="test", state={})
            result = tool_fn.__wrapped__(command="gh", args=["repo", "clone", "org/repo"], context_key="repo", context=ctx)
            assert result["status"] == "success"
            assert ctx.state["repo"] == "Cloning into '/tmp/repo'..."

    def test_context_key_empty_string_is_noop(self):
        """Empty context_key should not write anything."""
        from agentspan.agents.tool import ToolContext
        tool_fn = _make_cli_tool(allowed_commands=[])
        with patch("agentspan.agents.cli_config.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="val\n", stderr="")
            ctx = ToolContext(execution_id="test", agent_name="test", state={})
            tool_fn.__wrapped__(command="echo", context_key="", context=ctx)
            assert ctx.state == {}


class TestAgentCliIntegration:
    """Test Agent integration with CLI tools."""

    def test_cli_commands_true_attaches_tool(self):
        from agentspan.agents.agent import Agent

        agent = Agent(name="ops", model="openai/gpt-4o", cli_commands=True)
        tool_names = [t._tool_def.name for t in agent.tools if hasattr(t, "_tool_def")]
        assert any(n.endswith("_run_command") for n in tool_names)

    def test_cli_commands_false_no_tool(self):
        from agentspan.agents.agent import Agent

        agent = Agent(name="ops", model="openai/gpt-4o", cli_commands=False)
        tool_names = [t._tool_def.name for t in agent.tools if hasattr(t, "_tool_def")]
        assert not any(n.endswith("_run_command") for n in tool_names)

    def test_default_has_no_cli_tool(self):
        from agentspan.agents.agent import Agent

        agent = Agent(name="ops", model="openai/gpt-4o")
        tool_names = [t._tool_def.name for t in agent.tools if hasattr(t, "_tool_def")]
        assert not any(n.endswith("_run_command") for n in tool_names)

    def test_cli_allowed_commands_propagated(self):
        from agentspan.agents.agent import Agent

        agent = Agent(
            name="ops",
            model="openai/gpt-4o",
            cli_commands=True,
            cli_allowed_commands=["git", "gh"],
        )
        assert agent.cli_config is not None
        assert agent.cli_config.allowed_commands == ["git", "gh"]

    def test_cli_config_full_control(self):
        from agentspan.agents.agent import Agent

        cfg = CliConfig(
            allowed_commands=["docker"],
            timeout=120,
            allow_shell=True,
        )
        agent = Agent(name="ops", model="openai/gpt-4o", cli_config=cfg)
        assert agent.cli_config is cfg
        tool_names = [t._tool_def.name for t in agent.tools if hasattr(t, "_tool_def")]
        assert any(n.endswith("_run_command") for n in tool_names)

    def test_coexists_with_code_execution(self):
        from agentspan.agents.agent import Agent

        agent = Agent(
            name="ops",
            model="openai/gpt-4o",
            local_code_execution=True,
            cli_commands=True,
        )
        tool_names = [t._tool_def.name for t in agent.tools if hasattr(t, "_tool_def")]
        assert any(n.endswith("_execute_code") for n in tool_names)
        assert any(n.endswith("_run_command") for n in tool_names)

    def test_coexists_with_manual_tools(self):
        from agentspan.agents.agent import Agent
        from agentspan.agents.tool import tool

        @tool
        def search(query: str) -> str:
            """Search the web."""
            return query

        agent = Agent(
            name="ops",
            model="openai/gpt-4o",
            tools=[search],
            cli_commands=True,
        )
        tool_names = [t._tool_def.name for t in agent.tools if hasattr(t, "_tool_def")]
        assert "search" in tool_names
        assert any(n.endswith("_run_command") for n in tool_names)

    def test_agent_decorator_support(self):
        from agentspan.agents.agent import Agent, _resolve_agent, agent

        @agent(model="openai/gpt-4o", cli_commands=True, cli_allowed_commands=["git"])
        def my_agent():
            """An agent with CLI."""

        resolved = _resolve_agent(my_agent)
        assert isinstance(resolved, Agent)
        assert resolved.cli_config is not None
        assert resolved.cli_config.allowed_commands == ["git"]
        tool_names = [t._tool_def.name for t in resolved.tools if hasattr(t, "_tool_def")]
        assert any(n.endswith("_run_command") for n in tool_names)

    def test_cli_commands_fallback_to_allowed_commands(self):
        """When cli_commands=True with no cli_allowed_commands, falls back to allowed_commands."""
        from agentspan.agents.agent import Agent

        agent = Agent(
            name="ops",
            model="openai/gpt-4o",
            allowed_commands=["pip", "ls"],
            cli_commands=True,
        )
        assert agent.cli_config.allowed_commands == ["pip", "ls"]

    def test_cli_allowed_commands_takes_precedence(self):
        """cli_allowed_commands takes precedence over allowed_commands."""
        from agentspan.agents.agent import Agent

        agent = Agent(
            name="ops",
            model="openai/gpt-4o",
            allowed_commands=["pip", "ls"],
            cli_commands=True,
            cli_allowed_commands=["git"],
        )
        assert agent.cli_config.allowed_commands == ["git"]

    def test_disabled_cli_config_no_tool(self):
        from agentspan.agents.agent import Agent

        cfg = CliConfig(enabled=False, allowed_commands=["git"])
        agent = Agent(name="ops", model="openai/gpt-4o", cli_config=cfg)
        tool_names = [t._tool_def.name for t in agent.tools if hasattr(t, "_tool_def")]
        assert not any(n.endswith("_run_command") for n in tool_names)
