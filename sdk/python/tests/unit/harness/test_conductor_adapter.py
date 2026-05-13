"""Unit tests for the Conductor adapter that wraps harness Tools as
Conductor SIMPLE-task workers.

The adapter is the new core: each ``Tool`` becomes a sync wrapper that
runs schema validation → permission → pre_tool_use hook → tool.call() →
post_tool_use hook, and returns a dict the Conductor task output picks up.
Every failure mode (deny / hook block / tool exception / schema error)
becomes an LLM-visible ``{is_error: True, ...}`` result, never a worker
exception.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

import pytest

from agentspan.harness import HarnessConfig, HarnessRuntime
from agentspan.harness.conductor_adapter import (
    _run_tool_async,
    wrap_tool_as_tool_def,
)
from agentspan.harness.hooks.runner import Hook, HookOutcome, HookRunner
from agentspan.harness.permission import (
    PermissionEngine,
    PermissionRule,
    RuleSource,
)
from agentspan.harness.permission.rules import PermissionMode
from agentspan.harness.tools.contract import Tool, ToolResult


class _Echo(Tool):
    @property
    def name(self): return "echo"
    @property
    def description(self): return "echo input"
    @property
    def input_schema(self):
        return {"type": "object", "properties": {"text": {"type": "string"}},
                "required": ["text"]}
    def is_read_only(self, input): return True
    def is_concurrency_safe(self, input): return True
    async def call(self, input, context, parent_message=None, on_progress=None):
        return ToolResult.ok(content=input["text"])


class _SideEffect(Tool):
    @property
    def name(self): return "side_effect"
    @property
    def description(self): return "writes"
    @property
    def input_schema(self): return {"type": "object", "properties": {}}
    def is_read_only(self, input): return False
    async def call(self, input, context, parent_message=None, on_progress=None):
        return ToolResult.ok(content="did it")


class _Boom(Tool):
    @property
    def name(self): return "boom"
    @property
    def description(self): return "raises"
    @property
    def input_schema(self): return {"type": "object", "properties": {}}
    def is_read_only(self, input): return True
    async def call(self, input, context, parent_message=None, on_progress=None):
        raise RuntimeError("boom")


def _runtime(*, hook_runner=None, rules=None) -> HarnessRuntime:
    return HarnessRuntime(HarnessConfig(
        model="fake/m",
        tools=[],
        permission_engine=PermissionEngine(rules=rules or [],
                                            mode=PermissionMode.DEFAULT),
        hook_runner=hook_runner,
    ))


@pytest.mark.asyncio
async def test_happy_path_returns_content():
    rt = _runtime()
    res = await _run_tool_async(_Echo(), {"text": "hi"}, rt)
    assert not res["is_error"]
    assert res["result"] == "hi"
    rt.close()


@pytest.mark.asyncio
async def test_schema_violation_becomes_error_result():
    rt = _runtime()
    res = await _run_tool_async(_Echo(), {}, rt)  # missing required 'text'
    assert res["is_error"]
    assert "Invalid input" in res["result"]
    rt.close()


@pytest.mark.asyncio
async def test_permission_deny_becomes_error_result():
    # Side-effecting tool with no allow rule → default-deny in DEFAULT mode.
    rt = _runtime()
    res = await _run_tool_async(_SideEffect(), {}, rt)
    assert res["is_error"]
    assert "Permission denied" in res["result"]
    rt.close()


@pytest.mark.asyncio
async def test_permission_allow_lets_through():
    rules = [PermissionRule(source=RuleSource.PROJECT, behavior="allow",
                            tool_name="side_effect")]
    rt = _runtime(rules=rules)
    res = await _run_tool_async(_SideEffect(), {}, rt)
    assert not res["is_error"]
    assert res["result"] == "did it"
    rt.close()


@pytest.mark.asyncio
async def test_pre_tool_hook_can_block():
    runner = HookRunner()

    async def block(name, input, ctx):
        return HookOutcome(blocked=True, message="nope", hook_name="b")

    runner.register(Hook(name="b", event="pre_tool_use", fn=block))
    rt = _runtime(hook_runner=runner)
    res = await _run_tool_async(_Echo(), {"text": "hi"}, rt)
    assert res["is_error"]
    assert "blocked" in res["result"]
    assert "nope" in res["result"]
    rt.close()


@pytest.mark.asyncio
async def test_pre_tool_hook_can_rewrite_input():
    runner = HookRunner()

    async def rewrite(name, input, ctx):
        return HookOutcome(updated_input={**input, "text": "rewritten"})

    runner.register(Hook(name="r", event="pre_tool_use", fn=rewrite))
    rt = _runtime(hook_runner=runner)
    res = await _run_tool_async(_Echo(), {"text": "original"}, rt)
    assert not res["is_error"]
    assert res["result"] == "rewritten"
    rt.close()


@pytest.mark.asyncio
async def test_tool_exception_becomes_error_result():
    rt = _runtime()
    res = await _run_tool_async(_Boom(), {}, rt)
    assert res["is_error"]
    assert "RuntimeError: boom" in res["result"]
    rt.close()


@pytest.mark.asyncio
async def test_post_tool_hook_runs_but_does_not_change_result():
    runner = HookRunner()
    seen = []

    async def collect(name, input, result, ctx):
        seen.append((name, result.content))

    runner.register(Hook(name="c", event="post_tool_use", fn=collect))
    rt = _runtime(hook_runner=runner)
    res = await _run_tool_async(_Echo(), {"text": "hello"}, rt)
    assert not res["is_error"]
    assert res["result"] == "hello"
    assert seen == [("echo", "hello")]
    rt.close()


def test_wrap_tool_as_tool_def_shape():
    """The wrapper produces a ToolDef the agentspan Agent can consume."""
    rt = _runtime()
    td = wrap_tool_as_tool_def(_Echo(), rt)
    assert td.name == "echo"
    assert td.description == "echo input"
    assert td.tool_type == "worker"
    assert callable(td.func)
    assert td.input_schema["properties"]["text"]["type"] == "string"
    rt.close()


def test_wrapper_func_runs_pipeline_synchronously():
    """The ToolDef.func is sync — Conductor's worker thread can call it."""
    rt = _runtime()
    td = wrap_tool_as_tool_def(_Echo(), rt)
    out = td.func(text="sync ok")
    assert not out["is_error"]
    assert out["result"] == "sync ok"
    rt.close()


def test_wrapper_strips_framework_kwargs():
    """ToolContext-style framework kwargs (`context`, `_state_updates`) are
    stripped before being passed as tool input."""
    rt = _runtime()
    td = wrap_tool_as_tool_def(_Echo(), rt)
    out = td.func(text="x", context="injected", _state_updates={})
    assert not out["is_error"]
    assert out["result"] == "x"
    rt.close()
