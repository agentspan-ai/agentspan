# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Code executors — sandboxed environments for running LLM-generated code.

Provides pre-built tools that let agents write and execute code safely.
Each executor can be attached to an agent via ``executor.as_tool()``.

Supported execution environments:

- :class:`LocalCodeExecutor` — runs code in a local subprocess (no sandbox).
- :class:`DockerCodeExecutor` — runs code inside a Docker container.
- :class:`JupyterCodeExecutor` — runs code in a Jupyter kernel.
- :class:`ServerlessCodeExecutor` — extensible base for remote execution services.

Example::

    from agentspan.agents import Agent
    from agentspan.agents.code_executor import DockerCodeExecutor

    executor = DockerCodeExecutor(image="python:3.12-slim", timeout=30)

    agent = Agent(
        name="coder",
        model="openai/gpt-4o",
        tools=[executor.as_tool()],
        instructions="Write and execute Python code to solve problems.",
    )
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agentspan.agents.code_executor")


@dataclass
class ExecutionResult:
    """The result of a code execution.

    Attributes:
        output: Standard output from the execution.
        error: Standard error output (if any).
        exit_code: Process exit code (0 = success).
        timed_out: ``True`` if execution was killed due to timeout.
    """

    output: str = ""
    error: str = ""
    exit_code: int = 0
    timed_out: bool = False

    @property
    def success(self) -> bool:
        """``True`` if the execution succeeded (exit code 0, no timeout)."""
        return self.exit_code == 0 and not self.timed_out


class CodeExecutor(ABC):
    """Base class for code execution environments.

    Args:
        language: Programming language (default ``"python"``).
        timeout: Maximum execution time in seconds (default ``30``).
        working_dir: Working directory for execution.
    """

    def __init__(
        self,
        language: str = "python",
        timeout: int = 30,
        working_dir: Optional[str] = None,
    ) -> None:
        self.language = language
        self.timeout = timeout
        self.working_dir = working_dir

    @abstractmethod
    def execute(self, code: str) -> ExecutionResult:
        """Execute code and return the result.

        Args:
            code: Source code to execute.

        Returns:
            An :class:`ExecutionResult`.
        """
        ...

    def as_tool(self, name: Optional[str] = None, description: Optional[str] = None) -> Any:
        """Create a ``@tool``-compatible function for this executor.

        Returns a decorated function that can be passed directly to
        ``Agent(tools=[...])``.

        Args:
            name: Override tool name (default: ``"execute_code"``).
            description: Override description.
        """
        from agentspan.agents.tool import tool

        executor = self
        tool_name = name or "execute_code"
        tool_desc = description or (
            f"Execute {self.language} code. Returns stdout, stderr, and exit code. "
            f"Timeout: {self.timeout}s."
        )

        @tool(name=tool_name)
        def execute_code(code: str) -> dict:
            if not code:
                return {"status": "success", "stdout": "No code provided. Nothing to execute.", "stderr": ""}
            result = executor.execute(code)
            if result.success:
                return {
                    "status": "success",
                    "stdout": result.output or "",
                    "stderr": result.error or "",
                }
            else:
                stderr_parts = []
                if result.error:
                    stderr_parts.append(result.error.rstrip())
                if result.timed_out:
                    stderr_parts.append(f"TIMED OUT after {executor.timeout}s")
                stderr_parts.append(f"Exit code: {result.exit_code}")
                return {
                    "status": "error",
                    "stdout": result.output or "",
                    "stderr": "\n".join(stderr_parts),
                }

        # Override the description on the tool def
        execute_code._tool_def.description = tool_desc
        return execute_code

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(language={self.language!r}, "
            f"timeout={self.timeout})"
        )


class LocalCodeExecutor(CodeExecutor):
    """Execute code in a local subprocess.

    .. warning:: No sandboxing — the code runs with the same permissions as
       the Python process.  Use :class:`DockerCodeExecutor` for untrusted code.

    Args:
        language: Programming language (``"python"``, ``"bash"``, ``"node"``).
        timeout: Max seconds before the process is killed.
        working_dir: Working directory for execution.

    Example::

        executor = LocalCodeExecutor(language="python", timeout=10)
        result = executor.execute("print('hello')")
        assert result.output.strip() == "hello"
    """

    # Map language names to interpreter commands
    _INTERPRETERS = {
        "python": ["python3"],
        "python3": ["python3"],
        "bash": ["bash"],
        "sh": ["sh"],
        "node": ["node"],
        "javascript": ["node"],
        "ruby": ["ruby"],
    }

    def execute(self, code: str) -> ExecutionResult:
        if not code:
            return ExecutionResult(
                output="No code provided. Nothing to execute.",
                exit_code=0,
            )
        if not isinstance(code, str):
            code = str(code)
        interpreter = self._INTERPRETERS.get(self.language)
        if interpreter is None:
            return ExecutionResult(
                error=f"Unsupported language: {self.language}",
                exit_code=1,
            )

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=self._file_extension(), delete=False
        ) as f:
            f.write(code)
            f.flush()
            tmp_path = f.name

        try:
            result = subprocess.run(
                interpreter + [tmp_path],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=self.working_dir,
            )
            return ExecutionResult(
                output=result.stdout,
                error=result.stderr,
                exit_code=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                error=f"Execution timed out after {self.timeout}s",
                exit_code=-1,
                timed_out=True,
            )
        except FileNotFoundError:
            return ExecutionResult(
                error=f"Interpreter not found: {interpreter[0]}",
                exit_code=127,
            )
        except Exception as e:
            return ExecutionResult(error=str(e), exit_code=1)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _file_extension(self) -> str:
        ext_map = {
            "python": ".py", "python3": ".py",
            "bash": ".sh", "sh": ".sh",
            "node": ".js", "javascript": ".js",
            "ruby": ".rb",
        }
        return ext_map.get(self.language, ".txt")


class DockerCodeExecutor(CodeExecutor):
    """Execute code inside a Docker container.

    Provides isolation — the code cannot access the host filesystem
    or network (unless explicitly configured).

    Requires Docker to be installed and the Docker daemon running.

    Args:
        image: Docker image to use (default ``"python:3.12-slim"``).
        language: Programming language.
        timeout: Max seconds before the container is killed.
        network_enabled: Whether the container has network access (default ``False``).
        memory_limit: Container memory limit (e.g. ``"256m"``).
        volumes: Optional dict of host:container volume mounts.

    Example::

        executor = DockerCodeExecutor(image="python:3.12-slim", timeout=15)
        result = executor.execute("import sys; print(sys.version)")
    """

    def __init__(
        self,
        image: str = "python:3.12-slim",
        language: str = "python",
        timeout: int = 30,
        network_enabled: bool = False,
        memory_limit: Optional[str] = None,
        volumes: Optional[Dict[str, str]] = None,
    ) -> None:
        super().__init__(language=language, timeout=timeout)
        self.image = image
        self.network_enabled = network_enabled
        self.memory_limit = memory_limit
        self.volumes = volumes or {}

    def execute(self, code: str) -> ExecutionResult:
        cmd = ["docker", "run", "--rm"]

        if not self.network_enabled:
            cmd.append("--network=none")

        if self.memory_limit:
            cmd.extend(["--memory", self.memory_limit])

        for host_path, container_path in self.volumes.items():
            cmd.extend(["-v", f"{host_path}:{container_path}:ro"])

        # Pass code via stdin
        interpreter = {"python": "python3", "bash": "bash", "node": "node"}.get(
            self.language, "python3"
        )
        cmd.extend([self.image, interpreter, "-c", code])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout + 10,  # extra for container startup
            )
            return ExecutionResult(
                output=result.stdout,
                error=result.stderr,
                exit_code=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                error=f"Docker execution timed out after {self.timeout}s",
                exit_code=-1,
                timed_out=True,
            )
        except FileNotFoundError:
            return ExecutionResult(
                error="Docker not found. Install Docker to use DockerCodeExecutor.",
                exit_code=127,
            )
        except Exception as e:
            return ExecutionResult(error=str(e), exit_code=1)

    def __repr__(self) -> str:
        return (
            f"DockerCodeExecutor(image={self.image!r}, "
            f"language={self.language!r}, timeout={self.timeout})"
        )


class JupyterCodeExecutor(CodeExecutor):
    """Execute code in a Jupyter kernel.

    Maintains kernel state across executions — variables and imports
    persist between calls, just like a Jupyter notebook.

    Requires ``jupyter_client`` to be installed.

    Args:
        kernel_name: Jupyter kernel name (default ``"python3"``).
        timeout: Max seconds per cell execution.
        startup_code: Optional code to run when the kernel starts.

    Example::

        executor = JupyterCodeExecutor(timeout=30)
        executor.execute("x = 42")
        result = executor.execute("print(x)")
        assert "42" in result.output
    """

    def __init__(
        self,
        kernel_name: str = "python3",
        timeout: int = 30,
        startup_code: Optional[str] = None,
    ) -> None:
        super().__init__(language="python", timeout=timeout)
        self.kernel_name = kernel_name
        self.startup_code = startup_code
        self._kernel_manager = None
        self._kernel_client = None

    def _ensure_kernel(self) -> None:
        """Start a Jupyter kernel if one isn't running."""
        if self._kernel_client is not None:
            return

        try:
            from jupyter_client import KernelManager
        except ImportError:
            raise ImportError(
                "JupyterCodeExecutor requires jupyter_client. "
                "Install with: pip install jupyter_client ipykernel"
            )

        self._kernel_manager = KernelManager(kernel_name=self.kernel_name)
        self._kernel_manager.start_kernel()
        self._kernel_client = self._kernel_manager.client()
        self._kernel_client.start_channels()
        self._kernel_client.wait_for_ready(timeout=30)

        if self.startup_code:
            self._kernel_client.execute(self.startup_code)
            # Drain the startup output
            try:
                while True:
                    self._kernel_client.get_iopub_msg(timeout=2)
            except Exception:
                pass

    def execute(self, code: str) -> ExecutionResult:
        try:
            self._ensure_kernel()
        except ImportError as e:
            return ExecutionResult(error=str(e), exit_code=1)
        except Exception as e:
            return ExecutionResult(error=f"Kernel startup failed: {e}", exit_code=1)

        self._kernel_client.execute(code)

        outputs = []
        errors = []

        try:
            while True:
                msg = self._kernel_client.get_iopub_msg(timeout=self.timeout)
                msg_type = msg.get("msg_type", "")
                content = msg.get("content", {})

                if msg_type == "stream":
                    text = content.get("text", "")
                    if content.get("name") == "stderr":
                        errors.append(text)
                    else:
                        outputs.append(text)
                elif msg_type == "execute_result":
                    data = content.get("data", {})
                    outputs.append(data.get("text/plain", ""))
                elif msg_type == "error":
                    tb = content.get("traceback", [])
                    errors.append("\n".join(str(line) for line in tb))
                elif msg_type == "status" and content.get("execution_state") == "idle":
                    break
        except Exception:
            if not outputs and not errors:
                return ExecutionResult(
                    error=f"Execution timed out after {self.timeout}s",
                    exit_code=-1,
                    timed_out=True,
                )

        return ExecutionResult(
            output="".join(outputs),
            error="".join(errors),
            exit_code=1 if errors else 0,
        )

    def shutdown(self) -> None:
        """Shut down the Jupyter kernel."""
        if self._kernel_client:
            self._kernel_client.stop_channels()
            self._kernel_client = None
        if self._kernel_manager:
            self._kernel_manager.shutdown_kernel(now=True)
            self._kernel_manager = None

    def __del__(self) -> None:
        self.shutdown()

    def __repr__(self) -> str:
        return (
            f"JupyterCodeExecutor(kernel={self.kernel_name!r}, "
            f"timeout={self.timeout})"
        )


class ServerlessCodeExecutor(CodeExecutor):
    """Execute code via a remote serverless execution service.

    This is an extensible base for services like AWS Lambda, Google Cloud
    Functions, or hosted code execution APIs.  Subclass and override
    :meth:`_send_request` to integrate with your service.

    Args:
        endpoint: The HTTP endpoint URL for the execution service.
        api_key: Optional API key for authentication.
        language: Programming language.
        timeout: Max seconds to wait for a response.
        headers: Optional additional HTTP headers.

    Example (custom service)::

        executor = ServerlessCodeExecutor(
            endpoint="https://api.myservice.com/execute",
            api_key="sk-...",
        )
        result = executor.execute("print('hello from the cloud')")
    """

    def __init__(
        self,
        endpoint: str,
        api_key: Optional[str] = None,
        language: str = "python",
        timeout: int = 30,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        super().__init__(language=language, timeout=timeout)
        self.endpoint = endpoint
        self.api_key = api_key
        self.headers = headers or {}

    def execute(self, code: str) -> ExecutionResult:
        return self._send_request(code)

    def _send_request(self, code: str) -> ExecutionResult:
        """Send code to the remote execution service.

        Override this method to integrate with specific services.
        The default implementation uses ``requests`` or ``urllib``.
        """
        import json
        import urllib.request
        import urllib.error

        headers = {"Content-Type": "application/json", **self.headers}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = json.dumps({
            "code": code,
            "language": self.language,
            "timeout": self.timeout,
        }).encode("utf-8")

        req = urllib.request.Request(
            self.endpoint, data=payload, headers=headers, method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout + 5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return ExecutionResult(
                    output=data.get("output", data.get("stdout", "")),
                    error=data.get("error", data.get("stderr", "")),
                    exit_code=int(data.get("exit_code", 0)),
                )
        except urllib.error.URLError as e:
            return ExecutionResult(error=f"Request failed: {e}", exit_code=1)
        except Exception as e:
            return ExecutionResult(error=str(e), exit_code=1)

    def __repr__(self) -> str:
        return (
            f"ServerlessCodeExecutor(endpoint={self.endpoint!r}, "
            f"language={self.language!r})"
        )
