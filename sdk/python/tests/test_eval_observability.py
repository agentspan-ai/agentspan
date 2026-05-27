# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for eval observability (Issue #215).

Verifies:
- EvalCheckResult, EvalCaseResult, EvalSuiteResult serialize correctly via to_dict()
- Score/reasoning fields (Gap 3) round-trip through to_dict()
- CorrectnessEval tags runs with 'eval:' session_id prefix (Gap 1)
- CorrectnessEval calls _post_eval_run on the runtime after run() (Gap 2)
- No LLM used in assertions per CLAUDE.md
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from agentspan.agents.testing.eval_runner import (
    CorrectnessEval,
    EvalCase,
    EvalCaseResult,
    EvalCheckResult,
    EvalSuiteResult,
)
from agentspan.agents.result import AgentResult, FinishReason, Status


# ── Minimal stubs ──────────────────────────────────────────────────────────


@dataclass
class StubAgent:
    name: str = "stub-agent"


def _make_agent_result(status: str = "COMPLETED") -> AgentResult:
    return AgentResult(
        execution_id="exec-123",
        status=Status(status),
        finish_reason=FinishReason.STOP,
        output="Test output",
        messages=[],
        events=[],
        tool_calls=[],
    )


class StubRuntime:
    """Minimal runtime that records calls and returns a canned AgentResult."""

    def __init__(self, result: Optional[AgentResult] = None):
        self._result = result or _make_agent_result()
        self.calls: list = []
        self._posted_payloads: list = []

    def run(self, agent: Any, prompt: str, *, session_id: str = "", **kwargs) -> AgentResult:
        self.calls.append({"agent": agent, "prompt": prompt, "session_id": session_id})
        return self._result

    def _post_eval_run(self, payload: dict) -> None:
        self._posted_payloads.append(payload)


# ── EvalCheckResult ────────────────────────────────────────────────────────


class TestEvalCheckResultToDict:
    def test_basic_fields(self):
        check = EvalCheckResult(check="status", passed=True)
        d = check.to_dict()
        assert d["check"] == "status"
        assert d["passed"] is True
        assert d["message"] == ""
        assert "score" not in d
        assert "reasoning" not in d

    def test_failed_with_message(self):
        check = EvalCheckResult(check="tool_used:lookup", passed=False, message="Tool not used")
        d = check.to_dict()
        assert d["passed"] is False
        assert d["message"] == "Tool not used"

    def test_semantic_score_and_reasoning_included_when_set(self):
        check = EvalCheckResult(
            check="assert_output_satisfies",
            passed=True,
            score=0.85,
            reasoning="The response addressed the issue clearly.",
        )
        d = check.to_dict()
        assert d["score"] == pytest.approx(0.85)
        assert d["reasoning"] == "The response addressed the issue clearly."

    def test_score_none_not_in_dict(self):
        check = EvalCheckResult(check="status", passed=True, score=None)
        assert "score" not in check.to_dict()

    def test_reasoning_none_not_in_dict(self):
        check = EvalCheckResult(check="status", passed=True, reasoning=None)
        assert "reasoning" not in check.to_dict()


# ── EvalCaseResult ─────────────────────────────────────────────────────────


class TestEvalCaseResultToDict:
    def test_basic_fields(self):
        case = EvalCaseResult(name="my_case", passed=True, agent_name="my-agent")
        d = case.to_dict()
        assert d["name"] == "my_case"
        assert d["passed"] is True
        assert d["agentName"] == "my-agent"
        assert d["checks"] == []

    def test_checks_serialized(self):
        case = EvalCaseResult(
            name="c",
            passed=False,
            checks=[EvalCheckResult(check="status", passed=True)],
        )
        d = case.to_dict()
        assert len(d["checks"]) == 1
        assert d["checks"][0]["check"] == "status"

    def test_error_included(self):
        case = EvalCaseResult(name="c", passed=False, error="Timeout")
        assert case.to_dict()["error"] == "Timeout"


# ── EvalSuiteResult ────────────────────────────────────────────────────────


class TestEvalSuiteResultToDict:
    def test_basic_structure(self):
        suite = EvalSuiteResult(
            eval_run_id="run-abc",
            agent_name="my-agent",
            timestamp="2025-01-01T00:00:00Z",
            cases=[
                EvalCaseResult(name="c1", passed=True),
                EvalCaseResult(name="c2", passed=False),
            ],
        )
        d = suite.to_dict()
        assert d["id"] == "run-abc"
        assert d["agentName"] == "my-agent"
        assert d["totalCases"] == 2
        assert d["passedCases"] == 1
        assert len(d["cases"]) == 2

    def test_empty_suite(self):
        suite = EvalSuiteResult()
        d = suite.to_dict()
        assert d["totalCases"] == 0
        assert d["passedCases"] == 0
        assert d["cases"] == []


# ── CorrectnessEval — eval session tagging (Gap 1) ─────────────────────────


class TestEvalRunTagging:
    def test_run_passes_eval_session_id_to_runtime(self):
        agent = StubAgent("billing-agent")
        runtime = StubRuntime()
        ev = CorrectnessEval(runtime)

        ev.run([EvalCase(name="c1", agent=agent, prompt="Hello")])

        assert len(runtime.calls) == 1
        session_id = runtime.calls[0]["session_id"]
        assert session_id.startswith("eval:"), f"session_id should start with 'eval:', got: {session_id!r}"

    def test_all_cases_share_same_eval_session_id(self):
        agent = StubAgent()
        runtime = StubRuntime()
        ev = CorrectnessEval(runtime)

        ev.run([
            EvalCase(name="c1", agent=agent, prompt="First"),
            EvalCase(name="c2", agent=agent, prompt="Second"),
        ])

        session_ids = [c["session_id"] for c in runtime.calls]
        assert len(set(session_ids)) == 1, "All cases in a suite should use the same eval session_id"
        assert session_ids[0].startswith("eval:")

    def test_different_suite_runs_get_different_session_ids(self):
        agent = StubAgent()
        runtime = StubRuntime()
        ev = CorrectnessEval(runtime)

        ev.run([EvalCase(name="c1", agent=agent, prompt="A")])
        ev.run([EvalCase(name="c2", agent=agent, prompt="B")])

        ids = [c["session_id"] for c in runtime.calls]
        assert ids[0] != ids[1], "Different eval.run() calls should produce different session_ids"


# ── CorrectnessEval — result POSTed to server (Gap 2) ─────────────────────


class TestEvalResultPosted:
    def test_post_eval_run_called_after_run(self):
        agent = StubAgent("my-agent")
        runtime = StubRuntime()
        ev = CorrectnessEval(runtime)

        ev.run([EvalCase(name="billing_case", agent=agent, prompt="I need a refund")])

        assert len(runtime._posted_payloads) == 1
        payload = runtime._posted_payloads[0]
        assert payload["agentName"] == "my-agent"
        assert payload["totalCases"] == 1
        assert "id" in payload
        assert "timestamp" in payload

    def test_post_eval_run_not_raised_when_runtime_has_no_method(self):
        """If runtime doesn't have _post_eval_run, eval.run() should not raise."""

        class MinimalRuntime:
            def run(self, agent, prompt, **kw):
                return _make_agent_result()

        agent = StubAgent()
        ev = CorrectnessEval(MinimalRuntime())
        # Should not raise
        result = ev.run([EvalCase(name="c", agent=agent, prompt="Hi")])
        assert result.total == 1

    def test_post_eval_run_failure_doesnt_raise(self):
        """A server POST failure must not propagate out of eval.run()."""

        class FailingRuntime:
            def run(self, agent, prompt, **kw):
                return _make_agent_result()

            def _post_eval_run(self, payload):
                raise ConnectionError("Server unreachable")

        agent = StubAgent()
        ev = CorrectnessEval(FailingRuntime())
        result = ev.run([EvalCase(name="c", agent=agent, prompt="Hi")])
        assert result.total == 1  # result still returned even when POST fails


# ── CorrectnessEval — suite metadata (Gap 2) ──────────────────────────────


class TestSuiteMetadata:
    def test_suite_result_has_eval_run_id(self):
        agent = StubAgent()
        runtime = StubRuntime()
        ev = CorrectnessEval(runtime)

        result = ev.run([EvalCase(name="c", agent=agent, prompt="Hi")])

        assert result.eval_run_id, "eval_run_id should be set"
        assert result.timestamp, "timestamp should be set"

    def test_suite_result_has_agent_name_from_case(self):
        agent = StubAgent("special-agent")
        runtime = StubRuntime()
        ev = CorrectnessEval(runtime)

        result = ev.run([EvalCase(name="c", agent=agent, prompt="Hi")])

        assert result.agent_name == "special-agent"

    def test_suite_tags_passed_through(self):
        agent = StubAgent()
        runtime = StubRuntime()
        ev = CorrectnessEval(runtime)

        result = ev.run(
            [EvalCase(name="c", agent=agent, prompt="Hi")],
            suite_tags=["nightly", "billing"],
        )

        assert "nightly" in result.suite_tags
        assert "billing" in result.suite_tags

    def test_name_strategy_ranby_serialized(self):
        agent = StubAgent("my-agent")
        runtime = StubRuntime()
        ev = CorrectnessEval(runtime)

        result = ev.run(
            [EvalCase(name="c", agent=agent, prompt="Hi")],
            name="my_eval_v1",
            strategy="react",
            ran_by="ci_pipeline.py",
        )

        assert result.name == "my_eval_v1"
        assert result.strategy == "react"
        assert result.ran_by == "ci_pipeline.py"

        payload = runtime._posted_payloads[0]
        assert payload["name"] == "my_eval_v1"
        assert payload["strategy"] == "react"
        assert payload["ranBy"] == "ci_pipeline.py"


# ── CorrectnessEval — tags filter ─────────────────────────────────────────


class TestTagsFilter:
    def test_tags_filter_runs_only_matching_cases(self):
        agent = StubAgent()
        runtime = StubRuntime()
        ev = CorrectnessEval(runtime)

        cases = [
            EvalCase(name="auth_case", agent=agent, prompt="Login", tags=["auth"]),
            EvalCase(name="billing_case", agent=agent, prompt="Refund", tags=["billing"]),
            EvalCase(name="both_case", agent=agent, prompt="Both", tags=["auth", "billing"]),
        ]

        result = ev.run(cases, tags=["auth"])

        ran_names = [c.name for c in result.cases]
        assert "auth_case" in ran_names
        assert "both_case" in ran_names
        assert "billing_case" not in ran_names
        assert result.total == 2

    def test_tags_filter_with_no_match_runs_zero_cases(self):
        agent = StubAgent()
        runtime = StubRuntime()
        ev = CorrectnessEval(runtime)

        cases = [EvalCase(name="c1", agent=agent, prompt="Hi", tags=["nightly"])]

        result = ev.run(cases, tags=["smoke"])

        assert result.total == 0
        assert len(runtime.calls) == 0

    def test_no_tags_filter_runs_all_cases(self):
        agent = StubAgent()
        runtime = StubRuntime()
        ev = CorrectnessEval(runtime)

        cases = [
            EvalCase(name="c1", agent=agent, prompt="A", tags=["x"]),
            EvalCase(name="c2", agent=agent, prompt="B", tags=["y"]),
            EvalCase(name="c3", agent=agent, prompt="C"),
        ]

        result = ev.run(cases)

        assert result.total == 3


# ── agent_name not clobbered by expect_no_handoff_to loop ─────────────────


class TestAgentNamePreserved:
    def test_agent_name_not_overwritten_by_no_handoff_loop(self):
        """expect_no_handoff_to used a loop variable named agent_name that shadowed
        the outer agent_name — causing EvalCaseResult.agent_name to be set to the
        last entry of expect_no_handoff_to instead of the actual agent name."""
        agent = StubAgent("my-agent")
        runtime = StubRuntime()
        ev = CorrectnessEval(runtime)

        result = ev.run([
            EvalCase(
                name="routing_case",
                agent=agent,
                prompt="Hi",
                expect_no_handoff_to=["other-agent", "third-agent"],
            )
        ])

        assert result.cases[0].agent_name == "my-agent", (
            f"agent_name was corrupted to {result.cases[0].agent_name!r}"
        )
