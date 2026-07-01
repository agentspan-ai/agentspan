# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Eval runner — LLM-backed correctness testing for agent behavior.

Runs real prompts through agents and evaluates whether the agent's behavior
matches expectations.  Unlike mock tests, this actually exercises the LLM
and orchestration logic to verify correctness end-to-end.

Usage::

    from conductor.ai.agents.testing import CorrectnessEval, EvalCase

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

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

from conductor.ai.agents.result import AgentResult, EventType
from conductor.ai.agents.testing.assertions import (
    assert_handoff_to,
    assert_no_errors,
    assert_output_contains,
    assert_output_matches,
    assert_status,
    assert_tool_called_with,
    assert_tool_not_used,
    assert_tool_used,
)
from conductor.ai.agents.testing.strategy_validators import validate_strategy

logger = logging.getLogger("agentspan.agents.testing.eval_runner")

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
    semantic_criteria: Optional[str] = None


# ── Eval results ───────────────────────────────────────────────────────


@dataclass
class EvalCheckResult:
    """Result of a single check within an eval case."""

    check: str
    passed: bool
    message: str = ""
    # Populated by semantic (LLM-judge) assertions; None for deterministic checks.
    score: Optional[float] = None
    reasoning: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"check": self.check, "passed": self.passed, "message": self.message}
        if self.score is not None:
            d["score"] = self.score
        if self.reasoning is not None:
            d["reasoning"] = self.reasoning
        return d


@dataclass
class EvalCaseResult:
    """Result of running a single eval case."""

    name: str
    passed: bool
    checks: List[EvalCheckResult] = field(default_factory=list)
    result: Optional[AgentResult] = None
    error: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    agent_name: str = ""
    model: str = ""
    prompt: str = ""
    output: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name": self.name,
            "passed": self.passed,
            "error": self.error,
            "tags": self.tags,
            "agentName": self.agent_name,
            "model": self.model,
            "prompt": self.prompt,
            "checks": [c.to_dict() for c in self.checks],
        }
        if self.output is not None:
            d["output"] = self.output
        return d


@dataclass
class EvalSuiteResult:
    """Aggregated results from running a suite of eval cases."""

    cases: List[EvalCaseResult] = field(default_factory=list)
    eval_run_id: str = ""
    agent_name: str = ""
    timestamp: str = ""
    suite_tags: List[str] = field(default_factory=list)
    name: Optional[str] = None
    strategy: Optional[str] = None
    ran_by: Optional[str] = None
    dataset: Optional[str] = None

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

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "id": self.eval_run_id,
            "agentName": self.agent_name,
            "timestamp": self.timestamp,
            "totalCases": self.total,
            "passedCases": self.pass_count,
            "tags": self.suite_tags,
            "cases": [c.to_dict() for c in self.cases],
        }
        if self.name is not None:
            d["name"] = self.name
        if self.strategy is not None:
            d["strategy"] = self.strategy
        if self.ran_by is not None:
            d["ranBy"] = self.ran_by
        if self.dataset is not None:
            d["dataset"] = self.dataset
        return d


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
        suite_tags: Optional[List[str]] = None,
        name: Optional[str] = None,
        strategy: Optional[str] = None,
        ran_by: Optional[str] = None,
        dataset: Optional[str] = None,
    ) -> EvalSuiteResult:
        """Run all eval cases and return aggregated results.

        Args:
            cases: List of :class:`EvalCase` definitions.
            tags: If provided, only run cases with at least one matching tag.
            suite_tags: Optional tags to attach to the eval suite result.
            name: Optional human-readable name for this run.
            strategy: Optional orchestration strategy label.
            ran_by: Optional script/runner identifier.
            dataset: Optional name of the stored dataset these cases came from,
                so the run links back to that dataset in the UI.

        Returns:
            An :class:`EvalSuiteResult` with per-case and aggregated results.
        """
        eval_run_id = str(uuid.uuid4())
        eval_session_id = f"eval:{eval_run_id}"
        timestamp = datetime.now(timezone.utc).isoformat()

        # Determine the primary agent name from the first case
        agent_name = ""
        for case in cases:
            try:
                agent_name = case.agent.name
            except AttributeError:
                pass
            if agent_name:
                break

        suite = EvalSuiteResult(
            eval_run_id=eval_run_id,
            agent_name=agent_name,
            timestamp=timestamp,
            suite_tags=suite_tags or [],
            name=name,
            strategy=strategy,
            ran_by=ran_by,
            dataset=dataset,
        )

        for case in cases:
            if tags and not set(tags) & set(case.tags):
                continue
            case_result = self._run_case(case, eval_session_id=eval_session_id)
            suite.cases.append(case_result)

        self._post_eval_result(suite)
        return suite

    def _post_eval_result(self, suite: EvalSuiteResult) -> None:
        """Send eval suite result to server (best-effort, never raises)."""
        try:
            post_fn = getattr(self._runtime, "_post_eval_run", None)
            if post_fn is not None:
                post_fn(suite.to_dict())
        except Exception as exc:
            logger.warning("Failed to post eval result to server: %s", exc)

    def _run_case(self, case: EvalCase, *, eval_session_id: str = "") -> EvalCaseResult:
        """Run a single eval case."""
        checks: List[EvalCheckResult] = []
        agent_result: Optional[AgentResult] = None

        agent_name = ""
        try:
            agent_name = case.agent.name
        except AttributeError:
            pass

        # Tag with eval session_id so server can filter these from production views.
        # Pass session_id only when the runtime supports it (real AgentRuntime does;
        # test stubs may not) to avoid breaking existing usage.
        try:
            if eval_session_id:
                try:
                    agent_result = self._runtime.run(
                        case.agent, case.prompt, session_id=eval_session_id
                    )
                except TypeError:
                    agent_result = self._runtime.run(case.agent, case.prompt)
            else:
                agent_result = self._runtime.run(case.agent, case.prompt)
        except Exception as exc:
            return EvalCaseResult(
                name=case.name,
                passed=False,
                error=f"Agent execution failed: {exc}",
                tags=case.tags,
                agent_name=agent_name,
                prompt=case.prompt,
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
            for no_handoff_agent in case.expect_no_handoff_to:
                checks.append(
                    self._check(
                        f"no_handoff_to:{no_handoff_agent}",
                        lambda an=no_handoff_agent: _assert_no_handoff(agent_result, an),
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

        # Semantic (LLM-judge) check — only when a criterion is provided.
        if case.semantic_criteria:
            semantic_check = self._semantic_check(case.semantic_criteria, agent_result)
            if semantic_check is not None:
                checks.append(semantic_check)

        passed = all(c.passed for c in checks)
        output = getattr(agent_result, "output", None)
        if output is None:
            output = getattr(agent_result, "text", None)
        return EvalCaseResult(
            name=case.name,
            passed=passed,
            checks=checks,
            result=agent_result,
            tags=case.tags,
            agent_name=agent_name,
            prompt=case.prompt,
            output=str(output) if output is not None else None,
        )

    @staticmethod
    def _check(name: str, fn: Callable[[], None]) -> EvalCheckResult:
        """Run a single assertion and capture the result."""
        try:
            fn()
            return EvalCheckResult(check=name, passed=True)
        except (AssertionError, Exception) as exc:
            return EvalCheckResult(check=name, passed=False, message=str(exc))

    @staticmethod
    def _semantic_check(
        criterion: str, result: AgentResult, *, threshold: float = 0.7
    ) -> Optional[EvalCheckResult]:
        """Grade the output against a semantic criterion via an LLM judge.

        Returns an :class:`EvalCheckResult` carrying the judge's ``score`` and
        ``reasoning``. Returns ``None`` (skips the check) when the optional
        judge dependency ``litellm`` isn't installed — so a criterion never
        fails a case just because the judge is unavailable.
        """
        try:
            from conductor.ai.agents.testing.semantic import judge_output

            score, reason = judge_output(result, criterion)
        except ImportError:
            logger.warning(
                "semantic_criteria set but litellm is not installed; skipping "
                "semantic check. Install with: pip install agentspan[testing]"
            )
            return None
        except Exception as exc:  # judge/network/parse failure — surface as a failed check
            return EvalCheckResult(
                check="semantic", passed=False, message=f"Semantic judge error: {exc}"
            )

        passed = score >= threshold
        message = "" if passed else f"semantic score {score:.2f} < threshold {threshold:.2f}"
        return EvalCheckResult(
            check="semantic",
            passed=passed,
            message=message,
            score=score,
            reasoning=reason,
        )


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
