"""Worker secrets arrive on the wire-only ``Task.runtime_metadata`` — the ONLY delivery path.

The conductor core resolves the names declared on the worker's ``TaskDef.runtimeMetadata`` at
poll time and injects the values onto ``Task.runtimeMetadata`` in the poll response (never
persisted). The SDK reads that map and exposes it via ``get_secret()``; there is no server
endpoint to call (the native ``POST /api/workers/secrets`` pull was removed).
"""

import json

from conductor.client.http.api_client import ApiClient
from conductor.client.http.models.task import Task

from conductor.ai.agents.runtime._dispatch import make_tool_worker
from conductor.ai.agents.runtime.credentials import ensure_runtime_metadata_field
from conductor.ai.agents.runtime.credentials.accessor import get_secret
from conductor.ai.agents.tool import get_tool_def, tool


def _worker():
    @tool(credentials=["GITHUB_TOKEN"])
    def read_token() -> str:
        return get_secret("GITHUB_TOKEN")

    td = get_tool_def(read_token)
    return make_tool_worker(td.func, td.name, tool_def=td)


def test_reads_host_delivered_runtime_metadata():
    wrapper = _worker()
    task = Task()
    task.input_data = {}
    task.runtime_metadata = {"GITHUB_TOKEN": "ghp_host_resolved"}
    task.workflow_instance_id = "wf"
    task.task_id = "t"

    result = wrapper(task)

    assert result.status == "COMPLETED"
    assert result.output_data["result"] == "ghp_host_resolved"


def test_missing_delivery_surfaces_via_get_secret():
    # No runtime_metadata on the task: the worker runs, and get_secret() inside the
    # tool raises CredentialNotFoundError -> the task fails with that reason. No
    # endpoint is consulted (there is none).
    wrapper = _worker()
    task = Task()
    task.input_data = {}
    task.runtime_metadata = None
    task.workflow_instance_id = "wf"
    task.task_id = "t"

    result = wrapper(task)

    assert result.status != "COMPLETED"


def test_task_compat_shim_deserializes_runtime_metadata_from_wire():
    """The published conductor-python Task model doesn't carry runtime_metadata; the
    swagger deserializer drops unregistered JSON keys. The _task_compat shim registers
    the field so poll responses keep the host-resolved values — this is the regression
    test for the silent wire-drop."""
    ensure_runtime_metadata_field()

    class _Response:
        def __init__(self, payload):
            self._payload = payload
            self.data = json.dumps(payload)

        def json(self):
            return self._payload

    wire = {
        "taskType": "read_token",
        "status": "IN_PROGRESS",
        "runtimeMetadata": {"GITHUB_TOKEN": "ghp_from_wire"},
    }
    task = ApiClient().deserialize(_Response(wire), Task)

    assert task.runtime_metadata == {"GITHUB_TOKEN": "ghp_from_wire"}
    assert task.task_type == "read_token"

    # A task without the field still deserializes cleanly.
    bare = ApiClient().deserialize(_Response({"taskType": "x", "status": "SCHEDULED"}), Task)
    assert bare.runtime_metadata is None
