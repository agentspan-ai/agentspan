# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for the dispatch module workers.

Tests cover the native-FC workers: check_approval_worker and make_tool_worker.
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

    def test_extract_token_from_input_data(self):
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


class TestMakeToolWorkerWithCredentials:
    """make_tool_worker integrates with credential fetching."""

    def _make_task(self, input_data=None, ctx_token=None):
        from conductor.client.http.models.task import Task
        t = Task()
        t.input_data = input_data or {}
        if ctx_token:
            t.input_data["__agentspan_ctx__"] = ctx_token
        t.workflow_instance_id = "test-wf-001"
        t.task_id = "test-task-001"
        return t

    def test_non_isolated_tool_sets_credential_context(self):
        """isolated=False tool receives credentials via context var."""
        from unittest.mock import patch, MagicMock
        from agentspan.agents.runtime._dispatch import make_tool_worker
        from agentspan.agents.runtime.credentials.accessor import get_credential
        from agentspan.agents.tool import ToolDef, tool

        captured_token = {}

        @tool(isolated=False, credentials=["GITHUB_TOKEN"])
        def my_tool(x: str) -> str:
            """Get credential in tool."""
            captured_token["val"] = get_credential("GITHUB_TOKEN")
            return "ok"

        mock_fetcher = MagicMock()
        mock_fetcher.fetch.return_value = {"GITHUB_TOKEN": "ghp_from_service"}

        with patch(
            "agentspan.agents.runtime._dispatch._get_credential_fetcher",
            return_value=mock_fetcher,
        ):
            wrapper = make_tool_worker(my_tool, "my_tool")
            task = self._make_task(input_data={"x": "hello"}, ctx_token="exec-token-abc")
            result = wrapper(task)

        assert result.status == "COMPLETED"
        assert captured_token["val"] == "ghp_from_service"
        mock_fetcher.fetch.assert_called_once_with("exec-token-abc", ["GITHUB_TOKEN"])

    def test_no_credentials_no_fetcher_call(self):
        """Tool with no credentials — fetcher is not called."""
        from unittest.mock import patch, MagicMock
        from agentspan.agents.runtime._dispatch import make_tool_worker
        from agentspan.agents.tool import tool

        @tool
        def simple_tool(x: str) -> str:
            """No credentials needed."""
            return f"hello {x}"

        mock_fetcher = MagicMock()

        with patch(
            "agentspan.agents.runtime._dispatch._get_credential_fetcher",
            return_value=mock_fetcher,
        ):
            wrapper = make_tool_worker(simple_tool, "simple_tool")
            task = self._make_task(input_data={"x": "world"})
            result = wrapper(task)

        assert result.status == "COMPLETED"
        mock_fetcher.fetch.assert_not_called()

    def test_credential_auth_error_fails_task(self):
        """CredentialAuthError → task marked FAILED."""
        from unittest.mock import patch, MagicMock
        from agentspan.agents.runtime._dispatch import make_tool_worker
        from agentspan.agents.runtime.credentials.types import CredentialAuthError
        from agentspan.agents.tool import tool

        @tool(isolated=False, credentials=["GITHUB_TOKEN"])
        def my_tool(x: str) -> str:
            """Tool."""
            return "ok"

        mock_fetcher = MagicMock()
        mock_fetcher.fetch.side_effect = CredentialAuthError("token expired")

        with patch(
            "agentspan.agents.runtime._dispatch._get_credential_fetcher",
            return_value=mock_fetcher,
        ):
            wrapper = make_tool_worker(my_tool, "my_tool")
            task = self._make_task(input_data={"x": "hello"}, ctx_token="expired-token")
            result = wrapper(task)

        assert result.status == "FAILED"
        assert "expired" in result.reason_for_incompletion.lower()
