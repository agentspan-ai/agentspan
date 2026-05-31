#!/usr/bin/env python3
"""Quickstart test harness — runs all examples in parallel and validates results.

Assertions:
  a) All agents complete with status COMPLETED
  b) Each finishes within 30 seconds
  c) Tool calls (if any) completed successfully — no COMPLETED_WITH_ERRORS
  d) Guardrails (if any) completed successfully

Usage:
  uv run python quickstart/run_all.py
"""

import importlib.util
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List

import httpx

from agentspan.agents import AgentRuntime

# Import agents and prompts from quickstart examples (filenames start with digits)
_quickstart_dir = Path(__file__).parent


def _load_module(filename: str):
    """Load a Python module from a file whose name isn't a valid identifier."""
    path = _quickstart_dir / filename
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_m01 = _load_module("01_basic_agent.py")
_m02 = _load_module("02_tools.py")
_m03 = _load_module("03_multi_agent.py")
_m04 = _load_module("04_guardrails.py")
# NOTE: 05_claude_code is excluded — Claude Code agents need string tool names
# (e.g. "Read", "Glob") which require the framework worker subprocess.

# ── Config ──────────────────────────────────────────────

TIMEOUT_SECONDS = 30
SERVER_URL = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")


@dataclass
class TestCase:
    name: str
    agent: Any
    prompt: str
    expect_tools: bool = False
    expect_guardrails: bool = False


@dataclass
class TestResult:
    name: str
    passed: bool
    duration_s: float
    errors: List[str] = field(default_factory=list)


TESTS = [
    TestCase("01_basic_agent", _m01.agent, _m01.prompt),
    TestCase("02_tools", _m02.agent, _m02.prompt, expect_tools=True),
    TestCase("03_multi_agent", _m03.agent, _m03.prompt),
    TestCase("04_guardrails", _m04.agent, _m04.prompt, expect_guardrails=True),
]

# ── Helpers ─────────────────────────────────────────────


def fetch_execution(execution_id: str) -> dict:
    """Fetch the full Conductor execution with all tasks."""
    url = f"{SERVER_URL}/agent/executions/{execution_id}/full"
    resp = httpx.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()


# System task types managed by Conductor/AgentSpan — everything else is a tool worker task
SYSTEM_TASK_TYPES = {
    "LLM_CHAT_COMPLETE", "SET_VARIABLE", "DO_WHILE", "SWITCH", "FORK", "JOIN",
    "INLINE", "SUB_WORKFLOW", "HUMAN", "TERMINATE", "WAIT", "EVENT",
    "JSON_JQ_TRANSFORM", "KAFKA_PUBLISH", "HTTP",
}


def _is_tool_task(task: dict) -> bool:
    return task.get("taskType") not in SYSTEM_TASK_TYPES


def validate_tasks(execution: dict, test_case: TestCase) -> List[str]:
    """Validate individual task statuses in the execution."""
    errors = []
    tasks = execution.get("tasks", [])

    for task in tasks:
        task_name = task.get("referenceTaskName") or task.get("taskType") or "unknown"
        status = task.get("status")

        # Tool tasks: must not be COMPLETED_WITH_ERRORS or FAILED
        if _is_tool_task(task):
            if status == "COMPLETED_WITH_ERRORS":
                errors.append(f'Tool task "{task_name}" completed with errors')
            if status in ("FAILED", "FAILED_WITH_TERMINAL_ERROR"):
                errors.append(f'Tool task "{task_name}" failed with status {status}')

        # SUB_WORKFLOW tasks (multi-agent)
        if task.get("taskType") == "SUB_WORKFLOW":
            if status in ("FAILED", "COMPLETED_WITH_ERRORS"):
                errors.append(f'Sub-workflow task "{task_name}" has status {status}')

        # Guardrail tasks
        if "guardrail" in task_name.lower() or task.get("taskType") == "INLINE":
            if status in ("FAILED", "COMPLETED_WITH_ERRORS"):
                errors.append(f'Guardrail task "{task_name}" has status {status}')

    # If we expected tools, verify at least one tool call exists
    if test_case.expect_tools:
        tool_tasks = [t for t in tasks if _is_tool_task(t)]
        if not tool_tasks:
            errors.append("Expected tool calls but found none")

    return errors


# ── Runner ──────────────────────────────────────────────


def run_test(test_case: TestCase) -> TestResult:
    """Run a single test case and validate the result."""
    start = time.monotonic()
    errors = []

    try:
        with AgentRuntime() as runtime:
            result = runtime.run(agent=test_case.agent, prompt=test_case.prompt)
            duration_s = time.monotonic() - start

            # (a) Must complete successfully
            if not result.is_success:
                errors.append(
                    f"Expected COMPLETED but got {result.status}"
                    + (f": {result.error}" if result.error else "")
                )

            # (b) Must finish within 30 seconds
            if duration_s > TIMEOUT_SECONDS:
                errors.append(f"Took {duration_s:.1f}s (limit: {TIMEOUT_SECONDS}s)")

            # (c) & (d) Validate individual task statuses
            try:
                execution = fetch_execution(result.execution_id)
                task_errors = validate_tasks(execution, test_case)
                errors.extend(task_errors)
            except Exception as e:
                errors.append(f"Failed to fetch execution details: {e}")

            return TestResult(test_case.name, len(errors) == 0, duration_s, errors)

    except Exception as e:
        return TestResult(test_case.name, False, time.monotonic() - start, [str(e)])


# ── Main ────────────────────────────────────────────────


def main() -> None:
    print(f"\nRunning {len(TESTS)} quickstart examples in parallel...\n")

    with ThreadPoolExecutor(max_workers=len(TESTS)) as pool:
        futures = {pool.submit(run_test, t): t for t in TESTS}

        results = []
        for future in as_completed(futures):
            results.append(future.result())

    # Sort by name for consistent output
    results.sort(key=lambda r: r.name)

    # Print results
    all_passed = True
    for r in results:
        icon = "\033[32mPASS\033[0m" if r.passed else "\033[31mFAIL\033[0m"
        print(f"  [{icon}] {r.name} ({r.duration_s:.1f}s)")
        for err in r.errors:
            print(f"         -> {err}")
        if not r.passed:
            all_passed = False

    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    print(f"\n{passed} passed, {failed} failed out of {len(results)}\n")

    if not all_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
