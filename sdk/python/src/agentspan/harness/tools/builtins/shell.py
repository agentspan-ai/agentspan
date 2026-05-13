# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""``shell`` — bounded shell command execution.

Behavior per design §11:

  * Stream stdout+stderr to a per-task log file.
  * Keep a bounded preview in memory.
  * Enforce timeout (default 120s, max 600s).
  * Enforce max output bytes; truncate or kill on overflow.
  * Kill the entire process tree on timeout/abort, not just the parent.
  * Sandbox check before spawn; refuse on deny.
  * Exit code, stdout preview, stderr preview, and log file path in the
    result so the model can read the full output via ``read_task_output``.

Background execution + Conductor SUB_WORKFLOW backing live in
``tasks.py`` and the ``read_task_output`` / ``stop_task`` tools. This
file handles the foreground synchronous case.
"""

from __future__ import annotations

import asyncio
import os
import signal
import tempfile
import time
import uuid
from typing import Any, Callable, Dict, Optional

from ..contract import Tool, ToolResult, ToolUseContext


_DEFAULT_TIMEOUT = 120
_MAX_TIMEOUT = 600
_MAX_OUTPUT_BYTES = 10 * 1024 * 1024  # 10 MB to disk
_MAX_PREVIEW_CHARS = 4000


class Shell(Tool[Dict[str, Any], Dict[str, Any]]):
    @property
    def name(self) -> str:
        return "shell"

    @property
    def description(self) -> str:
        return (
            "Run a shell command. Returns exit_code, stdout/stderr preview, "
            "and a log_path for the full output. Use timeout (default 120s) "
            "to bound execution. Sandbox checks the command before spawn; "
            "denied commands return an error result."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {"type": "integer", "description": "Seconds; default 120, max 600."},
                "cwd": {"type": "string", "description": "Working directory; defaults to session cwd."},
                "run_in_background": {
                    "type": "boolean",
                    "description": (
                        "If true, return a task_id immediately and run the "
                        "command in the background. Use read_task_output to "
                        "stream its log and stop_task to kill it."
                    ),
                },
            },
            "required": ["command"],
        }

    def is_read_only(self, input: Dict[str, Any]) -> bool:
        return False

    def is_destructive(self, input: Dict[str, Any]) -> bool:
        # Conservative: assume destructive unless the sandbox says otherwise.
        return True

    def is_concurrency_safe(self, input: Dict[str, Any]) -> bool:
        return False

    async def call(
        self,
        input: Dict[str, Any],
        context: ToolUseContext,
        parent_message: Any = None,
        on_progress: Optional[Callable[[Any], None]] = None,
    ) -> ToolResult[Dict[str, Any]]:
        command = input["command"]
        timeout = min(int(input.get("timeout", _DEFAULT_TIMEOUT)), _MAX_TIMEOUT)
        cwd = input.get("cwd", context.cwd)
        if not os.path.isabs(cwd):
            cwd = os.path.normpath(os.path.join(context.cwd, cwd))

        sandbox = context.store.get("sandbox")
        if sandbox is not None:
            check = sandbox.check_command(command, cwd=cwd)
            if not check.allowed:
                return ToolResult.error(f"sandbox: {check.reason}")
            check_cwd = sandbox.check_path_read(cwd)
            if not check_cwd.allowed:
                return ToolResult.error(f"sandbox cwd: {check_cwd.reason}")

        if not os.path.isdir(cwd):
            return ToolResult.error(f"cwd does not exist: {cwd}")

        run_in_background = bool(input.get("run_in_background", False))

        # Allocate task log file for full output.
        task_id = f"shell_{uuid.uuid4().hex[:12]}"
        log_dir = os.environ.get("AGENTSPAN_HARNESS_TASKS_DIR") or os.path.join(
            os.path.expanduser("~"), ".agentspan", "harness", "tasks"
        )
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, f"{task_id}.log")

        if run_in_background:
            return await _run_background(
                command=command, cwd=cwd, log_path=log_path,
                context=context, timeout=timeout,
            )

        started = time.time()

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                start_new_session=True,  # process group for tree kill
            )
        except OSError as exc:
            return ToolResult.error(f"spawn failed: {exc}")

        # Stream output to the log file while keeping a bounded preview.
        bytes_written = 0
        stdout_preview: bytearray = bytearray()
        stderr_preview: bytearray = bytearray()
        truncated = False

        async def _drain(stream: Any, preview_buf: bytearray, label: bytes) -> None:
            nonlocal bytes_written, truncated
            with open(log_path, "ab") as fp:
                while True:
                    if context.abort.is_set():
                        return
                    chunk = await stream.read(4096)
                    if not chunk:
                        return
                    fp.write(label + chunk if label else chunk)
                    bytes_written += len(chunk)
                    if len(preview_buf) < _MAX_PREVIEW_CHARS:
                        room = _MAX_PREVIEW_CHARS - len(preview_buf)
                        preview_buf.extend(chunk[:room])
                    if bytes_written >= _MAX_OUTPUT_BYTES:
                        truncated = True
                        try:
                            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                        except (ProcessLookupError, OSError):
                            pass
                        return

        async def _wait_for_exit() -> int:
            stdout_task = asyncio.create_task(_drain(proc.stdout, stdout_preview, b""))
            stderr_task = asyncio.create_task(_drain(proc.stderr, stderr_preview, b""))
            try:
                exit_code = await asyncio.wait_for(proc.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                _kill_tree(proc.pid)
                exit_code = -signal.SIGTERM
            finally:
                # Best-effort drain remaining buffers.
                for t in (stdout_task, stderr_task):
                    try:
                        await asyncio.wait_for(t, timeout=2)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        t.cancel()
            return exit_code

        try:
            exit_code = await _wait_for_exit()
        except asyncio.CancelledError:
            _kill_tree(proc.pid)
            raise

        elapsed_ms = int((time.time() - started) * 1000)

        result_data = {
            "exit_code": exit_code,
            "stdout": stdout_preview.decode("utf-8", errors="replace"),
            "stderr": stderr_preview.decode("utf-8", errors="replace"),
            "duration_ms": elapsed_ms,
            "log_path": log_path,
            "log_bytes": bytes_written,
            "truncated": truncated,
        }

        # Compose model-facing content.
        summary = (
            f"exit_code={exit_code} duration_ms={elapsed_ms} "
            f"log={log_path} bytes={bytes_written}"
            + (" [truncated]" if truncated else "")
        )
        out_str = result_data["stdout"]
        err_str = result_data["stderr"]
        chunks = [summary]
        if out_str:
            chunks.append("--- stdout ---\n" + out_str)
        if err_str:
            chunks.append("--- stderr ---\n" + err_str)
        if truncated:
            chunks.append(
                f"\n[Output truncated after {bytes_written} bytes; "
                f"read full output via read_task_output(log_path={log_path!r})]"
            )
        content = "\n".join(chunks)

        is_error = exit_code != 0
        return ToolResult(
            output=result_data,
            content=content,
            is_error=is_error,
            content_ref=log_path,
            preview=summary,
        )


async def _run_background(
    *,
    command: str,
    cwd: str,
    log_path: str,
    context: ToolUseContext,
    timeout: int,
) -> ToolResult:
    """Background variant: spawn, register with TaskManager, return task_id."""
    tasks = context.store.get("task_manager")
    if tasks is None:
        return ToolResult.error("background shell requires a task manager")

    async def _runner(abort: asyncio.Event) -> Dict[str, Any]:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                start_new_session=True,
            )
        except OSError as exc:
            return {"exit_code": -1, "error": f"spawn failed: {exc}"}

        async def _drain(stream: Any) -> None:
            with open(log_path, "ab") as fp:
                while True:
                    if abort.is_set():
                        return
                    chunk = await stream.read(4096)
                    if not chunk:
                        return
                    fp.write(chunk)

        stdout_t = asyncio.create_task(_drain(proc.stdout))
        stderr_t = asyncio.create_task(_drain(proc.stderr))

        async def _supervisor() -> int:
            try:
                return await asyncio.wait_for(proc.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                _kill_tree(proc.pid)
                return -signal.SIGTERM

        async def _abort_watcher() -> None:
            await abort.wait()
            _kill_tree(proc.pid)

        watcher = asyncio.create_task(_abort_watcher())
        try:
            exit_code = await _supervisor()
        finally:
            watcher.cancel()
            for t in (stdout_t, stderr_t):
                try:
                    await asyncio.wait_for(t, timeout=2)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    t.cancel()
        return {"exit_code": exit_code, "log_path": log_path}

    state = await tasks.register(
        task_type="shell",
        description=command[:200],
        runner=_runner,
        output_file=log_path,
    )
    return ToolResult.ok(
        content={
            "task_id": state.id,
            "status": state.status,
            "log_path": log_path,
            "command": command,
        },
        output={"task_id": state.id, "log_path": log_path},
        content_ref=log_path,
    )


def _kill_tree(pid: int) -> None:
    """Kill the process tree rooted at ``pid``. Best-effort; swallows
    ProcessLookupError when the group is already gone.
    """
    try:
        pgid = os.getpgid(pid)
        os.killpg(pgid, signal.SIGTERM)
        # Give it 1s, then SIGKILL.
        time.sleep(1)
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass
    except (ProcessLookupError, OSError):
        # Already gone or no process group — fall back to single PID.
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass
