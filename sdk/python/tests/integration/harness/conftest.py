# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Per-test ``AgentRuntime`` + leftover-workflow cleanup for the harness
integration suite.

The default ``runtime`` fixture (in ``tests/integration/conftest.py``) is
module-scoped so the worker manager starts once per file. That works for
agentspan ``Agent`` tests because tool workers are pure ``@tool`` functions
with no per-test state.

The harness adapter is different: each ``HarnessRuntime`` builds tool
worker wrappers whose closures capture *that* runtime's state. We use a
name-keyed registry to route stale workers to the current harness, but
function-scoping the runtime gives each test a clean worker set as well.

We also kill any lingering ``harness_*`` workflows at module-load time so
abandoned tests from prior runs don't clog Conductor's task queues.
"""

from __future__ import annotations

import os

import pytest
import requests

from agentspan.agents import AgentRuntime
from agentspan.agents.runtime.config import AgentConfig

_SERVER_URL = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")


def _conductor_base() -> str:
    return _SERVER_URL.rstrip("/").replace("/api", "")


_HARNESS_TOOL_QUEUES = (
    "shell", "read_file", "write_file", "patch_file", "list_files",
    "search_text", "structured_output", "update_plan",
    "delete_file", "file_outline", "find_references",
    "shared_store_read", "shared_store_write", "shared_store_list",
    "read_task_output", "stop_task", "spawn_agent",
    "setup_repo", "fetch_issue", "fetch_pr", "open_pr",
)


def _terminate_running_harness_workflows() -> int:
    """Best-effort cleanup of leftover RUNNING ``harness_*`` workflows from
    crashed tests. Returns count terminated."""
    try:
        base = _conductor_base()
        resp = requests.get(
            f"{base}/api/workflow/search",
            params={"query": "status IN (RUNNING)", "size": 500},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("results", []) or []
        ids = [
            r["workflowId"] for r in results
            if "harness" in (r.get("workflowType") or "")
        ]
        for wid in ids:
            try:
                # DELETE actually terminates; POST .../terminate is a no-op
                # in this Conductor build.
                requests.delete(f"{base}/api/workflow/{wid}", timeout=5)
            except Exception:
                pass
        return len(ids)
    except Exception:
        return 0


def _drain_harness_tool_queues() -> int:
    """Drain SCHEDULED tasks for harness tool names from a polluted queue.

    After ``_terminate_running_harness_workflows`` the workflows are gone
    but their queued tool tasks remain. We poll-and-fail each one so a
    fresh test's worker doesn't have to grind through them first.
    """
    base = _conductor_base()
    drained = 0
    for q in _HARNESS_TOOL_QUEUES:
        for _ in range(50):  # bounded
            try:
                r = requests.get(
                    f"{base}/api/tasks/poll/{q}",
                    params={"workerid": "harness-cleanup"},
                    timeout=3,
                )
            except Exception:
                break
            if r.status_code != 200 or not r.text or r.text == "null":
                break
            try:
                data = r.json()
            except Exception:
                break
            if not data or not isinstance(data, dict):
                break
            tid = data.get("taskId")
            if not tid:
                break
            try:
                requests.post(
                    f"{base}/api/tasks",
                    json={
                        "taskId": tid,
                        "workflowInstanceId": data.get("workflowInstanceId"),
                        "status": "FAILED_WITH_TERMINAL_ERROR",
                        "reasonForIncompletion": "drained by harness test cleanup",
                        "outputData": {},
                    },
                    timeout=3,
                )
                drained += 1
            except Exception:
                break
    return drained


@pytest.fixture(scope="session", autouse=True)
def _cleanup_stale_harness_workflows():
    """Drain leftover ``harness_*`` workflows + tool queues once per session.

    Without this, abandoned tasks from prior crashed runs keep tool queues
    populated with stale SCHEDULED entries. A fresh test's worker picks
    those up first and starves the new test of its own tool task.
    """
    _terminate_running_harness_workflows()
    _drain_harness_tool_queues()
    yield


@pytest.fixture(autouse=True)
def _per_test_cleanup():
    """Before AND after each test, drain leftover harness workflows + queues.

    Each test creates its own workflow, and a fresh pytest invocation gets
    a clean AgentRuntime; but successive tests within ONE pytest run leave
    behind RUNNING workflows that pollute the queue with stale SCHEDULED
    tool tasks. Drain on both sides for symmetric isolation.
    """
    _terminate_running_harness_workflows()
    _drain_harness_tool_queues()
    yield
    _terminate_running_harness_workflows()
    _drain_harness_tool_queues()


@pytest.fixture
def runtime():
    """Function-scoped AgentRuntime — one per harness test, then shut down."""
    config = AgentConfig.from_env()
    with AgentRuntime(config=config) as rt:
        yield rt
