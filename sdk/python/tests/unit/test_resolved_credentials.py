"""Embedded host-delivered credential path: the worker prefers
``__resolved_credentials__`` from task input (resolved by the host from
``${workflow.secrets.NAME}``) over the native execution-token pull.
"""

from unittest.mock import patch

from conductor.ai.agents.runtime._dispatch import make_tool_worker
from conductor.ai.agents.runtime.credentials.accessor import get_secret
from conductor.ai.agents.tool import get_tool_def, tool
from conductor.client.http.models.task import Task


def _worker():
    @tool(credentials=["GITHUB_TOKEN"])
    def read_token() -> str:
        return get_secret("GITHUB_TOKEN")

    td = get_tool_def(read_token)
    return make_tool_worker(td.func, td.name, tool_def=td)


def test_prefers_host_delivered_resolved_credentials():
    wrapper = _worker()
    task = Task()
    task.input_data = {"__resolved_credentials__": {"GITHUB_TOKEN": "ghp_host_resolved"}}
    task.workflow_instance_id = "wf"
    task.task_id = "t"

    # The native fetcher must NOT be consulted when the host already delivered the map.
    with patch("conductor.ai.agents.runtime._dispatch._get_credential_fetcher") as mock_fetcher:
        result = wrapper(task)

    assert result.status == "COMPLETED"
    assert result.output_data["result"] == "ghp_host_resolved"
    mock_fetcher.assert_not_called()


def test_falls_back_to_native_fetch_when_no_resolved_map():
    wrapper = _worker()
    task = Task()
    task.input_data = {"__agentspan_ctx__": {"execution_token": "tok"}}
    task.workflow_instance_id = "wf"
    task.task_id = "t"

    class _Fetcher:
        def fetch(self, token, names):
            assert token == "tok"
            assert names == ["GITHUB_TOKEN"]
            return {"GITHUB_TOKEN": "ghp_native_pull"}

    with patch(
        "conductor.ai.agents.runtime._dispatch._get_credential_fetcher",
        return_value=_Fetcher(),
    ):
        result = wrapper(task)

    assert result.status == "COMPLETED"
    assert result.output_data["result"] == "ghp_native_pull"
