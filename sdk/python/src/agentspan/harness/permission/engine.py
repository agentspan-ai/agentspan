# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Permission engine — layered allow/deny decision pipeline.

The pipeline is ordered. Each stage either decides (returning a
PermissionDecision) or passes through to the next. The first stage that
decides wins.

Stages:

  1. Blanket deny rules (any source) — deny.
  2. Blanket ask rules — ask (will be converted to deny in DONT_ASK / no UI).
  3. Tool-specific check via ``Tool.check_permissions``.
     - "deny" → deny
     - "ask"  → ask
     - "allow" → continue (still subject to bypass-resistant safety)
     - "passthrough" → continue
  4. Mode policy:
     - PLAN: deny non-read-only tools
     - DONT_ASK: convert any prior "ask" into deny
  5. Explicit allow rules — allow.
  6. permission_request hooks — return their decision verbatim.
  7. Default: ask (no UI in v1 → deny).

This matches the design's pipeline (§9) with v1 simplifications:

  - No automated safety classifier (post-v1)
  - No interactive UI prompt (post-v1)
  - No bypass-mode allow path (BYPASS reserved)

Allow rules NEVER outrank deny or ask rules from the same or higher
trust source. We enforce this by checking deny before allow at every
stage, regardless of source.
"""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from ..tools.contract import PermissionResult, Tool, ToolUseContext
from .rules import PermissionMode, PermissionRule

logger = logging.getLogger("agentspan.harness.permission")


@dataclass(frozen=True)
class PermissionDecision:
    behavior: str  # "allow" | "deny" | "ask"
    message: str = ""
    reason: str = ""  # short tag for audit (e.g. "rule:project", "tool", "mode")
    updated_input: Optional[Dict[str, Any]] = None


# Permission hooks (registered separately; engine calls them by reference).
# Signature: (tool_name, input, context) → PermissionDecision | None
PermissionHook = Callable[
    [str, Dict[str, Any], ToolUseContext],
    Awaitable[Optional[PermissionDecision]],
]


class PermissionEngine:
    """The permission decision pipeline.

    Construct with a list of rules + a mode + optional hooks. The engine
    is stateless (decisions don't accumulate) — session-scoped allow
    decisions belong in ``rules`` with ``source=SESSION``.
    """

    def __init__(
        self,
        *,
        rules: Optional[List[PermissionRule]] = None,
        mode: PermissionMode = PermissionMode.DEFAULT,
        hooks: Optional[List[PermissionHook]] = None,
    ) -> None:
        self._rules: List[PermissionRule] = list(rules or [])
        self._mode = mode
        self._hooks: List[PermissionHook] = list(hooks or [])

    @property
    def mode(self) -> PermissionMode:
        return self._mode

    def add_rule(self, rule: PermissionRule) -> None:
        self._rules.append(rule)

    # ── Decision pipeline ────────────────────────────────────────────

    async def decide(
        self,
        *,
        tool: Tool,
        input: Dict[str, Any],
        context: ToolUseContext,
    ) -> PermissionDecision:
        # Stage 1: blanket deny rules win unconditionally.
        deny_rule = self._first_match(tool, input, "deny")
        if deny_rule is not None:
            return PermissionDecision(
                behavior="deny",
                message=deny_rule.reason or f"denied by {deny_rule.source.value} rule",
                reason=f"rule:{deny_rule.source.value}",
            )

        # Stage 2: blanket ask rules.
        ask_rule = self._first_match(tool, input, "ask")
        ask_pending = ask_rule is not None
        ask_message = ask_rule.reason if ask_rule else ""

        # Stage 3: tool-specific check.
        try:
            tool_result = await tool.check_permissions(input, context)
        except Exception:  # noqa: BLE001
            logger.exception("Tool %s.check_permissions raised", tool.name)
            return PermissionDecision(
                behavior="deny",
                message=f"Permission check crashed for {tool.name}",
                reason="tool_crash",
            )

        if tool_result.behavior == "deny":
            return PermissionDecision(
                behavior="deny",
                message=tool_result.message or f"{tool.name} denied",
                reason="tool",
            )
        if tool_result.behavior == "ask":
            ask_pending = True
            ask_message = tool_result.message or ask_message
        elif tool_result.behavior == "allow":
            # tool says allow, but ask rules and mode-policy still gate.
            pass

        # Stage 4: mode policy.
        if self._mode == PermissionMode.PLAN and not tool.is_read_only(input):
            return PermissionDecision(
                behavior="deny",
                message=f"{tool.name} is not read-only; blocked in plan mode",
                reason="mode:plan",
            )

        # Stage 5: explicit allow rules.
        allow_rule = self._first_match(tool, input, "allow")
        if allow_rule is not None and not ask_pending:
            return PermissionDecision(
                behavior="allow",
                message=allow_rule.reason or f"allowed by {allow_rule.source.value} rule",
                reason=f"rule:{allow_rule.source.value}",
                updated_input=tool_result.updated_input,
            )

        # Stage 6: permission_request hooks. They may decide allow / ask / deny.
        for hook in self._hooks:
            try:
                hook_decision = await hook(tool.name, input, context)
            except Exception:  # noqa: BLE001
                logger.exception("permission_request hook crashed")
                continue
            if hook_decision is not None:
                if hook_decision.behavior == "deny":
                    return hook_decision
                if hook_decision.behavior == "allow" and not ask_pending:
                    return hook_decision
                if hook_decision.behavior == "ask":
                    ask_pending = True
                    ask_message = hook_decision.message or ask_message

        # Stage 7: default.
        if tool.is_read_only(input) and not ask_pending and allow_rule is None:
            # Read-only tools allowed by default. The model can't break things.
            return PermissionDecision(
                behavior="allow",
                message="read-only tool allowed by default policy",
                reason="default:read_only",
                updated_input=tool_result.updated_input,
            )

        # Anything that reached here is an "ask". v1 has no UI: convert
        # to deny when in DONT_ASK mode OR when no hooks decided.
        if self._mode == PermissionMode.DONT_ASK or ask_pending:
            return PermissionDecision(
                behavior="deny" if self._mode == PermissionMode.DONT_ASK else "ask",
                message=ask_message
                or f"{tool.name} requires explicit approval (no allow rule matched)",
                reason="default:no_approval",
            )

        # Default: deny side-effecting tools without approval.
        return PermissionDecision(
            behavior="deny",
            message=(
                f"{tool.name} would have side effects but no allow rule matched. "
                "Add a permission rule (allow_rules=[...]) to authorize."
            ),
            reason="default:deny",
        )

    # ── Rule matching ────────────────────────────────────────────────

    def _first_match(
        self, tool: Tool, input: Dict[str, Any], behavior: str
    ) -> Optional[PermissionRule]:
        """Return the first rule of ``behavior`` that matches this call.

        Matching:

        * ``tool_name == "*"`` matches any tool.
        * ``tool_name == tool.name`` matches that tool.
        * ``pattern is None`` matches any input.
        * ``pattern`` non-None: applied via the tool's permission matcher
          if available, else best-effort fnmatch against
          ``input.get("command")``/``input.get("path")``/``input.get("url")``.

        Rules are scanned in registration order. Higher-trust sources are
        registered first by convention, but the engine doesn't enforce
        that — config loaders should put policy rules first.
        """
        for rule in self._rules:
            if rule.behavior != behavior:
                continue
            if rule.tool_name != "*" and rule.tool_name != tool.name:
                continue
            if rule.pattern is None or _pattern_matches(rule.pattern, input):
                return rule
        return None


def _pattern_matches(pattern: str, input: Dict[str, Any]) -> bool:
    """Best-effort default pattern match.

    Tools that need rich pattern semantics should expose a permission
    matcher and the engine will use that instead. v1 implements a
    fallback for the most common cases:

      * shell-like tools: match against ``input["command"]``
      * file-like tools: match against ``input["path"]``
      * web fetch tools: match against ``input["url"]``

    All match via ``fnmatch.fnmatch``.
    """
    for key in ("command", "path", "url", "name"):
        value = input.get(key)
        if isinstance(value, str) and fnmatch.fnmatch(value, pattern):
            return True
    return False


__all__ = ["PermissionDecision", "PermissionEngine", "PermissionHook"]
