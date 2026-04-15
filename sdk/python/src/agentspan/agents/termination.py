# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Termination conditions — composable rules that decide when an agent should stop.

Conditions can be combined with ``&`` (AND — all must trigger) and ``|``
(OR — any one triggers)::

    from agentspan.agents import (
        TextMentionTermination,
        MaxMessageTermination,
        TokenUsageTermination,
    )

    # Stop when the LLM says "DONE" OR after 50 messages
    stop = TextMentionTermination("DONE") | MaxMessageTermination(50)

    # Stop when BOTH conditions are met
    stop = TextMentionTermination("FINAL") & MaxMessageTermination(10)

Each condition is compiled into a Conductor worker task that evaluates inside
the DoWhile loop, contributing to the loop's termination expression.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class TerminationResult:
    """The result of evaluating a termination condition.

    Attributes:
        should_terminate: ``True`` if the agent should stop.
        reason: Human-readable explanation of why termination was triggered.
    """

    should_terminate: bool
    reason: str = ""


class TerminationCondition(ABC):
    """Base class for all termination conditions.

    Subclasses implement :meth:`should_terminate` which receives a context
    dict and returns a :class:`TerminationResult`.

    Conditions are composable via ``&`` (AND) and ``|`` (OR) operators.
    """

    @abstractmethod
    def should_terminate(self, context: Dict[str, Any]) -> TerminationResult:
        """Evaluate whether the agent should stop.

        Args:
            context: A dict with keys:
                - ``result``: The latest LLM output text.
                - ``messages``: The full conversation history (list of dicts).
                - ``iteration``: The current loop iteration number.
                - ``token_usage``: Token usage dict (if available).

        Returns:
            A :class:`TerminationResult`.
        """
        ...

    def __and__(self, other: "TerminationCondition") -> "TerminationCondition":
        """Combine two conditions with AND — both must trigger to terminate."""
        return _AndTermination(self, other)

    def __or__(self, other: "TerminationCondition") -> "TerminationCondition":
        """Combine two conditions with OR — either one triggers termination."""
        return _OrTermination(self, other)

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"


# ── Concrete conditions ─────────────────────────────────────────────────


class TextMentionTermination(TerminationCondition):
    """Terminate when the LLM output contains a specific text string.

    Args:
        text: The text to look for (case-insensitive by default).
        case_sensitive: Whether the match should be case-sensitive.

    Example::

        stop = TextMentionTermination("TERMINATE")
        agent = Agent(..., termination=stop)
    """

    def __init__(self, text: str, *, case_sensitive: bool = False) -> None:
        self.text = text
        self.case_sensitive = case_sensitive

    def should_terminate(self, context: Dict[str, Any]) -> TerminationResult:
        result = str(context.get("result", ""))
        text = self.text
        if not self.case_sensitive:
            result = result.lower()
            text = text.lower()
        if text in result:
            return TerminationResult(
                should_terminate=True,
                reason=f"Text '{self.text}' found in output",
            )
        return TerminationResult(should_terminate=False)

    def __repr__(self) -> str:
        return f"TextMentionTermination({self.text!r})"


class StopMessageTermination(TerminationCondition):
    """Terminate when the LLM output exactly matches a stop signal.

    Similar to :class:`TextMentionTermination` but uses exact match
    (after stripping whitespace) rather than substring search.

    Args:
        stop_message: The exact message to match (default ``"TERMINATE"``).

    Example::

        stop = StopMessageTermination("DONE")
    """

    def __init__(self, stop_message: str = "TERMINATE") -> None:
        self.stop_message = stop_message

    def should_terminate(self, context: Dict[str, Any]) -> TerminationResult:
        result = str(context.get("result", "")).strip()
        if result == self.stop_message:
            return TerminationResult(
                should_terminate=True,
                reason=f"Stop message '{self.stop_message}' received",
            )
        return TerminationResult(should_terminate=False)

    def __repr__(self) -> str:
        return f"StopMessageTermination({self.stop_message!r})"


class MaxMessageTermination(TerminationCondition):
    """Terminate after a maximum number of messages in the conversation.

    Counts all messages in ``context["messages"]``, including system,
    user, assistant, and tool messages.

    Args:
        max_messages: Maximum number of messages before termination.

    Example::

        stop = MaxMessageTermination(20)
    """

    def __init__(self, max_messages: int) -> None:
        if max_messages < 1:
            raise ValueError("max_messages must be >= 1")
        self.max_messages = max_messages

    def should_terminate(self, context: Dict[str, Any]) -> TerminationResult:
        messages = context.get("messages", [])
        count = len(messages) if isinstance(messages, list) else 0
        # Fall back to iteration count when messages list is not populated
        # (e.g., in Conductor workflow context where iteration tracks LLM turns).
        if count == 0:
            count = context.get("iteration", 0)
        if count >= self.max_messages:
            return TerminationResult(
                should_terminate=True,
                reason=f"Message count ({count}) >= limit ({self.max_messages})",
            )
        return TerminationResult(should_terminate=False)

    def __repr__(self) -> str:
        return f"MaxMessageTermination({self.max_messages})"


class TokenUsageTermination(TerminationCondition):
    """Terminate when cumulative token usage exceeds a budget.

    Checks ``context["token_usage"]`` which should be a dict with
    ``prompt_tokens``, ``completion_tokens``, and/or ``total_tokens``.

    Args:
        max_total_tokens: Maximum total tokens (prompt + completion).
        max_prompt_tokens: Maximum prompt tokens (optional).
        max_completion_tokens: Maximum completion tokens (optional).

    Example::

        stop = TokenUsageTermination(max_total_tokens=10000)
    """

    def __init__(
        self,
        max_total_tokens: Optional[int] = None,
        max_prompt_tokens: Optional[int] = None,
        max_completion_tokens: Optional[int] = None,
    ) -> None:
        if max_total_tokens is None and max_prompt_tokens is None and max_completion_tokens is None:
            raise ValueError("At least one token limit must be specified")
        self.max_total_tokens = max_total_tokens
        self.max_prompt_tokens = max_prompt_tokens
        self.max_completion_tokens = max_completion_tokens

    def should_terminate(self, context: Dict[str, Any]) -> TerminationResult:
        usage = context.get("token_usage", {})
        if not isinstance(usage, dict):
            return TerminationResult(should_terminate=False)

        total = usage.get("total_tokens", 0)
        prompt = usage.get("prompt_tokens", 0)
        completion = usage.get("completion_tokens", 0)

        if self.max_total_tokens is not None and total >= self.max_total_tokens:
            return TerminationResult(
                should_terminate=True,
                reason=f"Total tokens ({total}) >= limit ({self.max_total_tokens})",
            )
        if self.max_prompt_tokens is not None and prompt >= self.max_prompt_tokens:
            return TerminationResult(
                should_terminate=True,
                reason=f"Prompt tokens ({prompt}) >= limit ({self.max_prompt_tokens})",
            )
        if self.max_completion_tokens is not None and completion >= self.max_completion_tokens:
            return TerminationResult(
                should_terminate=True,
                reason=f"Completion tokens ({completion}) >= limit ({self.max_completion_tokens})",
            )
        return TerminationResult(should_terminate=False)

    def __repr__(self) -> str:
        parts = []
        if self.max_total_tokens is not None:
            parts.append(f"max_total={self.max_total_tokens}")
        if self.max_prompt_tokens is not None:
            parts.append(f"max_prompt={self.max_prompt_tokens}")
        if self.max_completion_tokens is not None:
            parts.append(f"max_completion={self.max_completion_tokens}")
        return f"TokenUsageTermination({', '.join(parts)})"


# ── Composite conditions ────────────────────────────────────────────────


class _AndTermination(TerminationCondition):
    """AND combinator: terminates only when ALL child conditions trigger.

    Created via ``condition_a & condition_b``.
    """

    def __init__(self, *conditions: TerminationCondition) -> None:
        self.conditions: List[TerminationCondition] = []
        for c in conditions:
            if isinstance(c, _AndTermination):
                self.conditions.extend(c.conditions)
            else:
                self.conditions.append(c)

    def should_terminate(self, context: Dict[str, Any]) -> TerminationResult:
        reasons = []
        for cond in self.conditions:
            result = cond.should_terminate(context)
            if not result.should_terminate:
                return TerminationResult(should_terminate=False)
            if result.reason:
                reasons.append(result.reason)
        return TerminationResult(
            should_terminate=True,
            reason=" AND ".join(reasons),
        )

    def __repr__(self) -> str:
        inner = " & ".join(repr(c) for c in self.conditions)
        return f"({inner})"


class _OrTermination(TerminationCondition):
    """OR combinator: terminates when ANY child condition triggers.

    Created via ``condition_a | condition_b``.
    """

    def __init__(self, *conditions: TerminationCondition) -> None:
        self.conditions: List[TerminationCondition] = []
        for c in conditions:
            if isinstance(c, _OrTermination):
                self.conditions.extend(c.conditions)
            else:
                self.conditions.append(c)

    def should_terminate(self, context: Dict[str, Any]) -> TerminationResult:
        for cond in self.conditions:
            result = cond.should_terminate(context)
            if result.should_terminate:
                return result
        return TerminationResult(should_terminate=False)

    def __repr__(self) -> str:
        inner = " | ".join(repr(c) for c in self.conditions)
        return f"({inner})"
