"""Unit tests for the permission engine pipeline."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

import pytest

from agentspan.harness.permission import (
    PermissionEngine,
    PermissionMode,
    PermissionRule,
    RuleSource,
)
from agentspan.harness.tools.contract import (
    PermissionResult,
    Tool,
    ToolResult,
    ToolUseContext,
)


class _ReadOnlyTool(Tool[Dict[str, Any], str]):
    @property
    def name(self) -> str:
        return "read_only"

    @property
    def description(self) -> str:
        return "test"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    def is_read_only(self, input: Dict[str, Any]) -> bool:
        return True

    async def call(self, input, context, parent_message=None, on_progress=None):
        return ToolResult.ok(content="ok")


class _SideEffectTool(Tool[Dict[str, Any], str]):
    @property
    def name(self) -> str:
        return "shell"

    @property
    def description(self) -> str:
        return "test"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {"command": {"type": "string"}}}

    def is_read_only(self, input: Dict[str, Any]) -> bool:
        return False

    async def call(self, input, context, parent_message=None, on_progress=None):
        return ToolResult.ok(content="ok")


@pytest.fixture
def ctx():
    return ToolUseContext(cwd="/tmp", session_id="t", abort=asyncio.Event())


@pytest.mark.asyncio
async def test_readonly_tool_allowed_by_default(ctx):
    engine = PermissionEngine()
    decision = await engine.decide(tool=_ReadOnlyTool(), input={}, context=ctx)
    assert decision.behavior == "allow"
    assert decision.reason == "default:read_only"


@pytest.mark.asyncio
async def test_side_effect_tool_denied_without_rule(ctx):
    engine = PermissionEngine()
    decision = await engine.decide(
        tool=_SideEffectTool(), input={"command": "ls"}, context=ctx
    )
    assert decision.behavior == "deny"


@pytest.mark.asyncio
async def test_explicit_allow_rule(ctx):
    engine = PermissionEngine(
        rules=[
            PermissionRule(
                source=RuleSource.PROJECT,
                behavior="allow",
                tool_name="shell",
                pattern="ls*",
            )
        ]
    )
    decision = await engine.decide(
        tool=_SideEffectTool(), input={"command": "ls -l"}, context=ctx
    )
    assert decision.behavior == "allow"


@pytest.mark.asyncio
async def test_deny_beats_allow(ctx):
    """Even at lower-trust source, a deny rule wins over an allow."""
    engine = PermissionEngine(
        rules=[
            PermissionRule(
                source=RuleSource.SESSION,
                behavior="deny",
                tool_name="shell",
                pattern="rm*",
            ),
            PermissionRule(
                source=RuleSource.POLICY,  # higher trust
                behavior="allow",
                tool_name="shell",
                pattern="*",  # broader allow
            ),
        ]
    )
    decision = await engine.decide(
        tool=_SideEffectTool(), input={"command": "rm -rf"}, context=ctx
    )
    assert decision.behavior == "deny"


@pytest.mark.asyncio
async def test_plan_mode_blocks_side_effects(ctx):
    engine = PermissionEngine(mode=PermissionMode.PLAN)
    # Read-only tool: still allowed even in plan mode
    decision = await engine.decide(tool=_ReadOnlyTool(), input={}, context=ctx)
    assert decision.behavior == "allow"
    # Side-effecting tool: blocked
    decision = await engine.decide(
        tool=_SideEffectTool(), input={"command": "ls"}, context=ctx
    )
    assert decision.behavior == "deny"
    assert decision.reason == "mode:plan"


@pytest.mark.asyncio
async def test_dont_ask_mode_converts_ask_to_deny(ctx):
    engine = PermissionEngine(
        mode=PermissionMode.DONT_ASK,
        rules=[
            PermissionRule(
                source=RuleSource.PROJECT, behavior="ask", tool_name="*"
            )
        ],
    )
    decision = await engine.decide(
        tool=_SideEffectTool(), input={"command": "ls"}, context=ctx
    )
    assert decision.behavior == "deny"


@pytest.mark.asyncio
async def test_tool_specific_check_overrides(ctx):
    class StrictTool(_SideEffectTool):
        async def check_permissions(self, input, context):
            return PermissionResult(behavior="deny", message="too dangerous")

    decision = await PermissionEngine().decide(
        tool=StrictTool(), input={"command": "ls"}, context=ctx
    )
    assert decision.behavior == "deny"
    assert decision.reason == "tool"
