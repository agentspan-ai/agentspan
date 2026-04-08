"""Cross-SDK e2e test infrastructure.

Requires a running agentspan server. No mocks.
Validates workflow output via the server REST API.
"""
import os
import time
import warnings

import pytest
import requests

# macOS fork() warning is expected — Conductor workers use fork-based multiprocessing
warnings.filterwarnings("ignore", message=".*fork.*", category=DeprecationWarning)


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "integration: e2e tests requiring a live server")

SERVER_URL = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
BASE_URL = SERVER_URL.rstrip("/").replace("/api", "")

@pytest.fixture(scope="session", autouse=True)
def verify_server():
    """Fail fast if server isn't running."""
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        assert resp.json()["healthy"], "Server is not healthy"
    except Exception as e:
        pytest.skip(f"Server not available: {e}")

def get_workflow(execution_id: str) -> dict:
    """Fetch full workflow details from server API."""
    resp = requests.get(f"{BASE_URL}/api/workflow/{execution_id}", timeout=10)
    resp.raise_for_status()
    return resp.json()

def get_task_output(execution_id: str, task_name: str) -> dict:
    """Get output of a specific task in a workflow."""
    wf = get_workflow(execution_id)
    for task in wf.get("tasks", []):
        if task.get("taskDefName") == task_name:
            return task.get("outputData", {})
    return {}

def assert_workflow_completed(execution_id: str):
    """Assert workflow completed successfully."""
    wf = get_workflow(execution_id)
    assert wf["status"] == "COMPLETED", f"Workflow {execution_id} status: {wf['status']}, reason: {wf.get('reasonForIncompletion', '')}"

def assert_workflow_failed(execution_id: str, error_contains: str = ""):
    """Assert workflow failed (for negative tests)."""
    wf = get_workflow(execution_id)
    assert wf["status"] in ("FAILED", "TERMINATED"), f"Expected failure but got: {wf['status']}"
    if error_contains:
        reason = wf.get("reasonForIncompletion", "")
        assert error_contains.lower() in reason.lower(), f"Expected '{error_contains}' in reason: {reason}"

def assert_task_exists(execution_id: str, task_name: str):
    """Assert a task with the given name exists in the workflow."""
    wf = get_workflow(execution_id)
    task_names = [t.get("taskDefName", "") for t in wf.get("tasks", [])]
    assert task_name in task_names, f"Task '{task_name}' not found. Tasks: {task_names}"

def assert_required_workers_returned(start_response: dict):
    """Assert the server returned requiredWorkers in the start response."""
    assert "requiredWorkers" in start_response or "required_workers" in start_response, \
        f"Server did not return requiredWorkers. Keys: {list(start_response.keys())}"


@pytest.fixture(autouse=True)
def _clear_conductor_worker_registry():
    """Clear the Conductor global worker registry between tests.

    The Conductor SDK stores ``@worker_task``-decorated functions in a
    module-level dict keyed by ``(task_name, domain)``
    (``_decorated_functions`` in ``conductor.client.automator.task_handler``).
    With pytest-xdist, each gw process runs tests sequentially in the same
    Python process.  Without cleanup, this dict accumulates every tool
    registered across all prior tests in that process.

    The accumulation is harmful: each new ``AgentRuntime`` calls
    ``get_registered_workers()`` which iterates the entire dict and spawns
    a multiprocessing worker process per entry.  By the 10th test in a gw
    process, a runtime may spawn 5–10 worker processes simultaneously.
    On a resource-constrained CI machine running several gw processes in
    parallel this causes some worker processes to fail to start, leaving
    their Conductor tasks in queue until ``response_timeout_seconds``
    expires — previously 3600 s, now 120 s.

    Clearing the dict after each test ensures every test starts with exactly
    the workers it registered, regardless of test order or gw assignment.
    """
    yield
    try:
        from conductor.client.automator.task_handler import _decorated_functions
        _decorated_functions.clear()
    except ImportError:
        pass
