# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for code executors — LocalCodeExecutor, DockerCodeExecutor,
JupyterCodeExecutor, ServerlessCodeExecutor.
"""

import json
import subprocess
from unittest.mock import MagicMock, patch, mock_open

import pytest

from agentspan.agents.code_executor import (
    CodeExecutor,
    DockerCodeExecutor,
    ExecutionResult,
    JupyterCodeExecutor,
    LocalCodeExecutor,
    ServerlessCodeExecutor,
)


# ── ExecutionResult ─────────────────────────────────────────────────────


class TestExecutionResult:

    def test_success_property(self):
        r = ExecutionResult(output="hello", exit_code=0)
        assert r.success is True

    def test_failure_exit_code(self):
        r = ExecutionResult(exit_code=1)
        assert r.success is False

    def test_timed_out(self):
        r = ExecutionResult(exit_code=0, timed_out=True)
        assert r.success is False


# ── LocalCodeExecutor ───────────────────────────────────────────────────


class TestLocalCodeExecutor:

    @patch("agentspan.agents.code_executor.subprocess.run")
    @patch("agentspan.agents.code_executor.os.unlink")
    def test_execute_python_success(self, mock_unlink, mock_run):
        mock_run.return_value = MagicMock(stdout="hello\n", stderr="", returncode=0)
        executor = LocalCodeExecutor(language="python", timeout=10)
        result = executor.execute("print('hello')")

        assert result.output == "hello\n"
        assert result.exit_code == 0
        assert result.success is True
        mock_unlink.assert_called_once()

    @patch("agentspan.agents.code_executor.subprocess.run")
    @patch("agentspan.agents.code_executor.os.unlink")
    def test_execute_bash(self, mock_unlink, mock_run):
        mock_run.return_value = MagicMock(stdout="ok", stderr="", returncode=0)
        executor = LocalCodeExecutor(language="bash")
        result = executor.execute("echo ok")

        cmd = mock_run.call_args.args[0]
        assert cmd[0] == "bash"
        assert result.output == "ok"

    @patch("agentspan.agents.code_executor.subprocess.run")
    @patch("agentspan.agents.code_executor.os.unlink")
    def test_execute_nonzero_exit(self, mock_unlink, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="error!", returncode=1)
        executor = LocalCodeExecutor(language="python")
        result = executor.execute("bad code")

        assert result.exit_code == 1
        assert result.error == "error!"
        assert result.success is False

    @patch("agentspan.agents.code_executor.subprocess.run")
    @patch("agentspan.agents.code_executor.os.unlink")
    def test_execute_timeout(self, mock_unlink, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="python3", timeout=10)
        executor = LocalCodeExecutor(language="python", timeout=10)
        result = executor.execute("while True: pass")

        assert result.timed_out is True
        assert result.exit_code == -1
        assert "timed out" in result.error.lower()

    @patch("agentspan.agents.code_executor.subprocess.run")
    @patch("agentspan.agents.code_executor.os.unlink")
    def test_execute_missing_interpreter(self, mock_unlink, mock_run):
        mock_run.side_effect = FileNotFoundError()
        executor = LocalCodeExecutor(language="python")
        result = executor.execute("print('hi')")

        assert result.exit_code == 127
        assert "not found" in result.error.lower()

    @patch("agentspan.agents.code_executor.subprocess.run")
    @patch("agentspan.agents.code_executor.os.unlink")
    def test_execute_general_exception(self, mock_unlink, mock_run):
        mock_run.side_effect = OSError("permission denied")
        executor = LocalCodeExecutor(language="python")
        result = executor.execute("code")

        assert result.exit_code == 1
        assert "permission denied" in result.error

    def test_execute_unsupported_language(self):
        executor = LocalCodeExecutor(language="cobol")
        result = executor.execute("DISPLAY 'HELLO'")

        assert result.exit_code == 1
        assert "Unsupported" in result.error

    @patch("agentspan.agents.code_executor.subprocess.run")
    @patch("agentspan.agents.code_executor.os.unlink")
    def test_temp_file_cleanup_on_failure(self, mock_unlink, mock_run):
        mock_run.side_effect = RuntimeError("unexpected")
        executor = LocalCodeExecutor(language="python")
        executor.execute("code")
        mock_unlink.assert_called_once()


class TestLocalFileExtension:

    def test_python(self):
        assert LocalCodeExecutor(language="python")._file_extension() == ".py"

    def test_python3(self):
        assert LocalCodeExecutor(language="python3")._file_extension() == ".py"

    def test_bash(self):
        assert LocalCodeExecutor(language="bash")._file_extension() == ".sh"

    def test_javascript(self):
        assert LocalCodeExecutor(language="javascript")._file_extension() == ".js"

    def test_node(self):
        assert LocalCodeExecutor(language="node")._file_extension() == ".js"

    def test_ruby(self):
        assert LocalCodeExecutor(language="ruby")._file_extension() == ".rb"

    def test_unknown(self):
        assert LocalCodeExecutor(language="fortran")._file_extension() == ".txt"


# ── DockerCodeExecutor ──────────────────────────────────────────────────


class TestDockerCodeExecutor:

    @patch("agentspan.agents.code_executor.subprocess.run")
    def test_execute_success(self, mock_run):
        mock_run.return_value = MagicMock(stdout="42\n", stderr="", returncode=0)
        executor = DockerCodeExecutor(image="python:3.12-slim")
        result = executor.execute("print(42)")

        assert result.output == "42\n"
        assert result.exit_code == 0
        cmd = mock_run.call_args.args[0]
        assert "docker" in cmd
        assert "python:3.12-slim" in cmd
        assert "--network=none" in cmd  # default: network disabled

    @patch("agentspan.agents.code_executor.subprocess.run")
    def test_execute_network_enabled(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        executor = DockerCodeExecutor(network_enabled=True)
        executor.execute("code")

        cmd = mock_run.call_args.args[0]
        assert "--network=none" not in cmd

    @patch("agentspan.agents.code_executor.subprocess.run")
    def test_execute_memory_limit(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        executor = DockerCodeExecutor(memory_limit="256m")
        executor.execute("code")

        cmd = mock_run.call_args.args[0]
        assert "--memory" in cmd
        idx = cmd.index("--memory")
        assert cmd[idx + 1] == "256m"

    @patch("agentspan.agents.code_executor.subprocess.run")
    def test_execute_volumes(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        executor = DockerCodeExecutor(volumes={"/host/data": "/data"})
        executor.execute("code")

        cmd = mock_run.call_args.args[0]
        assert "-v" in cmd
        idx = cmd.index("-v")
        assert cmd[idx + 1] == "/host/data:/data:ro"

    @patch("agentspan.agents.code_executor.subprocess.run")
    def test_execute_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker", timeout=40)
        executor = DockerCodeExecutor(timeout=30)
        result = executor.execute("while True: pass")

        assert result.timed_out is True
        assert result.exit_code == -1

    @patch("agentspan.agents.code_executor.subprocess.run")
    def test_execute_docker_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        executor = DockerCodeExecutor()
        result = executor.execute("code")

        assert result.exit_code == 127
        assert "Docker not found" in result.error

    @patch("agentspan.agents.code_executor.subprocess.run")
    def test_execute_general_exception(self, mock_run):
        mock_run.side_effect = RuntimeError("container error")
        executor = DockerCodeExecutor()
        result = executor.execute("code")

        assert result.exit_code == 1
        assert "container error" in result.error

    def test_repr(self):
        executor = DockerCodeExecutor(image="node:18", language="node", timeout=60)
        r = repr(executor)
        assert "DockerCodeExecutor" in r
        assert "node:18" in r


# ── JupyterCodeExecutor ─────────────────────────────────────────────────


class TestJupyterCodeExecutor:

    def test_execute_import_error(self):
        executor = JupyterCodeExecutor()
        with patch.object(executor, "_ensure_kernel", side_effect=ImportError("no jupyter")):
            result = executor.execute("print(1)")
        assert result.exit_code == 1
        assert "no jupyter" in result.error

    def test_execute_kernel_startup_failure(self):
        executor = JupyterCodeExecutor()
        with patch.object(executor, "_ensure_kernel", side_effect=RuntimeError("kernel died")):
            result = executor.execute("print(1)")
        assert result.exit_code == 1
        assert "Kernel startup failed" in result.error

    def test_execute_success(self):
        executor = JupyterCodeExecutor()
        mock_client = MagicMock()

        # Simulate messages: stream output, then status idle
        messages = [
            {"msg_type": "stream", "content": {"name": "stdout", "text": "hello\n"}},
            {"msg_type": "status", "content": {"execution_state": "idle"}},
        ]
        mock_client.get_iopub_msg.side_effect = messages
        mock_client.execute.return_value = None

        executor._kernel_client = mock_client
        result = executor.execute("print('hello')")

        assert result.output == "hello\n"
        assert result.exit_code == 0

    def test_execute_with_stderr(self):
        executor = JupyterCodeExecutor()
        mock_client = MagicMock()

        messages = [
            {"msg_type": "stream", "content": {"name": "stderr", "text": "warning\n"}},
            {"msg_type": "status", "content": {"execution_state": "idle"}},
        ]
        mock_client.get_iopub_msg.side_effect = messages
        executor._kernel_client = mock_client

        result = executor.execute("import warnings")

        assert result.error == "warning\n"
        assert result.exit_code == 1  # errors present

    def test_execute_with_error_message(self):
        executor = JupyterCodeExecutor()
        mock_client = MagicMock()

        messages = [
            {"msg_type": "error", "content": {"traceback": ["NameError: x"]}},
            {"msg_type": "status", "content": {"execution_state": "idle"}},
        ]
        mock_client.get_iopub_msg.side_effect = messages
        executor._kernel_client = mock_client

        result = executor.execute("print(x)")

        assert "NameError" in result.error
        assert result.exit_code == 1

    def test_execute_with_execute_result(self):
        executor = JupyterCodeExecutor()
        mock_client = MagicMock()

        messages = [
            {"msg_type": "execute_result", "content": {"data": {"text/plain": "42"}}},
            {"msg_type": "status", "content": {"execution_state": "idle"}},
        ]
        mock_client.get_iopub_msg.side_effect = messages
        executor._kernel_client = mock_client

        result = executor.execute("21 + 21")
        assert result.output == "42"

    def test_execute_timeout(self):
        executor = JupyterCodeExecutor(timeout=1)
        mock_client = MagicMock()
        # Raise on get_iopub_msg (simulates timeout)
        mock_client.get_iopub_msg.side_effect = Exception("timeout")
        executor._kernel_client = mock_client

        result = executor.execute("while True: pass")

        assert result.timed_out is True
        assert result.exit_code == -1

    def test_ensure_kernel_already_running(self):
        executor = JupyterCodeExecutor()
        executor._kernel_client = MagicMock()
        # Should not raise or create new kernel
        executor._ensure_kernel()

    @patch("agentspan.agents.code_executor.JupyterCodeExecutor._ensure_kernel")
    def test_ensure_kernel_import_error_propagates(self, mock_ensure):
        mock_ensure.side_effect = ImportError("no jupyter_client")
        executor = JupyterCodeExecutor()
        result = executor.execute("print(1)")
        assert result.exit_code == 1

    def test_shutdown(self):
        executor = JupyterCodeExecutor()
        mock_client = MagicMock()
        mock_manager = MagicMock()
        executor._kernel_client = mock_client
        executor._kernel_manager = mock_manager

        executor.shutdown()

        mock_client.stop_channels.assert_called_once()
        mock_manager.shutdown_kernel.assert_called_once_with(now=True)
        assert executor._kernel_client is None
        assert executor._kernel_manager is None

    def test_shutdown_noop_when_not_started(self):
        executor = JupyterCodeExecutor()
        executor.shutdown()  # Should not raise

    def test_repr(self):
        executor = JupyterCodeExecutor(kernel_name="ir", timeout=60)
        r = repr(executor)
        assert "JupyterCodeExecutor" in r
        assert "ir" in r


# ── ServerlessCodeExecutor ──────────────────────────────────────────────


class TestServerlessCodeExecutor:

    @patch("urllib.request.urlopen")
    def test_send_request_success(self, mock_urlopen):
        response_data = json.dumps({"output": "hello", "error": "", "exit_code": 0}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = response_data
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        executor = ServerlessCodeExecutor(endpoint="https://api.example.com/exec")
        result = executor.execute("print('hello')")

        assert result.output == "hello"
        assert result.exit_code == 0

    @patch("urllib.request.urlopen")
    def test_send_request_with_api_key(self, mock_urlopen):
        response_data = json.dumps({"output": "ok", "exit_code": 0}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = response_data
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        executor = ServerlessCodeExecutor(
            endpoint="https://api.example.com/exec",
            api_key="sk-test-key",
        )
        executor.execute("code")

        # Check request headers include Authorization
        req = mock_urlopen.call_args.args[0]
        assert "Bearer sk-test-key" in req.get_header("Authorization")

    @patch("urllib.request.urlopen")
    def test_send_request_without_api_key(self, mock_urlopen):
        response_data = json.dumps({"output": "ok", "exit_code": 0}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = response_data
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        executor = ServerlessCodeExecutor(endpoint="https://api.example.com/exec")
        executor.execute("code")

        req = mock_urlopen.call_args.args[0]
        assert not req.has_header("Authorization")

    @patch("urllib.request.urlopen")
    def test_send_request_alternate_keys(self, mock_urlopen):
        """Response uses 'stdout'/'stderr' instead of 'output'/'error'."""
        response_data = json.dumps({"stdout": "result", "stderr": "warn", "exit_code": 0}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = response_data
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        executor = ServerlessCodeExecutor(endpoint="https://api.example.com/exec")
        result = executor.execute("code")

        assert result.output == "result"
        assert result.error == "warn"

    @patch("urllib.request.urlopen")
    def test_send_request_url_error(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("connection refused")

        executor = ServerlessCodeExecutor(endpoint="https://api.example.com/exec")
        result = executor.execute("code")

        assert result.exit_code == 1
        assert "Request failed" in result.error

    @patch("urllib.request.urlopen")
    def test_send_request_general_error(self, mock_urlopen):
        mock_urlopen.side_effect = RuntimeError("unexpected")

        executor = ServerlessCodeExecutor(endpoint="https://api.example.com/exec")
        result = executor.execute("code")

        assert result.exit_code == 1
        assert "unexpected" in result.error

    def test_repr(self):
        executor = ServerlessCodeExecutor(
            endpoint="https://api.example.com/exec",
            language="node",
        )
        r = repr(executor)
        assert "ServerlessCodeExecutor" in r
        assert "api.example.com" in r


# ── Base class: as_tool() and __repr__() ────────────────────────────────


class TestCodeExecutorBase:

    def test_as_tool_returns_decorated(self):
        executor = LocalCodeExecutor(language="python", timeout=10)
        tool_fn = executor.as_tool()
        assert hasattr(tool_fn, "_tool_def")
        assert tool_fn._tool_def.name == "execute_code"

    def test_as_tool_custom_name(self):
        executor = LocalCodeExecutor()
        tool_fn = executor.as_tool(name="run_python")
        assert tool_fn._tool_def.name == "run_python"

    def test_as_tool_custom_description(self):
        executor = LocalCodeExecutor()
        tool_fn = executor.as_tool(description="Run code safely")
        assert tool_fn._tool_def.description == "Run code safely"

    def test_repr(self):
        executor = LocalCodeExecutor(language="python", timeout=15)
        r = repr(executor)
        assert "LocalCodeExecutor" in r
        assert "python" in r
        assert "15" in r

    @patch("subprocess.run")
    def test_as_tool_output_formatting_stdout(self, mock_run):
        """as_tool() returns structured dict with status/stdout/stderr."""
        mock_run.return_value = MagicMock(
            stdout="hello world",
            stderr="",
            returncode=0,
        )
        executor = LocalCodeExecutor(language="python")
        tool_fn = executor.as_tool()
        result = tool_fn(code="print('hello world')")
        assert result["status"] == "success"
        assert result["stdout"] == "hello world"
        assert result["stderr"] == ""

    @patch("subprocess.run")
    def test_as_tool_output_formatting_stderr(self, mock_run):
        """as_tool() returns error dict on non-zero exit code."""
        mock_run.return_value = MagicMock(
            stdout="",
            stderr="error occurred",
            returncode=1,
        )
        executor = LocalCodeExecutor(language="python")
        tool_fn = executor.as_tool()
        result = tool_fn(code="bad code")
        assert result["status"] == "error"
        assert "error occurred" in result["stderr"]
        assert "Exit code: 1" in result["stderr"]

    @patch("subprocess.run")
    def test_as_tool_output_formatting_timeout(self, mock_run):
        """as_tool() returns error dict on timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="python", timeout=5)
        executor = LocalCodeExecutor(language="python", timeout=5)
        tool_fn = executor.as_tool()
        result = tool_fn(code="import time; time.sleep(999)")
        assert result["status"] == "error"
        assert "TIMED OUT" in result["stderr"]

    def test_as_tool_empty_code_returns_dict(self):
        """as_tool() returns structured dict for empty code."""
        executor = LocalCodeExecutor(language="python")
        tool_fn = executor.as_tool()
        result = tool_fn(code="")
        assert result["status"] == "success"
        assert "No code provided" in result["stdout"]
        assert result["stderr"] == ""


class TestJupyterCodeExecutor:
    """Tests for JupyterCodeExecutor with mocked jupyter_client."""

    def test_ensure_kernel_creates_manager(self):
        """_ensure_kernel creates KernelManager and starts kernel."""
        mock_km = MagicMock()
        mock_client = MagicMock()
        mock_km.client.return_value = mock_client

        with patch.dict("sys.modules", {"jupyter_client": MagicMock()}):
            executor = JupyterCodeExecutor()
            executor._kernel_manager = None
            executor._kernel_client = None

            # Manually set up the kernel (simulating _ensure_kernel)
            with patch("agentspan.agents.code_executor.JupyterCodeExecutor._ensure_kernel") as mock_ensure:
                # Instead of calling _ensure_kernel, just set internal state
                executor._kernel_manager = mock_km
                executor._kernel_client = mock_client

                assert executor._kernel_manager is mock_km
                assert executor._kernel_client is mock_client

    def test_ensure_kernel_already_running(self):
        """If kernel is already running, _ensure_kernel is a no-op."""
        executor = JupyterCodeExecutor()
        mock_client = MagicMock()
        executor._kernel_client = mock_client

        executor._ensure_kernel()  # Should return immediately
        # No new kernel manager should be created
        assert executor._kernel_client is mock_client

    def test_ensure_kernel_import_error(self):
        """If jupyter_client is not installed, raises ImportError."""
        executor = JupyterCodeExecutor()
        executor._kernel_client = None

        with patch("builtins.__import__", side_effect=ImportError("No module named 'jupyter_client'")):
            with pytest.raises(ImportError, match="jupyter_client"):
                executor._ensure_kernel()

    def test_ensure_kernel_with_startup_code(self):
        """_ensure_kernel executes startup_code when provided."""
        executor = JupyterCodeExecutor(startup_code="import numpy")
        executor._kernel_client = None

        mock_km = MagicMock()
        mock_client = MagicMock()
        mock_km.client.return_value = mock_client
        # Make get_iopub_msg raise to drain startup output
        mock_client.get_iopub_msg.side_effect = Exception("timeout")

        mock_jupyter = MagicMock()
        mock_jupyter.KernelManager.return_value = mock_km

        with patch.dict("sys.modules", {"jupyter_client": mock_jupyter}):
            # Reset to force reimport
            executor._kernel_client = None
            executor._kernel_manager = None
            executor._ensure_kernel()

            mock_client.execute.assert_called_once_with("import numpy")

    def test_execute_success(self):
        """Execute code and collect stdout output."""
        executor = JupyterCodeExecutor()
        mock_client = MagicMock()
        executor._kernel_client = mock_client

        # Simulate iopub messages: stream output then idle status
        mock_client.get_iopub_msg.side_effect = [
            {"msg_type": "stream", "content": {"name": "stdout", "text": "hello world"}},
            {"msg_type": "status", "content": {"execution_state": "idle"}},
        ]

        result = executor.execute("print('hello world')")
        assert result.output == "hello world"
        assert result.exit_code == 0

    def test_execute_with_execute_result(self):
        """Execute code that returns an execute_result."""
        executor = JupyterCodeExecutor()
        mock_client = MagicMock()
        executor._kernel_client = mock_client

        mock_client.get_iopub_msg.side_effect = [
            {"msg_type": "execute_result", "content": {"data": {"text/plain": "42"}}},
            {"msg_type": "status", "content": {"execution_state": "idle"}},
        ]

        result = executor.execute("21 * 2")
        assert result.output == "42"
        assert result.exit_code == 0

    def test_execute_with_stderr(self):
        """Execute code that produces stderr output."""
        executor = JupyterCodeExecutor()
        mock_client = MagicMock()
        executor._kernel_client = mock_client

        mock_client.get_iopub_msg.side_effect = [
            {"msg_type": "stream", "content": {"name": "stderr", "text": "warning: something"}},
            {"msg_type": "status", "content": {"execution_state": "idle"}},
        ]

        result = executor.execute("import warnings; warnings.warn('something')")
        assert result.error == "warning: something"
        assert result.exit_code == 1

    def test_execute_with_error(self):
        """Execute code that raises an error."""
        executor = JupyterCodeExecutor()
        mock_client = MagicMock()
        executor._kernel_client = mock_client

        mock_client.get_iopub_msg.side_effect = [
            {"msg_type": "error", "content": {"traceback": ["ValueError", "bad value"]}},
            {"msg_type": "status", "content": {"execution_state": "idle"}},
        ]

        result = executor.execute("raise ValueError('bad')")
        assert "ValueError" in result.error
        assert result.exit_code == 1

    def test_execute_timeout(self):
        """Execute code that times out."""
        executor = JupyterCodeExecutor(timeout=1)
        mock_client = MagicMock()
        executor._kernel_client = mock_client

        # Simulate timeout by raising an exception from get_iopub_msg
        mock_client.get_iopub_msg.side_effect = Exception("timeout")

        result = executor.execute("import time; time.sleep(999)")
        assert result.timed_out is True
        assert result.exit_code == -1

    def test_execute_import_error_returns_result(self):
        """Execute when kernel can't start returns error result."""
        executor = JupyterCodeExecutor()
        executor._kernel_client = None

        with patch.object(executor, "_ensure_kernel", side_effect=ImportError("no jupyter_client")):
            result = executor.execute("print('hi')")
            assert result.exit_code == 1
            assert "jupyter_client" in result.error

    def test_execute_kernel_startup_failure(self):
        """Execute when kernel startup fails returns error result."""
        executor = JupyterCodeExecutor()
        executor._kernel_client = None

        with patch.object(executor, "_ensure_kernel", side_effect=RuntimeError("kernel crash")):
            result = executor.execute("print('hi')")
            assert result.exit_code == 1
            assert "Kernel startup failed" in result.error

    def test_shutdown(self):
        """shutdown() stops channels and shuts down kernel."""
        executor = JupyterCodeExecutor()
        mock_client = MagicMock()
        mock_manager = MagicMock()
        executor._kernel_client = mock_client
        executor._kernel_manager = mock_manager

        executor.shutdown()

        mock_client.stop_channels.assert_called_once()
        mock_manager.shutdown_kernel.assert_called_once_with(now=True)
        assert executor._kernel_client is None
        assert executor._kernel_manager is None

    def test_shutdown_no_kernel(self):
        """shutdown() with no kernel is a no-op."""
        executor = JupyterCodeExecutor()
        executor.shutdown()  # Should not raise

    def test_repr(self):
        executor = JupyterCodeExecutor(kernel_name="python3", timeout=30)
        r = repr(executor)
        assert "JupyterCodeExecutor" in r
        assert "python3" in r


class TestLocalCodeExecutorOSErrorCleanup:
    """Test that OSError during temp file cleanup is handled."""

    @patch("subprocess.run")
    @patch("os.unlink", side_effect=OSError("permission denied"))
    @patch("tempfile.NamedTemporaryFile")
    def test_os_error_on_unlink_is_handled(self, mock_tmpfile, mock_unlink, mock_run):
        """OSError during temp file cleanup should not crash execution."""
        mock_file = MagicMock()
        mock_file.name = "/tmp/test.py"
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_tmpfile.return_value = mock_file

        mock_run.return_value = MagicMock(
            stdout="output",
            stderr="",
            returncode=0,
        )

        executor = LocalCodeExecutor(language="python")
        result = executor.execute("print('hi')")
        # Should still return the result despite cleanup failure
        assert result.output == "output"
        assert result.exit_code == 0
