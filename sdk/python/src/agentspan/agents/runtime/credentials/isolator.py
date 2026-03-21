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
  - Parent process environment is NEVER modified — env dict is serialized
    inside the cloudpickle payload and applied inside the child process.

Implementation uses multiprocessing spawn + cloudpickle for clean isolation.
"""

from __future__ import annotations

import multiprocessing
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple, Union

from agentspan.agents.runtime.credentials.types import CredentialFile


def _subprocess_entry(pickled_payload: bytes, result_queue: Any) -> None:
    """Subprocess entry point.

    The payload is a cloudpickle-serialized ``(env, fn, args, kwargs)`` tuple.
    We apply *env* to the subprocess's ``os.environ`` first, then call the function.
    """
    import cloudpickle  # noqa: PLC0415

    try:
        env, fn, args, kwargs = cloudpickle.loads(pickled_payload)
        # Apply the isolated environment inside the child process only.
        os.environ.clear()
        os.environ.update(env)
        result = fn(*args, **kwargs)
        result_queue.put(("ok", result))
    except BaseException as exc:  # noqa: BLE001
        result_queue.put(("error", exc))


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
        """Serialize (env, fn, args, kwargs) with cloudpickle and spawn a process."""
        import cloudpickle  # noqa: PLC0415

        # Env dict is part of the payload — parent os.environ is never touched.
        pickled = cloudpickle.dumps((env, fn, args, kwargs))

        ctx = multiprocessing.get_context("spawn")
        result_queue: multiprocessing.Queue = ctx.Queue()
        proc = ctx.Process(target=_subprocess_entry, args=(pickled, result_queue))
        proc.start()
        proc.join(timeout=self._timeout)

        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=5)
            raise TimeoutError(f"Subprocess timed out after {self._timeout}s")

        if not result_queue.empty():
            status, value = result_queue.get_nowait()
            if status == "ok":
                return value
            raise value

        raise RuntimeError(f"Subprocess exited with code {proc.exitcode} and produced no result")
