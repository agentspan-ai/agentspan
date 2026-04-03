# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Eval runner — LLM-backed correctness testing for agent behavior.

Runs real prompts through agents and evaluates whether the agent's behavior
matches expectations.  Unlike mock tests, this actually exercises the LLM
and orchestration logic to verify correctness end-to-end.

Usage::

    from agentspan.agents.testing import CorrectnessEval, EvalCase

    eval = CorrectnessEval(runtime)

    results = eval.run([
        EvalCase(
            name="billing_routes_correctly",
            agent=support_agent,
            prompt="I need a refund for order #123",
            expect_tools=["lookup_order"],
            expect_handoff_to="billing",
            expect_output_contains=["refund"],
        ),
        EvalCase(
            name="tech_routes_correctly",
            agent=support_agent,
            prompt="My app crashes on startup",
            expect_handoff_to="technical",
            expect_tools_not_used=["lookup_order", "process_refund"],
        ),
    ])

    results.print_summary()
    assert results.all_passed
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from agentspan.agents.result import AgentResult, EventType
from agentspan.agents.testing.assertions import (
    assert_handoff_to,
    assert_no_errors,
    assert_output_contains,
    assert_output_matches,
    assert_status,
    assert_tool_called_with,
    assert_tool_not_used,
    assert_tool_used,
)
from agentspan.agents.testing.strategy_validators import validate_strategy

# ── Eval case definition ───────────────────────────────────────────────


@dataclass
class EvalCase:
    """A single correctness test case for an agent.

    Define what you send to the agent and what correct behavior looks like.

    Args:
        name: Descriptive name for this test case.
        agent: The Agent to test.
        prompt: The user message to send.
        expect_tools: Tools that MUST be used.
        expect_tools_not_used: Tools that must NOT be used.
        expect_tool_args: Tool that must be called with specific args.
            Dict of ``{tool_name: {arg: value}}``.
        expect_handoff_to: Agent name that should receive the handoff.
        expect_no_handoff_to: Agent names that should NOT receive handoffs.
        expect_output_contains: Substrings the output must contain.
        expect_output_matches: Regex pattern the output must match.
        expect_status: Expected status (default ``"COMPLETED"``).
        expect_no_errors: If True (default), assert no error events.
        validate_orchestration: If True (default), run strategy validator.
        custom_assertions: Extra assertion functions ``(result) -> None``.
        tags: Optional tags for filtering eval cases.
    """

    name: str = ""
    agent: Any = None
    prompt: str = ""

    # Tool expectations
    expect_tools: Optional[List[str]] = None
    expect_tools_not_used: Optional[List[str]] = None
    expect_tool_args: Optional[Dict[str, Dict[str, Any]]] = None

    # Routing expectations
    expect_handoff_to: Optional[str] = None
    expect_no_handoff_to: Optional[List[str]] = None

    # Output expectations
    expect_output_contains: Optional[List[str]] = None
    expect_output_matches: Optional[str] = None
    expect_status: str = "COMPLETED"
    expect_no_errors: bool = True

    # Strategy validation
    validate_orchestration: bool = True

    # Custom assertions
    custom_assertions: List[Callable[[AgentResult], None]] = field(default_factory=list)

    # Metadata
    tags: List[str] = field(default_factory=list)


# ── Eval results ───────────────────────────────────────────────────────


@dataclass
class EvalCheckResult:
    """Result of a single check within an eval case."""

    check: str
    passed: bool
    message: str = ""


@dataclass
class EvalCaseResult:
    """Result of running a single eval case."""

    name: str
    passed: bool
    checks: List[EvalCheckResult] = field(default_factory=list)
    result: Optional[AgentResult] = None
    error: Optional[str] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class EvalSuiteResult:
    """Aggregated results from running a suite of eval cases."""

    cases: List[EvalCaseResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        """True if every case passed."""
        return all(c.passed for c in self.cases)

    @property
    def pass_count(self) -> int:
        return sum(1 for c in self.cases if c.passed)

    @property
    def fail_count(self) -> int:
        return sum(1 for c in self.cases if not c.passed)

    @property
    def total(self) -> int:
        return len(self.cases)

    def print_summary(self) -> None:
        """Print a formatted summary of all eval results."""
        width = 60
        print(f"\n{'=' * width}")
        print(" Agent Correctness Eval Results")
        print(f"{'=' * width}")

        for case in self.cases:
            icon = "PASS" if case.passed else "FAIL"
            print(f"\n  [{icon}] {case.name}")
            if not case.passed:
                for check in case.checks:
                    if not check.passed:
                        print(f"         x {check.check}: {check.message}")
                if case.error:
                    print(f"         x Error: {case.error}")

        print(f"\n{'─' * width}")
        print(f"  {self.pass_count}/{self.total} passed, {self.fail_count} failed")
        print(f"{'=' * width}\n")

    def failed_cases(self) -> List[EvalCaseResult]:
        """Return only the failed cases."""
        return [c for c in self.cases if not c.passed]


# ── Eval runner ────────────────────────────────────────────────────────


class CorrectnessEval:
    """Runs eval cases against a live Agentspan runtime.

    Args:
        runtime: An :class:`AgentRuntime` instance (or any object with a
            ``run(agent, prompt)`` method).
    """

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    def run(
        self,
        cases: Sequence[EvalCase],
        *,
        tags: Optional[List[str]] = None,
    ) -> EvalSuiteResult:
        """Run all eval cases and return aggregated results.

        Args:
            cases: List of :class:`EvalCase` definitions.
            tags: If provided, only run cases with at least one matching tag.

        Returns:
            An :class:`EvalSuiteResult` with per-case and aggregated results.
        """
        suite = EvalSuiteResult()

        for case in cases:
            if tags and not set(tags) & set(case.tags):
                continue
            case_result = self._run_case(case)
            suite.cases.append(case_result)

        return suite

    def _run_case(self, case: EvalCase) -> EvalCaseResult:
        """Run a single eval case."""
        checks: List[EvalCheckResult] = []
        agent_result: Optional[AgentResult] = None

        # Execute the agent
        try:
            agent_result = self._runtime.run(case.agent, case.prompt)
        except Exception as exc:
            return EvalCaseResult(
                name=case.name,
                passed=False,
                error=f"Agent execution failed: {exc}",
                tags=case.tags,
            )

        # Run all checks
        checks.append(
            self._check("status", lambda: assert_status(agent_result, case.expect_status))
        )

        if case.expect_no_errors:
            checks.append(self._check("no_errors", lambda: assert_no_errors(agent_result)))

        if case.expect_tools:
            for tool_name in case.expect_tools:
                checks.append(
                    self._check(
                        f"tool_used:{tool_name}",
                        lambda tn=tool_name: assert_tool_used(agent_result, tn),
                    )
                )

        if case.expect_tools_not_used:
            for tool_name in case.expect_tools_not_used:
                checks.append(
                    self._check(
                        f"tool_not_used:{tool_name}",
                        lambda tn=tool_name: assert_tool_not_used(agent_result, tn),
                    )
                )

        if case.expect_tool_args:
            for tool_name, args in case.expect_tool_args.items():
                checks.append(
                    self._check(
                        f"tool_args:{tool_name}",
                        lambda tn=tool_name, a=args: assert_tool_called_with(
                            agent_result, tn, args=a
                        ),
                    )
                )

        if case.expect_handoff_to:
            checks.append(
                self._check(
                    f"handoff_to:{case.expect_handoff_to}",
                    lambda: assert_handoff_to(agent_result, case.expect_handoff_to),
                )
            )

        if case.expect_no_handoff_to:
            for agent_name in case.expect_no_handoff_to:
                checks.append(
                    self._check(
                        f"no_handoff_to:{agent_name}",
                        lambda an=agent_name: _assert_no_handoff(agent_result, an),
                    )
                )

        if case.expect_output_contains:
            for text in case.expect_output_contains:
                checks.append(
                    self._check(
                        f"output_contains:'{text}'",
                        lambda t=text: assert_output_contains(
                            agent_result, t, case_sensitive=False
                        ),
                    )
                )

        if case.expect_output_matches:
            checks.append(
                self._check(
                    f"output_matches:'{case.expect_output_matches}'",
                    lambda: assert_output_matches(agent_result, case.expect_output_matches),
                )
            )

        if case.validate_orchestration:
            checks.append(
                self._check(
                    "strategy_validation",
                    lambda: validate_strategy(case.agent, agent_result),
                )
            )

        for i, custom_fn in enumerate(case.custom_assertions):
            checks.append(self._check(f"custom_{i}", lambda fn=custom_fn: fn(agent_result)))

        passed = all(c.passed for c in checks)
        return EvalCaseResult(
            name=case.name,
            passed=passed,
            checks=checks,
            result=agent_result,
            tags=case.tags,
        )

    @staticmethod
    def _check(name: str, fn: Callable[[], None]) -> EvalCheckResult:
        """Run a single assertion and capture the result."""
        try:
            fn()
            return EvalCheckResult(check=name, passed=True)
        except (AssertionError, Exception) as exc:
            return EvalCheckResult(check=name, passed=False, message=str(exc))


def _assert_no_handoff(result: AgentResult, agent_name: str) -> None:
    """Assert that NO handoff to the given agent occurred."""
    handoffs = [
        ev.target
        for ev in result.events
        if ev.type == EventType.HANDOFF and ev.target == agent_name
    ]
    if handoffs:
        raise AssertionError(
            f"Expected NO handoff to '{agent_name}', but {len(handoffs)} occurred."
        )


# ── Eval case generation from observed results ───────────────────────


def _slugify(text: str, max_len: int = 60) -> str:
    """Turn a prompt into a snake_case name."""
    import re

    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug[:max_len].rstrip("_")


# Keys injected by the runtime that should not be captured in eval expectations.
_INTERNAL_ARG_KEYS = frozenset({"__agentspan_ctx__", "_agent_state", "method"})


def eval_case_from_result(
    result: AgentResult,
    *,
    agent: Any,
    prompt: str,
    name: str = "",
    include_tool_args: bool = True,
    tags: Optional[List[str]] = None,
) -> EvalCase:
    """Generate an :class:`EvalCase` from an observed :class:`AgentResult`.

    Inspects the result's tool calls, handoff events, status, and output
    to build expectations automatically — no manual case authoring needed.

    Typical workflow::

        # 1. Run agent against a live server
        result = runtime.run(agent, "What's the weather in Tokyo?")

        # 2. Auto-generate an eval case from the observed behavior
        case = eval_case_from_result(result, agent=agent, prompt="What's the weather in Tokyo?")

        # 3. Use it in future regression runs
        evaluator = CorrectnessEval(runtime)
        suite = evaluator.run([case])

    Args:
        result: The :class:`AgentResult` to build expectations from.
        agent: The Agent that produced this result (stored in the case).
        prompt: The prompt that was sent to the agent.
        name: Optional descriptive name. Auto-generated from prompt if empty.
        include_tool_args: If True (default), capture tool call arguments
            in ``expect_tool_args``.
        tags: Optional tags for filtering.

    Returns:
        A fully-populated :class:`EvalCase`.
    """
    if not name:
        name = _slugify(prompt)

    # Extract tools used
    tool_names = []
    tool_args: Dict[str, Dict[str, Any]] = {}
    for tc in result.tool_calls:
        tool_name = tc.get("name", "")
        if tool_name and tool_name not in tool_names:
            tool_names.append(tool_name)
        if include_tool_args and tool_name and tc.get("args"):
            # Strip internal runtime keys that change per-execution
            cleaned = {
                k: v for k, v in tc["args"].items() if k not in _INTERNAL_ARG_KEYS
            }
            if cleaned:
                tool_args[tool_name] = cleaned

    # Extract handoff target from events
    handoff_target = None
    for ev in result.events:
        if ev.type == EventType.HANDOFF and ev.target:
            handoff_target = ev.target
            break  # Use first handoff

    # Check for errors
    has_errors = any(ev.type == EventType.ERROR for ev in result.events)

    return EvalCase(
        name=name,
        agent=agent,
        prompt=prompt,
        expect_tools=tool_names if tool_names else None,
        expect_tool_args=tool_args if tool_args else None,
        expect_handoff_to=handoff_target,
        expect_status=str(result.status.value) if hasattr(result.status, "value") else str(result.status),
        expect_no_errors=not has_errors,
        validate_orchestration=True,
        tags=list(tags) if tags else ["captured"],
    )


def capture_eval_case(
    runtime: Any,
    agent: Any,
    prompt: str,
    *,
    name: str = "",
    include_tool_args: bool = True,
    tags: Optional[List[str]] = None,
) -> tuple:
    """Run an agent and auto-generate an :class:`EvalCase` from the result.

    Convenience wrapper that combines ``runtime.run()`` with
    :func:`eval_case_from_result`.  Returns both the generated case and
    the original result for inspection.

    Example::

        with AgentRuntime() as runtime:
            case, result = capture_eval_case(runtime, agent, "Check stock for AAPL")
            result.print_result()  # inspect what happened

            # Replay later as a regression test
            evaluator = CorrectnessEval(runtime)
            suite = evaluator.run([case])
            suite.print_summary()

    Args:
        runtime: An :class:`AgentRuntime` instance (or any object with a
            ``run(agent, prompt)`` method).
        agent: The Agent to run.
        prompt: The user message to send.
        name: Optional descriptive name. Auto-generated from prompt if empty.
        include_tool_args: If True (default), capture tool call arguments.
        tags: Optional tags for filtering.

    Returns:
        A tuple of ``(EvalCase, AgentResult)``.
    """
    result = runtime.run(agent, prompt)
    case = eval_case_from_result(
        result,
        agent=agent,
        prompt=prompt,
        name=name,
        include_tool_args=include_tool_args,
        tags=tags,
    )
    return case, result
