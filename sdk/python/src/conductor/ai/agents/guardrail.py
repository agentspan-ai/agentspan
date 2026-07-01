# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Guardrails — input and output validation for agent responses.

Guardrails compile to Conductor worker tasks positioned before (input)
or after (output) the LlmChatComplete task.  On failure with
``on_fail="retry"``, the guardrail's message is appended to the
conversation and the LLM is called again.

Specialised guardrails:

- :class:`RegexGuardrail` — validates content against one or more regex patterns.
- :class:`LLMGuardrail` — uses an LLM to judge content against a policy.
"""

from __future__ import annotations

import functools
import inspect
import re
from dataclasses import dataclass
from enum import Enum
from typing import Callable, List, Optional, Union

# ── Enums ─────────────────────────────────────────────────────────────────


class OnFail(str, Enum):
    """What to do when a guardrail check fails."""

    RETRY = "retry"
    RAISE = "raise"
    FIX = "fix"
    HUMAN = "human"


class Position(str, Enum):
    """Where a guardrail runs relative to the LLM call."""

    INPUT = "input"
    OUTPUT = "output"


# ── GuardrailResult ───────────────────────────────────────────────────────


@dataclass
class GuardrailResult:
    """The result of a guardrail check.

    Attributes:
        passed: ``True`` if the content passes the guardrail.
        message: Feedback message — sent back to the LLM on ``on_fail="retry"``.
        fixed_output: For ``on_fail="fix"`` — the corrected output to use
            instead of the original.  Ignored when *passed* is ``True``.
    """

    passed: bool
    message: str = ""
    fixed_output: Optional[str] = None


# ── GuardrailDef (attached by @guardrail decorator) ──────────────────────


@dataclass
class GuardrailDef:
    """Resolved guardrail definition (parallel to ToolDef)."""

    name: str
    description: str
    func: Optional[Callable[[str], GuardrailResult]]


# ── @guardrail decorator ─────────────────────────────────────────────────


def guardrail(func=None, *, name=None):
    """Register a function as a guardrail.

    The function must accept a single ``str`` and return
    :class:`GuardrailResult`.

    Can be used bare or with keyword arguments::

        @guardrail
        def no_pii(content: str) -> GuardrailResult: ...

        @guardrail(name="pii_checker")
        def no_pii(content: str) -> GuardrailResult: ...
    """

    def _wrap(fn):
        gd = GuardrailDef(
            name=name or fn.__name__,
            description=inspect.getdoc(fn) or "",
            func=fn,
        )

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)

        wrapper._guardrail_def = gd
        return wrapper

    if func is not None:
        return _wrap(func)
    return _wrap


_VALID_ON_FAIL = ("retry", "raise", "fix", "human")


class Guardrail:
    """A validation guardrail for agent input or output.

    Args:
        func: A callable ``(content: str) -> GuardrailResult`` that validates
            the content.  Also accepts ``@guardrail``-decorated functions
            (the underlying function and name are extracted automatically).
            If ``None`` and *name* is provided, the guardrail is treated as
            an **external** reference to a worker running elsewhere.
        position: Where the guardrail runs — ``"input"`` or ``"output"``.
            Accepts :class:`Position` enum values or plain strings.
            Default ``"output"``.
        on_fail: What to do when the guardrail fails.  Accepts
            :class:`OnFail` enum values or plain strings.  Default
            ``"raise"``.
        name: Optional name for the guardrail (defaults to the function name).
        max_retries: Maximum retry attempts for ``on_fail="retry"``.
            Default ``3``.
    """

    def __init__(
        self,
        func: Optional[Callable[[str], GuardrailResult]] = None,
        position: Union[str, Position] = Position.OUTPUT,
        on_fail: Union[str, OnFail] = OnFail.RAISE,
        name: Optional[str] = None,
        max_retries: int = 3,
    ) -> None:
        # Accept @guardrail-decorated functions
        if func is not None and hasattr(func, "_guardrail_def"):
            gd = func._guardrail_def
            func = gd.func
            if name is None:
                name = gd.name

        if position not in ("input", "output"):
            raise ValueError(f"Invalid position {position!r}. Must be 'input' or 'output'")
        if on_fail not in _VALID_ON_FAIL:
            raise ValueError(f"Invalid on_fail {on_fail!r}. Must be one of {_VALID_ON_FAIL}")
        if on_fail == "human" and position == "input":
            raise ValueError(
                "on_fail='human' is only valid for position='output' "
                "(input guardrails are client-side and cannot pause a workflow)"
            )
        if func is None and name is None:
            raise ValueError(
                "Either func or name must be provided. "
                "Pass a callable for a local guardrail, or name for an external one."
            )
        if max_retries < 1:
            raise ValueError(f"max_retries must be >= 1, got {max_retries}")

        self.func = func
        self.position = position
        self.on_fail = on_fail
        self.name = name or getattr(func, "__name__", "guardrail")
        self.max_retries = max_retries

    @property
    def external(self) -> bool:
        """``True`` if this guardrail references an external worker (no local func)."""
        return self.func is None

    def check(self, content: str) -> GuardrailResult:
        """Run the guardrail check against *content*."""
        if self.func is None:
            raise RuntimeError(
                f"Cannot call check() on external guardrail {self.name!r}. "
                "External guardrails run as Conductor worker tasks."
            )
        return self.func(content)

    def __repr__(self) -> str:
        extra = ", external=True" if self.external else ""
        return (
            f"Guardrail(name={self.name!r}, position={self.position!r}, "
            f"on_fail={self.on_fail!r}{extra})"
        )


# ── Specialised guardrail types ────────────────────────────────────────


class RegexGuardrail(Guardrail):
    """A guardrail that validates content against regex patterns.

    By default the guardrail **rejects** content that matches any of the
    given patterns (blocklist mode).  Set ``mode="allow"`` to **reject**
    content that does NOT match at least one pattern (allowlist mode).

    Args:
        patterns: A single regex string or a list of regex strings.
        mode: ``"block"`` (default) — fail if any pattern matches.
            ``"allow"`` — fail if NO pattern matches.
        position: ``"input"`` or ``"output"``.
        on_fail: ``"retry"`` or ``"raise"``.
        name: Optional guardrail name.
        message: Custom failure message.  Defaults to an auto-generated one.

    Example::

        # Block any content with email addresses
        no_emails = RegexGuardrail(
            patterns=[r"[\\w.+-]+@[\\w-]+\\.[\\w.-]+"],
            name="no_pii",
            message="Response must not contain email addresses.",
        )

        # Only allow JSON output
        json_only = RegexGuardrail(
            patterns=[r"^\\s*[\\{\\[]"],
            mode="allow",
            name="json_output",
            message="Response must be valid JSON.",
        )
    """

    def __init__(
        self,
        patterns: Union[str, List[str]],
        *,
        mode: str = "block",
        position: Union[str, Position] = Position.OUTPUT,
        on_fail: Union[str, OnFail] = OnFail.RAISE,
        name: Optional[str] = None,
        message: Optional[str] = None,
        max_retries: int = 3,
    ) -> None:
        if mode not in ("block", "allow"):
            raise ValueError(f"Invalid mode {mode!r}. Must be 'block' or 'allow'")

        if isinstance(patterns, str):
            patterns = [patterns]

        self._pattern_strings = list(patterns)
        self._patterns = [re.compile(p) for p in patterns]
        self._mode = mode
        self._custom_message = message

        def _check(content: str) -> GuardrailResult:
            matched = any(p.search(content) for p in self._patterns)

            if mode == "block" and matched:
                msg = message or "Content matched a blocked pattern."
                return GuardrailResult(passed=False, message=msg)
            elif mode == "allow" and not matched:
                msg = message or "Content did not match any allowed pattern."
                return GuardrailResult(passed=False, message=msg)
            return GuardrailResult(passed=True)

        super().__init__(
            func=_check,
            position=position,
            on_fail=on_fail,
            name=name or "regex_guardrail",
            max_retries=max_retries,
        )

    def __repr__(self) -> str:
        return (
            f"RegexGuardrail(name={self.name!r}, mode={self._mode!r}, "
            f"patterns={len(self._patterns)}, position={self.position!r})"
        )


class LLMGuardrail(Guardrail):
    """A guardrail that uses an LLM to evaluate content against a policy.

    The LLM receives a policy prompt along with the content to evaluate
    and must respond with a JSON ``{"passed": true/false, "reason": "..."}``.

    .. note:: This guardrail calls the LLM synchronously at evaluation time.
       The model/provider should be fast (e.g. a small model) to avoid
       slowing down the agent loop.

    Args:
        model: LLM model in ``"provider/model"`` format.
        policy: A description of what the guardrail should check for.
        position: ``"input"`` or ``"output"``.
        on_fail: ``"retry"`` or ``"raise"``.
        name: Optional guardrail name.

    Example::

        safety = LLMGuardrail(
            model="anthropic/claude-sonnet-4-6",
            policy="Reject any content that contains harmful, violent, or discriminatory language.",
            name="safety_check",
        )
    """

    def __init__(
        self,
        model: str,
        policy: str,
        *,
        position: Union[str, Position] = Position.OUTPUT,
        on_fail: Union[str, OnFail] = OnFail.RAISE,
        name: Optional[str] = None,
        max_retries: int = 3,
        max_tokens: Optional[int] = None,
    ) -> None:
        self._model = model
        self._policy = policy
        self._max_tokens = max_tokens

        def _check(content: str) -> GuardrailResult:
            return self._evaluate(content)

        super().__init__(
            func=_check,
            position=position,
            on_fail=on_fail,
            name=name or "llm_guardrail",
            max_retries=max_retries,
        )

    def _evaluate(self, content: str) -> GuardrailResult:
        """Call the LLM to evaluate content against the policy."""
        import json as _json

        prompt = (
            f"You are a content safety evaluator. Evaluate the following "
            f"content against this policy:\n\n"
            f"POLICY: {self._policy}\n\n"
            f"CONTENT: {content}\n\n"
            f'Respond with ONLY a JSON object: {{"passed": true/false, "reason": "..."}}'
        )

        try:
            from conductor.ai.agents._internal.model_parser import parse_model

            parsed = parse_model(self._model)

            # Try using litellm for the evaluation call
            try:
                import litellm

                response = litellm.completion(
                    model=f"{parsed.provider}/{parsed.model}",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=self._max_tokens,
                    temperature=0,
                )
                result_text = response.choices[0].message.content.strip()
            except ImportError:
                # Fail-safe: guardrail cannot evaluate without litellm
                return GuardrailResult(
                    passed=False,
                    message="LLMGuardrail requires the 'litellm' package. "
                    "Install it with: pip install litellm",
                )

            # Parse the JSON response
            try:
                data = _json.loads(result_text)
                return GuardrailResult(
                    passed=bool(data.get("passed", False)),
                    message=str(data.get("reason", "")),
                )
            except (_json.JSONDecodeError, AttributeError):
                # If LLM didn't return valid JSON, be conservative and fail
                return GuardrailResult(
                    passed=False,
                    message=f"LLM guardrail returned unparseable response: {result_text[:200]}",
                )

        except Exception as e:
            return GuardrailResult(
                passed=False,
                message=f"LLM guardrail evaluation error: {e}",
            )

    def __repr__(self) -> str:
        return (
            f"LLMGuardrail(name={self.name!r}, model={self._model!r}, position={self.position!r})"
        )
