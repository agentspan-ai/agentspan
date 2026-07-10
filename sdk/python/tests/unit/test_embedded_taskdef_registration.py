"""Worker TaskDefs are registered create-only (overwrite_task_def=False): the SDK creates the def
when absent but never overwrites an existing one. When embedded, the host server pre-registers the
worker TaskDef and declares its secret names on TaskDef.runtimeMetadata (conductor-oss PR #1255);
overwriting here with a bare def (the client TaskDef model has no runtimeMetadata field) would clobber
that and starve the host resolver. This needs no embedded flag — the existence check chooses correctly.
"""

from unittest.mock import patch

from conductor.ai.agents.runtime.tool_registry import ToolRegistry
from conductor.ai.agents.tool import tool


def _worker_task_kwargs():
    @tool(credentials=["DEMO_SECRET"])
    def check_secret() -> dict:
        return {"ok": True}

    calls = []

    def fake_worker_task(**kwargs):
        calls.append(kwargs)
        return lambda fn: fn  # decorator passthrough

    with patch("conductor.client.worker.worker_task.worker_task", side_effect=fake_worker_task):
        ToolRegistry().register_tool_workers([check_secret], "secret_agent")
    return next(c for c in calls if c.get("task_definition_name") == "check_secret")


def test_worker_taskdef_is_create_only_never_overwrite():
    kwargs = _worker_task_kwargs()
    # create-only: register when missing, but never overwrite (preserves server runtimeMetadata).
    assert kwargs["register_task_def"] is True
    assert kwargs["overwrite_task_def"] is False
