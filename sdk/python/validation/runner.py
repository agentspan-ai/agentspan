"""Example execution and server health check."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import MODELS
from .models import Example, RunResult
from .parsing import parse_output


def _decode(val: str | bytes | None) -> str:
    if val is None:
        return ""
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace")
    return val


def check_server_health(server_url: str | None = None) -> bool:
    try:
        import urllib.request

        url = server_url or os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:8080/api")
        base = url.rstrip("/api").rstrip("/")
        health_url = f"{base}/health"
        req = urllib.request.Request(health_url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def run_example(
    example: Example,
    model_name: str,
    model_id: str,
    timeout: int,
    retries: int,
    server_url: str | None = None,
) -> RunResult:
    env = os.environ.copy()
    env["AGENTSPAN_LLM_MODEL"] = model_id
    if server_url:
        env["AGENTSPAN_SERVER_URL"] = server_url

    base_name = example.name.split("/")[-1]
    from .groups import HITL_STDIN

    stdin_data = None
    for prefix, response in HITL_STDIN.items():
        if base_name.startswith(prefix):
            stdin_data = response + "\n"
            break

    result = RunResult()
    for attempt in range(1 + retries):
        start = time.monotonic()
        try:
            proc = subprocess.run(
                [sys.executable, str(example.path)],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=str(example.cwd),
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


def run_example_all(
    example: Example,
    timeout: int,
    retries: int,
    models: dict[str, str] | None = None,
    server_urls: dict[str, str] | None = None,
) -> dict[str, RunResult]:
    active_models = models or MODELS
    results = {}
    with ThreadPoolExecutor(max_workers=len(active_models)) as pool:
        futures = {
            pool.submit(
                run_example,
                example,
                name,
                model_id,
                timeout,
                retries,
                server_url=(server_urls or {}).get(name),
            ): name
            for name, model_id in active_models.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            results[name] = future.result()
    return results


def compute_match(results: dict[str, RunResult]) -> tuple[str, str, str]:
    notes_parts = []
    completed = {k for k, r in results.items() if r.status == "COMPLETED"}
    failed = {k: r for k, r in results.items() if r.status != "COMPLETED"}

    if len(completed) == len(results):
        match = "PASS"
        tool_counts = {k: r.tool_calls for k, r in results.items()}
        if len(set(tool_counts.values())) > 1:
            notes_parts.append(
                "tool_calls differ: " + " ".join(f"{k}={v}" for k, v in tool_counts.items())
            )
            confidence = "MEDIUM"
        else:
            confidence = "HIGH"
    elif len(completed) == 0:
        match = "FAIL"
        confidence = "N/A"
        notes_parts.append("all failed: " + " ".join(f"{k}={r.status}" for k, r in failed.items()))
    else:
        match = "PARTIAL"
        confidence = "LOW"
        for k, r in failed.items():
            notes_parts.append(f"{k} {r.status}")

    return match, confidence, "; ".join(notes_parts)
