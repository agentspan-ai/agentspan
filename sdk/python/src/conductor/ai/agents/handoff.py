# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Handoff conditions — rules that trigger automatic agent transitions.

Used with ``strategy="swarm"`` to define post-tool and post-work
transitions between agents::

    from conductor.ai.agents import Agent
    from conductor.ai.agents.handoff import OnToolResult, OnTextMention

    refund_agent = Agent(name="refund", model="openai/gpt-4o", ...)
    support_agent = Agent(
        name="support",
        model="openai/gpt-4o",
        agents=[refund_agent],
        strategy="swarm",
        handoffs=[
            OnToolResult(tool_name="check_order", target="refund"),
            OnTextMention(text="refund", target="refund"),
        ],
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


@dataclass
class HandoffCondition:
    """Base class for handoff conditions.

    A handoff condition determines when an agent should transfer
    control to another agent during swarm orchestration.

    Attributes:
        target: Name of the agent to hand off to.
    """

    target: str

    def should_handoff(self, context: Dict[str, Any]) -> bool:
        """Evaluate whether a handoff should occur.

        Args:
            context: Dict with keys:
                - ``result``: Latest LLM output text.
                - ``tool_name``: Name of the last tool called (if any).
                - ``tool_result``: Result of the last tool call (if any).
                - ``messages``: Full conversation history.

        Returns:
            ``True`` if the handoff should trigger.
        """
        return False


@dataclass
class OnToolResult(HandoffCondition):
    """Hand off after a specific tool is called.

    Triggers when the agent invokes the named tool, regardless of the
    tool's return value.

    Args:
        tool_name: The tool that triggers the handoff.
        target: The agent to hand off to.
        result_contains: Optional — only trigger if the tool result
            contains this substring.

    Example::

        OnToolResult(tool_name="escalate", target="supervisor")
    """

    tool_name: str = ""
    result_contains: Optional[str] = None

    def should_handoff(self, context: Dict[str, Any]) -> bool:
        called_tool = context.get("tool_name", "")
        if called_tool != self.tool_name:
            return False
        if self.result_contains is not None:
            tool_result = str(context.get("tool_result", ""))
            return self.result_contains in tool_result
        return True


@dataclass
class OnTextMention(HandoffCondition):
    """Hand off when the LLM output contains specific text.

    Args:
        text: The text to look for (case-insensitive).
        target: The agent to hand off to.

    Example::

        OnTextMention(text="transfer to billing", target="billing_agent")
    """

    text: str = ""

    def should_handoff(self, context: Dict[str, Any]) -> bool:
        result = str(context.get("result", "")).lower()
        return self.text.lower() in result


@dataclass
class OnCondition(HandoffCondition):
    """Hand off when a custom callable returns ``True``.

    Args:
        condition: A callable ``(context) -> bool``.
        target: The agent to hand off to.

    Example::

        OnCondition(
            condition=lambda ctx: ctx.get("iteration", 0) > 5,
            target="summarizer",
        )
    """

    condition: Callable[[Dict[str, Any]], bool] = lambda ctx: False

    def should_handoff(self, context: Dict[str, Any]) -> bool:
        try:
            return self.condition(context)
        except Exception:
            return False
