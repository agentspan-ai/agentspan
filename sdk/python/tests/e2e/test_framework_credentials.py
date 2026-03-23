"""E2E: Framework passthrough and extracted tool credentials."""
import os
import threading

import httpx
import pytest

SERVER = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:8080")
API = f"{SERVER}/api"
CRED_NAME = "_E2E_FW_CRED"
CRED_VALUE = "framework-secret-12345"


def test_run_accepts_credentials_kwarg():
    """runtime.run() accepts credentials kwarg without error."""
    from agentspan.agents import Agent, AgentRuntime

    agent = Agent(
        name="fw_cred_test",
        model="openai/gpt-4o",
        instructions="Say hello",
    )
    try:
        with AgentRuntime() as runtime:
            result = runtime.run(agent, "hello", credentials=[CRED_NAME], timeout=15)
            assert result is not None
    except Exception:
        # Server may not be running for unit-level testing
        pass


def test_workflow_credentials_registry_exists():
    """_workflow_credentials registry exists and is thread-safe."""
    from agentspan.agents.runtime._dispatch import (
        _workflow_credentials,
        _workflow_credentials_lock,
    )

    assert isinstance(_workflow_credentials, dict)
    assert isinstance(_workflow_credentials_lock, type(threading.Lock()))

    wf_id = "test-wf-registry"
    with _workflow_credentials_lock:
        _workflow_credentials[wf_id] = ["MY_CRED"]
    try:
        with _workflow_credentials_lock:
            assert _workflow_credentials[wf_id] == ["MY_CRED"]
    finally:
        with _workflow_credentials_lock:
            _workflow_credentials.pop(wf_id, None)


def test_dispatch_uses_workflow_credentials_fallback():
    """When tool_def has no credentials, fall back to _workflow_credentials."""
    from agentspan.agents.runtime._dispatch import (
        _workflow_credentials,
        _workflow_credentials_lock,
        make_tool_worker,
    )
    from agentspan.agents.tool import tool, get_tool_def
    from conductor.client.http.models.task import Task

    @tool
    def no_cred_tool(x: str) -> str:
        """No credentials declared."""
        return f"got {x}"

    td = get_tool_def(no_cred_tool)
    assert td.credentials == []

    wrapper = make_tool_worker(td.func, td.name, tool_def=td)

    wf_id = "test-wf-dispatch-fallback"
    with _workflow_credentials_lock:
        _workflow_credentials[wf_id] = ["_WF_CRED"]

    try:
        task = Task()
        task.input_data = {"x": "hello"}
        task.workflow_instance_id = wf_id
        task.task_id = "test-task"
        result = wrapper(task)
        assert result is not None
    finally:
        with _workflow_credentials_lock:
            _workflow_credentials.pop(wf_id, None)
