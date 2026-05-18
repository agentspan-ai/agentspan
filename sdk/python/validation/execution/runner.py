"""Example execution and server health check."""

from __future__ import annotations

import os
import subprocess
import sys
import time

from ..config import SCRIPT_DIR
from ..models import Example, RunResult
from ..parsing import parse_output

_PROJECT_ROOT = str(SCRIPT_DIR.parent)


def _decode(val: str | bytes | None) -> str:
    if val is None:
        return ""
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace")
    return val


def check_server_health(server_url: str | None = None) -> bool:
    try:
        import urllib.request

        url = server_url or os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
        base = url.rstrip("/api").rstrip("/")
        health_url = f"{base}/health"
        req = urllib.request.Request(health_url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def build_resolved_env(
    model_id: str,
    server_url: str | None,
    secondary_model: str | None = None,
    global_env: dict | None = None,
    run_env: dict | None = None,
) -> dict:
    """Build a per-run env dict without mutating os.environ."""
    env = os.environ.copy()
    if global_env:
        env.update(global_env)
    if run_env:
        env.update(run_env)
    env["AGENTSPAN_LLM_MODEL"] = model_id
    if server_url:
        env["AGENTSPAN_SERVER_URL"] = server_url
    if secondary_model:
        env["AGENTSPAN_SECONDARY_LLM_MODEL"] = secondary_model
    return env


def run_example(
    example: Example,
    model_name: str,
    model_id: str,
    timeout: int,
    retries: int,
    server_url: str | None = None,
    native: bool = False,
    secondary_model: str | None = None,
    extra_env: dict | None = None,
) -> RunResult:
    env = build_resolved_env(model_id, server_url, secondary_model, run_env=extra_env)

    base_name = example.name.split("/")[-1]
    from ..groups import HITL_STDIN

    stdin_data = None
    for prefix, response in HITL_STDIN.items():
        if base_name.startswith(prefix):
            stdin_data = response + "\n"
            break

    result = RunResult()
    for attempt in range(1 + retries):
        start = time.monotonic()
        try:
            cmd = (
                [sys.executable, "-m", "validation.native.shim", str(example.path)]
                if native
                else [sys.executable, str(example.path)]
            )
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=_PROJECT_ROOT if native else str(example.cwd),
                input=stdin_data,
            )
            duration = time.monotonic() - start
            result = parse_output(proc.stdout, proc.stderr, proc.returncode, duration, False)
        except subprocess.TimeoutExpired as e:
            duration = time.monotonic() - start
            result = parse_output(_decode(e.stdout), _decode(e.stderr), 124, duration, True)

        if result.exit_code == 0 or attempt == retries:
            if attempt > 0:
                result.error_summary = f"(retry {attempt}/{retries}) {result.error_summary}"
            return result

    return result
