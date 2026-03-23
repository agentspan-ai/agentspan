# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""SubprocessIsolator — runs tool functions in credential-isolated subprocesses.

Security model:
  - Each tool execution gets a fresh temporary HOME directory.
  - String credentials are injected as environment variables (subprocess only).
  - File credentials are written to {tmp_home}/{relative_path} with 0o600 perms.
  - The env var for file credentials points to the absolute path.
  - Temp HOME and all credential files are deleted synchronously after the
    subprocess exits (TemporaryDirectory context manager).
  - Parent process environment is NEVER modified — env dict is passed via
    subprocess.Popen(env=...) and applied inside the child process.

Implementation uses subprocess.Popen + cloudpickle for clean isolation.
This works from daemon threads (unlike multiprocessing.Process).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple, Union

from agentspan.agents.runtime.credentials.types import CredentialFile

# Python helper script executed in the child process.
# Reads a cloudpickle payload from stdin, executes the function,
# and writes the result back to stdout.
_CHILD_SCRIPT = """\
import sys, os, cloudpickle, base64
payload = base64.b64decode(sys.stdin.buffer.read())
env, fn, args, kwargs = cloudpickle.loads(payload)
os.environ.clear()
os.environ.update(env)
# Redirect stdout to stderr so tool print() doesn't corrupt the result channel.
_real_stdout = sys.stdout
sys.stdout = sys.stderr
try:
    result = fn(*args, **kwargs)
    out = cloudpickle.dumps(("ok", result))
except BaseException as exc:
    out = cloudpickle.dumps(("error", exc))
_real_stdout.buffer.write(base64.b64encode(out))
_real_stdout.buffer.flush()
"""


class SubprocessIsolator:
    """Runs a callable in a subprocess with an isolated HOME and injected credentials.

    The parent process environment is never modified. All credential material
    lives only in the spawned child process and the temp directory, which is
    deleted synchronously after the child exits.

    Args:
        timeout: Maximum seconds to wait for the subprocess. ``None`` = no limit.
    """

    def __init__(self, timeout: Optional[int] = None) -> None:
        self._timeout = timeout

    def run(
        self,
        fn: Callable[..., Any],
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        credentials: Dict[str, Union[str, CredentialFile]],
    ) -> Any:
        """Execute *fn* in a subprocess with an isolated credential environment.

        Args:
            fn: The callable to execute.
            args: Positional arguments for *fn*.
            kwargs: Keyword arguments for *fn*.
            credentials: Credential name → string value or ``CredentialFile``.

        Returns:
            Return value of ``fn(*args, **kwargs)``.

        Raises:
            Any exception raised by *fn* (re-raised in caller's process).
            ``TimeoutError`` if the subprocess exceeds *timeout* seconds.
        """
        with tempfile.TemporaryDirectory(prefix="agentspan-") as tmp_home:
            env = self._build_env(tmp_home, credentials)
            return self._run_in_subprocess(fn, args, kwargs, env)

    # ── Private helpers ──────────────────────────────────────────────────

    def _build_env(
        self,
        tmp_home: str,
        credentials: Dict[str, Union[str, CredentialFile]],
    ) -> Dict[str, str]:
        """Build subprocess environment: parent env + HOME override + credentials."""
        env = os.environ.copy()
        env["HOME"] = tmp_home

        for _name, value in credentials.items():
            if isinstance(value, str):
                env[_name] = value
            elif isinstance(value, CredentialFile):
                abs_path = os.path.join(tmp_home, value.relative_path)
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                content = value.content or ""
                Path(abs_path).write_text(content)
                os.chmod(abs_path, 0o600)
                env[value.env_var] = abs_path

        return env

    def _run_in_subprocess(
        self,
        fn: Callable[..., Any],
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        env: Dict[str, str],
    ) -> Any:
        """Serialize (env, fn, args, kwargs) with cloudpickle and run via Popen."""
        import base64

        import cloudpickle  # noqa: PLC0415

        pickled = cloudpickle.dumps((env, fn, args, kwargs))
        encoded = base64.b64encode(pickled)

        proc = subprocess.Popen(
            [sys.executable, "-c", _CHILD_SCRIPT],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

        try:
            stdout, stderr = proc.communicate(input=encoded, timeout=self._timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise TimeoutError(f"Subprocess timed out after {self._timeout}s")

        if proc.returncode != 0:
            raise RuntimeError(
                f"Subprocess exited with code {proc.returncode}: {stderr.decode(errors='replace')}"
            )

        if not stdout:
            raise RuntimeError("Subprocess produced no output")

        result_bytes = base64.b64decode(stdout)
        status, value = cloudpickle.loads(result_bytes)
        if status == "ok":
            return value
        raise value
