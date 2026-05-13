# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""HookRunner — invokes registered hooks with timeout and abort support.

v1 supports four hook events (per design §16):

  * ``session_start`` — runs once per session before the first turn
  * ``pre_tool_use`` — before each tool execution; may block or rewrite input
  * ``post_tool_use`` — after each tool execution; audit / follow-up work
  * ``stop`` — before the engine returns the terminal turn

Hooks are async callables registered with ``HookRunner.register(...)``.
Each event has a typed signature; the runner enforces timeouts and
catches exceptions so a misbehaving hook cannot crash the engine.

A future iteration will add ``permission_request``, ``user_prompt_submit``,
``subagent_start``, ``subagent_stop`` events. The runner is shaped so they
slot in without engine changes.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from ..tools.contract import ToolResult, ToolUseContext

logger = logging.getLogger("agentspan.harness.hooks")


# ── Hook signatures ──────────────────────────────────────────────────────

# session_start: (context) → None
SessionStartHookFn = Callable[[ToolUseContext], Awaitable[None]]

# pre_tool_use: (tool_name, input, context) → HookOutcome
PreToolHookFn = Callable[
    [str, Dict[str, Any], ToolUseContext], Awaitable["HookOutcome"]
]

# post_tool_use: (tool_name, input, result, context) → None
PostToolHookFn = Callable[
    [str, Dict[str, Any], ToolResult, ToolUseContext], Awaitable[None]
]

# stop: (context, final_message_text) → Optional[str]; non-None blocks/replaces
StopHookFn = Callable[[ToolUseContext, str], Awaitable[Optional[str]]]


@dataclass
class HookOutcome:
    """Result of a pre_tool_use hook.

    - ``blocked=True`` → orchestrator returns a tool-error result.
    - ``updated_input != None`` → orchestrator uses the new input.
    - both False/None → continue with original input.
    """

    blocked: bool = False
    hook_name: str = ""
    message: str = ""
    updated_input: Optional[Dict[str, Any]] = None


@dataclass
class Hook:
    """A registered hook entry.

    ``timeout_seconds`` defaults to 5s; tools-internal hooks should stay
    well under this. Exceeding the timeout is treated as failure-closed:
    pre_tool_use → block, post_tool_use → silently ignored, stop → no-op.
    """

    name: str
    event: str  # one of "session_start" | "pre_tool_use" | "post_tool_use" | "stop"
    fn: Callable[..., Awaitable[Any]]
    timeout_seconds: float = 5.0


class HookRunner:
    """Registers and runs hooks per event.

    Construction:

      runner = HookRunner()
      runner.register(Hook("git-status", "pre_tool_use", my_hook_fn))
    """

    def __init__(self) -> None:
        self._hooks: Dict[str, List[Hook]] = {
            "session_start": [],
            "pre_tool_use": [],
            "post_tool_use": [],
            "stop": [],
        }

    def register(self, hook: Hook) -> None:
        if hook.event not in self._hooks:
            raise ValueError(f"unknown hook event: {hook.event}")
        self._hooks[hook.event].append(hook)

    # ── Event invocations ────────────────────────────────────────────

    async def session_start(self, context: ToolUseContext) -> None:
        for h in self._hooks["session_start"]:
            await self._safe_call(h, h.fn(context), default=None)

    async def pre_tool_use(
        self,
        *,
        tool_name: str,
        input: Dict[str, Any],
        context: ToolUseContext,
    ) -> HookOutcome:
        effective_input = input
        for h in self._hooks["pre_tool_use"]:
            outcome = await self._safe_call(
                h,
                h.fn(tool_name, effective_input, context),
                default=HookOutcome(blocked=True, hook_name=h.name, message="hook timeout"),
            )
            if outcome is None:
                continue
            if outcome.blocked:
                outcome.hook_name = outcome.hook_name or h.name
                return outcome
            if outcome.updated_input is not None:
                effective_input = outcome.updated_input
        return HookOutcome(blocked=False, updated_input=effective_input if effective_input is not input else None)

    async def post_tool_use(
        self,
        *,
        tool_name: str,
        input: Dict[str, Any],
        result: ToolResult,
        context: ToolUseContext,
    ) -> None:
        for h in self._hooks["post_tool_use"]:
            await self._safe_call(h, h.fn(tool_name, input, result, context), default=None)

    async def stop(self, *, context: ToolUseContext, final_text: str) -> Optional[str]:
        """Run stop hooks. The first hook that returns a non-None string
        replaces the final message text (or blocks completion in v2).
        """
        for h in self._hooks["stop"]:
            replacement = await self._safe_call(h, h.fn(context, final_text), default=None)
            if isinstance(replacement, str):
                return replacement
        return None

    # ── Internals ────────────────────────────────────────────────────

    async def _safe_call(
        self,
        hook: Hook,
        coro: Awaitable[Any],
        *,
        default: Any,
    ) -> Any:
        try:
            return await asyncio.wait_for(coro, timeout=hook.timeout_seconds)
        except asyncio.TimeoutError:
            logger.warning("hook %s/%s timed out after %.1fs", hook.event, hook.name, hook.timeout_seconds)
            return default
        except Exception:  # noqa: BLE001
            logger.exception("hook %s/%s raised", hook.event, hook.name)
            return default
