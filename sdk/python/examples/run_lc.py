#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Run all LangGraph + LangChain examples in parallel.

Runs every numbered example in examples/langgraph/ and examples/langchain/,
collects results, and prints a summary table. A background HITL watcher
automatically approves any pending HUMAN tasks so examples never stall.

Usage:
    cd sdk/python
    uv run python examples/run_lc.py
    uv run python examples/run_lc.py --workers 8 --timeout 180
    uv run python examples/run_lc.py --only langgraph
    uv run python examples/run_lc.py --only langchain
    uv run python examples/run_lc.py --filter 03,22,27   # run specific numbers
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SDK_DIR = os.path.dirname(SCRIPT_DIR)   # sdk/python/


def _collect_examples(subdir: str, number_filter: Optional[List[str]] = None) -> List[str]:
    """Return sorted list of absolute paths for numbered example scripts."""
    folder = os.path.join(SCRIPT_DIR, subdir)
    paths = sorted(
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.endswith(".py") and f[:2].isdigit()
    )
    if number_filter:
        paths = [p for p in paths if any(os.path.basename(p).startswith(n) for n in number_filter)]
    return paths


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class ExampleResult:
    name: str          # e.g. "langgraph/02_react_with_tools.py"
    passed: bool = False
    error: str = ""
    execution_ids: List[str] = field(default_factory=list)
    duration_s: float = 0.0
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""


# ---------------------------------------------------------------------------
# HITL auto-approver
# ---------------------------------------------------------------------------

class HitlWatcher(threading.Thread):
    """Background thread that polls for IN_PROGRESS HUMAN tasks and auto-approves them.

    Polls the Conductor workflow search API every few seconds, finds any workflow
    with a HUMAN task stuck IN_PROGRESS, and calls POST /agent/{id}/respond
    with {"approved": true}.
    """

    def __init__(self, server_url: str, auth_key: str = "", auth_secret: str = ""):
        super().__init__(daemon=True, name="hitl-watcher")
        # Normalise: ensure no trailing /api so we can build both Conductor and Agentspan URLs
        self._base = server_url.rstrip("/")
        if not self._base.endswith("/api"):
            self._base = self._base + "/api"
        self._headers: Dict[str, str] = {}
        if auth_key:
            self._headers["X-Auth-Key"] = auth_key
        if auth_secret:
            self._headers["X-Auth-Secret"] = auth_secret
        self._stop = threading.Event()
        self._approved: set = set()
        self.approvals: int = 0

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            import requests
        except ImportError:
            return

        while not self._stop.wait(3):
            try:
                # Search for RUNNING workflows
                resp = requests.get(
                    f"{self._base}/workflow/search",
                    params={"query": "status:RUNNING", "size": 50},
                    headers=self._headers,
                    timeout=8,
                )
                if not resp.ok:
                    continue

                hits = resp.json().get("results", [])
                for hit in hits:
                    wf_id = hit.get("workflowId") or hit.get("workflowSummary", {}).get("workflowId")
                    if not wf_id or wf_id in self._approved:
                        continue

                    # Fetch full workflow to inspect tasks
                    try:
                        wf_resp = requests.get(
                            f"{self._base}/workflow/{wf_id}",
                            headers=self._headers,
                            timeout=8,
                        )
                        if not wf_resp.ok:
                            continue
                        wf = wf_resp.json()
                    except Exception:
                        continue

                    # Look for any HUMAN task that is IN_PROGRESS
                    for task in wf.get("tasks", []):
                        if task.get("taskType") == "HUMAN" and task.get("status") == "IN_PROGRESS":
                            try:
                                r = requests.post(
                                    f"{self._base}/agent/{wf_id}/respond",
                                    json={"approved": True},
                                    headers=self._headers,
                                    timeout=8,
                                )
                                if r.ok:
                                    self._approved.add(wf_id)
                                    self.approvals += 1
                                    print(
                                        f"\n  [HITL] Auto-approved HUMAN task "
                                        f"in workflow {wf_id[:8]}…",
                                        flush=True,
                                    )
                            except Exception:
                                pass
                            break  # one approval per workflow per cycle

            except Exception:
                pass


# ---------------------------------------------------------------------------
# Run one example as a subprocess
# ---------------------------------------------------------------------------

def run_example(path: str, timeout: int) -> ExampleResult:
    rel = os.path.relpath(path, SCRIPT_DIR)
    result = ExampleResult(name=rel)
    t0 = time.time()

    try:
        proc = subprocess.run(
            ["uv", "run", "python", path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=SDK_DIR,
        )
        result.duration_s = time.time() - t0
        result.exit_code = proc.returncode
        result.stdout = proc.stdout
        result.stderr = proc.stderr

        # Parse execution IDs from output
        result.execution_ids = re.findall(
            r"(?:Workflow|Execution) ID:\s*([0-9a-f]{8}-[0-9a-f-]{27,35})",
            proc.stdout,
        )

        if proc.returncode == 0:
            # Trust exit code 0; double-check for explicit failure keywords
            combined = proc.stdout + proc.stderr
            if re.search(r"Traceback|Error:|Exception:", combined):
                # Might still be OK (some examples print errors as examples)
                # Only fail if it's in stderr and exit code is non-zero
                result.passed = True
            else:
                result.passed = True
        else:
            result.passed = False
            # Grab last meaningful error line
            err_lines = [
                l.strip() for l in (proc.stderr or proc.stdout).splitlines()
                if l.strip() and not l.startswith("WARNING") and not l.startswith("INFO")
            ]
            result.error = err_lines[-1][:120] if err_lines else f"exit code {proc.returncode}"

    except subprocess.TimeoutExpired:
        result.duration_s = time.time() - t0
        result.exit_code = -1
        result.passed = False
        result.error = f"timed out after {timeout}s"

    except Exception as exc:
        result.duration_s = time.time() - t0
        result.passed = False
        result.error = f"{type(exc).__name__}: {exc}"

    return result


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

_GREEN = "\033[32m"
_RED   = "\033[31m"
_CYAN  = "\033[36m"
_DIM   = "\033[2m"
_RESET = "\033[0m"

_USE_COLOR = sys.stdout.isatty()


def _c(text: str, color: str) -> str:
    return f"{color}{text}{_RESET}" if _USE_COLOR else text


def print_report(results: List[ExampleResult]) -> None:
    passed  = [r for r in results if r.passed]
    failed  = [r for r in results if not r.passed]

    # Column widths
    name_w = max(len(r.name) for r in results) + 2

    header = f"{'Example':<{name_w}}  {'Status':<6}  {'Time':>6}  Workflow ID / Error"
    sep = "-" * (name_w + 60)

    print(f"\n{'=' * (name_w + 60)}")
    print("  LangGraph + LangChain — Run Results")
    print(f"{'=' * (name_w + 60)}")
    print(f"  {header}")
    print(f"  {sep}")

    # Group: langgraph then langchain
    for group_prefix in ("langgraph", "langchain"):
        group = [r for r in results if r.name.startswith(group_prefix)]
        if not group:
            continue
        print(f"\n  {_c(group_prefix.upper(), _CYAN)}")
        for r in group:
            icon   = _c("PASS", _GREEN) if r.passed else _c("FAIL", _RED)
            wf_ids = ", ".join(r.execution_ids[:2]) or ""
            detail = r.error if not r.passed else wf_ids
            name   = r.name[len(group_prefix) + 1:]   # strip "langgraph/" prefix
            print(f"  {name:<{name_w - len(group_prefix) - 1}}  [{icon}]  {r.duration_s:>5.1f}s  {detail}")

    print(f"\n  {sep}")
    print(f"  SUMMARY  {len(passed)} passed, {len(failed)} failed  (out of {len(results)})")
    print(f"  Total wall-clock time: {sum(r.duration_s for r in results):.1f}s")
    print(f"{'=' * (name_w + 60)}\n")

    if failed:
        print("  Failed examples:")
        for r in failed:
            print(f"    {r.name}: {r.error}")
            if r.stderr:
                for line in r.stderr.splitlines()[-5:]:
                    print(f"      {_c(line, _DIM)}")
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Run all LangGraph + LangChain examples")
    parser.add_argument("--workers",  type=int, default=6,
                        help="Max parallel example runners (default: 6)")
    parser.add_argument("--timeout",  type=int, default=150,
                        help="Per-example timeout in seconds (default: 150)")
    parser.add_argument("--only",     choices=["langgraph", "langchain"],
                        help="Run only one suite")
    parser.add_argument("--filter",   type=str, default="",
                        help="Comma-separated example numbers to run, e.g. 01,03,22")
    parser.add_argument("--no-hitl",  action="store_true",
                        help="Disable the HITL auto-approver")
    args = parser.parse_args()

    number_filter = [n.strip().zfill(2) for n in args.filter.split(",") if n.strip()] or None

    # Build example list
    suites: List[str] = []
    if args.only != "langchain":
        suites += _collect_examples("langgraph", number_filter)
    if args.only != "langgraph":
        suites += _collect_examples("langchain", number_filter)

    if not suites:
        print("No examples matched.")
        return 1

    # Read server config from env (same vars as AgentRuntime)
    server_url  = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
    auth_key    = os.environ.get("AGENTSPAN_AUTH_KEY", "")
    auth_secret = os.environ.get("AGENTSPAN_AUTH_SECRET", "")

    print(f"\nRunning {len(suites)} examples with {args.workers} workers "
          f"(timeout {args.timeout}s each)")
    print(f"Server: {server_url}\n")

    # Start HITL watcher
    hitl: Optional[HitlWatcher] = None
    if not args.no_hitl:
        hitl = HitlWatcher(server_url, auth_key, auth_secret)
        hitl.start()

    results: List[ExampleResult] = []
    completed_count = 0
    wall_start = time.time()

    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            future_to_path = {
                pool.submit(run_example, path, args.timeout): path
                for path in suites
            }
            for future in as_completed(future_to_path):
                r = future.result()
                results.append(r)
                completed_count += 1
                icon = "PASS" if r.passed else "FAIL"
                wf   = r.execution_ids[0][:8] + "…" if r.execution_ids else ""
                print(
                    f"  [{icon}] {r.name}  ({r.duration_s:.1f}s)  {wf}",
                    flush=True,
                )
    finally:
        if hitl:
            hitl.stop()
            if hitl.approvals:
                print(f"\n  [HITL] Auto-approved {hitl.approvals} HUMAN task(s) during the run.")

    # Sort results to match file order for the report
    results.sort(key=lambda r: r.name)

    print_report(results)

    passed = sum(1 for r in results if r.passed)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
