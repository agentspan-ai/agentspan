"""Unit tests for HookRunner."""

from __future__ import annotations

import asyncio

import pytest

from agentspan.harness.hooks.runner import Hook, HookOutcome, HookRunner
from agentspan.harness.tools.contract import ToolResult, ToolUseContext


@pytest.fixture
def ctx():
    return ToolUseContext(cwd="/tmp", session_id="t", abort=asyncio.Event())


@pytest.mark.asyncio
async def test_pre_tool_hook_can_block(ctx):
    runner = HookRunner()

    async def block(name, input, c):
        return HookOutcome(blocked=True, message="nope")

    runner.register(Hook(name="b", event="pre_tool_use", fn=block))
    out = await runner.pre_tool_use(tool_name="x", input={}, context=ctx)
    assert out.blocked
    assert out.message == "nope"
    assert out.hook_name == "b"


@pytest.mark.asyncio
async def test_pre_tool_hook_can_rewrite_input(ctx):
    runner = HookRunner()

    async def rewrite(name, input, c):
        return HookOutcome(updated_input={**input, "added": True})

    runner.register(Hook(name="r", event="pre_tool_use", fn=rewrite))
    out = await runner.pre_tool_use(tool_name="x", input={"a": 1}, context=ctx)
    assert not out.blocked
    assert out.updated_input == {"a": 1, "added": True}


@pytest.mark.asyncio
async def test_post_tool_hook_runs_and_does_not_block(ctx):
    runner = HookRunner()
    seen = []

    async def collect(name, input, result, c):
        seen.append((name, result.content))

    runner.register(Hook(name="c", event="post_tool_use", fn=collect))
    await runner.post_tool_use(
        tool_name="x", input={}, result=ToolResult.ok(content="hi"), context=ctx
    )
    assert seen == [("x", "hi")]


@pytest.mark.asyncio
async def test_hook_timeout_fails_closed_for_pre(ctx):
    runner = HookRunner()

    async def slow(name, input, c):
        await asyncio.sleep(2.0)
        return HookOutcome()

    runner.register(Hook(name="s", event="pre_tool_use", fn=slow, timeout_seconds=0.05))
    out = await runner.pre_tool_use(tool_name="x", input={}, context=ctx)
    assert out.blocked
    assert "timeout" in out.message


@pytest.mark.asyncio
async def test_hook_exception_does_not_crash(ctx):
    runner = HookRunner()

    async def boom(name, input, result, c):
        raise RuntimeError("hook failed")

    runner.register(Hook(name="b", event="post_tool_use", fn=boom))
    # Should not raise.
    await runner.post_tool_use(
        tool_name="x", input={}, result=ToolResult.ok(content=""), context=ctx
    )


@pytest.mark.asyncio
async def test_session_start_runs_all(ctx):
    runner = HookRunner()
    calls = []

    async def a(c):
        calls.append("a")

    async def b(c):
        calls.append("b")

    runner.register(Hook(name="a", event="session_start", fn=a))
    runner.register(Hook(name="b", event="session_start", fn=b))
    await runner.session_start(ctx)
    assert calls == ["a", "b"]


@pytest.mark.asyncio
async def test_stop_hook_replacement(ctx):
    runner = HookRunner()

    async def replace(c, txt):
        return f"[REWRITTEN] {txt}"

    runner.register(Hook(name="r", event="stop", fn=replace))
    out = await runner.stop(context=ctx, final_text="done")
    assert out == "[REWRITTEN] done"
