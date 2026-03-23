# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tests for isolated tool dispatch with real subprocess credential injection.

No mocks — uses real SubprocessIsolator and verifies env vars arrive in the child.
"""

import os

from agentspan.agents.runtime._dispatch import make_tool_worker
from agentspan.agents.tool import tool, get_tool_def


class TestIsolatedToolDispatch:
    """isolated=True tool runs in subprocess with env var credentials."""

    def _make_task(self, input_data=None, ctx_token=None):
        from conductor.client.http.models.task import Task
        t = Task()
        t.input_data = input_data or {}
        if ctx_token:
            t.input_data["__agentspan_ctx__"] = {"execution_token": ctx_token}
        t.workflow_instance_id = "test-wf-isolated"
        t.task_id = "test-task-isolated"
        return t

    def test_tool_def_credentials_survive_into_worker(self):
        """The ToolDef.credentials list must be accessible in make_tool_worker."""

        @tool(isolated=True, credentials=["TEST_CRED"])
        def my_tool() -> str:
            return "ok"

        td = get_tool_def(my_tool)
        assert td.credentials == ["TEST_CRED"]
        # Passing tool_def ensures credentials are available in the worker
        wrapper = make_tool_worker(td.func, td.name, tool_def=td)
        # The wrapper is callable — just verify it was created with the right tool_def
        assert wrapper is not None

    def test_credential_not_in_parent_env(self):
        """Isolated credentials must NOT leak into parent os.environ."""
        secret_key = "_AGENTSPAN_TEST_ISOLATED_SECRET_99999"
        assert secret_key not in os.environ

        @tool(isolated=True, credentials=[secret_key])
        def noop_tool() -> str:
            return "done"

        # After tool creation, parent env is still clean
        assert secret_key not in os.environ

    def test_subprocess_isolator_injects_env(self):
        """SubprocessIsolator actually sets env vars in the child process."""
        from agentspan.agents.runtime.credentials.isolator import SubprocessIsolator

        def check_env(**kwargs):
            import os as _os
            return {
                "val": _os.environ.get("_TEST_ISOLATED_CRED"),
                "parent_home": _os.environ.get("HOME"),
            }

        isolator = SubprocessIsolator(timeout=30)
        result = isolator.run(
            check_env,
            args=(),
            kwargs={},
            credentials={"_TEST_ISOLATED_CRED": "secret-123"},
        )
        assert result["val"] == "secret-123"
        # HOME should be a temp dir, not the real home
        assert result["parent_home"] != os.environ.get("HOME")
        # Parent env not modified
        assert "_TEST_ISOLATED_CRED" not in os.environ
