# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tests for the dispatch module workers.

Tests cover the native-FC workers: check_approval_worker and make_tool_worker.
No mocks — tests exercise real code paths.
"""

import pytest

from agentspan.agents.runtime._dispatch import (
    _mcp_servers,
    _tool_approval_flags,
    _tool_registry,
    _tool_task_names,
    _tool_type_registry,
    check_approval_worker,
)

# ── helpers ──────────────────────────────────────────────────────────────


def _register_tools(name: str, funcs: dict):
    """Register tools under a fake task name and populate _tool_task_names."""
    _tool_registry[name] = funcs
    for fn_name in funcs:
        _tool_task_names[fn_name] = fn_name


@pytest.fixture(autouse=True)
def _clean_registry():
    """Clear all global registries between tests."""
    _tool_registry.clear()
    _tool_type_registry.clear()
    _tool_task_names.clear()
    _tool_approval_flags.clear()
    _mcp_servers.clear()
    yield
    _tool_registry.clear()
    _tool_type_registry.clear()
    _tool_task_names.clear()
    _tool_approval_flags.clear()
    _mcp_servers.clear()


# ── tests: check_approval_worker (native FC) ────────────────────────────


class TestCheckApprovalWorker:
    """Test check_approval_worker — checks _tool_approval_flags for any tool in batch."""

    def test_approval_required_single(self):
        _tool_approval_flags["danger"] = True
        result = check_approval_worker(tool_calls=[{"name": "danger"}])
        assert result["needs_approval"] is True

    def test_approval_required_in_batch(self):
        _tool_approval_flags["danger"] = True
        result = check_approval_worker(
            tool_calls=[
                {"name": "safe_tool"},
                {"name": "danger"},
            ]
        )
        assert result["needs_approval"] is True

    def test_no_approval(self):
        result = check_approval_worker(tool_calls=[{"name": "safe_tool"}])
        assert result["needs_approval"] is False

    def test_empty_tool_calls(self):
        result = check_approval_worker(tool_calls=[])
        assert result["needs_approval"] is False

    def test_none_tool_calls(self):
        result = check_approval_worker(tool_calls=None)
        assert result["needs_approval"] is False


class TestCredentialExtraction:
    """_dispatch.py extracts __agentspan_ctx__ from task input/variables."""

    def test_extract_token_from_input_data_dict(self):
        from agentspan.agents.runtime._dispatch import _extract_execution_token

        class FakeTask:
            input_data = {"__agentspan_ctx__": {"execution_token": "token-from-input"}, "x": "hello"}
            workflow_input = {}

        token = _extract_execution_token(FakeTask())
        assert token == "token-from-input"

    def test_extract_token_from_input_data_string(self):
        """Backwards compat: plain string is also accepted."""
        from agentspan.agents.runtime._dispatch import _extract_execution_token

        class FakeTask:
            input_data = {"__agentspan_ctx__": "token-from-input", "x": "hello"}
            workflow_input = {}

        token = _extract_execution_token(FakeTask())
        assert token == "token-from-input"

    def test_extract_token_returns_none_when_absent(self):
        from agentspan.agents.runtime._dispatch import _extract_execution_token

        class FakeTask:
            input_data = {"x": "hello"}
            workflow_input = {}

        token = _extract_execution_token(FakeTask())
        assert token is None

    def test_extract_token_from_workflow_input_dict(self):
        from agentspan.agents.runtime._dispatch import _extract_execution_token

        class FakeTask:
            input_data = {}
            workflow_input = {"__agentspan_ctx__": {"execution_token": "token-from-wf"}}

        token = _extract_execution_token(FakeTask())
        assert token == "token-from-wf"

    def test_extract_token_empty_dict_returns_none(self):
        from agentspan.agents.runtime._dispatch import _extract_execution_token

        class FakeTask:
            input_data = {"__agentspan_ctx__": {}}
            workflow_input = {}

        token = _extract_execution_token(FakeTask())
        assert token is None


class TestToolDefCredentialsSurvival:
    """Verify credentials from @tool decorator survive into make_tool_worker."""

    def test_tool_def_credentials_accessible_via_get_tool_def(self):
        from agentspan.agents.tool import tool, get_tool_def

        @tool(credentials=["MY_SECRET"])
        def my_tool(x: str) -> str:
            return x

        td = get_tool_def(my_tool)
        assert td.credentials == ["MY_SECRET"]

    def test_make_tool_worker_with_tool_def_has_credentials(self):
        """When tool_def is passed, make_tool_worker can access credentials."""
        from agentspan.agents.runtime._dispatch import make_tool_worker, _get_credential_names_from_tool
        from agentspan.agents.tool import tool, get_tool_def

        @tool(credentials=["GITHUB_TOKEN", "OPENAI_API_KEY"])
        def cred_tool(x: str) -> str:
            return x

        td = get_tool_def(cred_tool)
        # Both raw func and wrapper have _tool_def (needed for spawn-mode pickling)
        assert _get_credential_names_from_tool(td.func) == ["GITHUB_TOKEN", "OPENAI_API_KEY"]
        assert _get_credential_names_from_tool(cred_tool) == ["GITHUB_TOKEN", "OPENAI_API_KEY"]

    def test_no_credentials_tool_returns_empty(self):
        from agentspan.agents.tool import tool, get_tool_def

        @tool
        def simple_tool(x: str) -> str:
            return x

        td = get_tool_def(simple_tool)
        assert td.credentials == []

    def test_tool_worker_no_credentials_runs_directly(self):
        """Tool without credentials runs without subprocess isolation."""
        from agentspan.agents.runtime._dispatch import make_tool_worker
        from agentspan.agents.tool import tool, get_tool_def
        from conductor.client.http.models.task import Task

        @tool
        def add(a: int, b: int) -> int:
            return a + b

        td = get_tool_def(add)
        wrapper = make_tool_worker(td.func, td.name, tool_def=td)

        task = Task()
        task.input_data = {"a": 3, "b": 4}
        task.workflow_instance_id = "test-wf"
        task.task_id = "test-task"

        result = wrapper(task)
        assert result.status == "COMPLETED"
        assert result.output_data["result"] == 7
