# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tests for conductor.ai.agents.testing.eval_runner."""

from conductor.ai.agents.result import AgentEvent, AgentResult, EventType
from conductor.ai.agents.testing.eval_runner import (
    CorrectnessEval,
    EvalCase,
    EvalCaseResult,
    EvalSuiteResult,
)

# ── Fake runtime that returns scripted results ────────────────────────


class FakeRuntime:
    """A mock runtime that returns pre-configured results."""

    def __init__(self, results=None, error=None):
        self._results = results or {}
        self._error = error
        self.calls = []

    def run(self, agent, prompt):
        self.calls.append((agent, prompt))
        if self._error:
            raise self._error
        key = getattr(agent, "name", str(agent))
        if key in self._results:
            return self._results[key]
        # Default: simple completed result
        return AgentResult(output="default output", status="COMPLETED")


class FakeAgent:
    def __init__(
        self,
        name="test_agent",
        agents=None,
        strategy="handoff",
        max_turns=25,
        allowed_transitions=None,
    ):
        self.name = name
        self.agents = agents or []
        self.strategy = strategy
        self.max_turns = max_turns
        self.allowed_transitions = allowed_transitions


class FakeSubAgent:
    def __init__(self, name):
        self.name = name


# ── EvalSuiteResult ───────────────────────────────────────────────────


class TestEvalSuiteResult:
    def test_all_passed(self):
        suite = EvalSuiteResult(
            cases=[
                EvalCaseResult(name="a", passed=True),
                EvalCaseResult(name="b", passed=True),
            ]
        )
        assert suite.all_passed
        assert suite.pass_count == 2
        assert suite.fail_count == 0

    def test_some_failed(self):
        suite = EvalSuiteResult(
            cases=[
                EvalCaseResult(name="a", passed=True),
                EvalCaseResult(name="b", passed=False),
            ]
        )
        assert not suite.all_passed
        assert suite.pass_count == 1
        assert suite.fail_count == 1

    def test_failed_cases(self):
        suite = EvalSuiteResult(
            cases=[
                EvalCaseResult(name="a", passed=True),
                EvalCaseResult(name="b", passed=False),
                EvalCaseResult(name="c", passed=False),
            ]
        )
        failed = suite.failed_cases()
        assert len(failed) == 2
        assert failed[0].name == "b"
        assert failed[1].name == "c"


# ── CorrectnessEval ───────────────────────────────────────────────────


class TestCorrectnessEval:
    def test_basic_passing_case(self):
        """Simple case that should pass all checks."""
        runtime = FakeRuntime(
            results={
                "support": AgentResult(
                    output="Your refund has been processed.",
                    status="COMPLETED",
                    events=[
                        AgentEvent(type=EventType.HANDOFF, target="billing"),
                        AgentEvent(type=EventType.DONE, output="Your refund has been processed."),
                    ],
                    tool_calls=[{"name": "lookup_order", "args": {"id": "123"}}],
                ),
            }
        )
        agent = FakeAgent(
            name="support",
            agents=[FakeSubAgent("billing"), FakeSubAgent("tech")],
            strategy="handoff",
        )

        eval = CorrectnessEval(runtime)
        results = eval.run(
            [
                EvalCase(
                    name="billing_routes_correctly",
                    agent=agent,
                    prompt="I need a refund",
                    expect_handoff_to="billing",
                    expect_tools=["lookup_order"],
                    expect_output_contains=["refund"],
                ),
            ]
        )

        assert results.all_passed
        assert results.total == 1

    def test_tool_not_used_check(self):
        """Verify expect_tools_not_used catches violations."""
        runtime = FakeRuntime(
            results={
                "support": AgentResult(
                    output="Here's some info",
                    status="COMPLETED",
                    events=[AgentEvent(type=EventType.DONE, output="info")],
                    tool_calls=[{"name": "send_email", "args": {}}],
                ),
            }
        )
        agent = FakeAgent(name="support")

        eval = CorrectnessEval(runtime)
        results = eval.run(
            [
                EvalCase(
                    name="should_not_send_email",
                    agent=agent,
                    prompt="Tell me about the weather",
                    expect_tools_not_used=["send_email"],
                ),
            ]
        )

        assert not results.all_passed
        failed_checks = [c for c in results.cases[0].checks if not c.passed]
        assert any("send_email" in c.check for c in failed_checks)

    def test_handoff_to_wrong_agent(self):
        """Expect handoff to billing but got tech."""
        runtime = FakeRuntime(
            results={
                "support": AgentResult(
                    output="Tech support here",
                    status="COMPLETED",
                    events=[
                        AgentEvent(type=EventType.HANDOFF, target="tech"),
                        AgentEvent(type=EventType.DONE, output="Tech support here"),
                    ],
                ),
            }
        )
        agent = FakeAgent(
            name="support",
            agents=[FakeSubAgent("billing"), FakeSubAgent("tech")],
        )

        eval = CorrectnessEval(runtime)
        results = eval.run(
            [
                EvalCase(
                    name="should_go_to_billing",
                    agent=agent,
                    prompt="I need a refund",
                    expect_handoff_to="billing",
                ),
            ]
        )

        assert not results.all_passed

    def test_expect_no_handoff_to(self):
        """Verify that unexpected handoff is caught."""
        runtime = FakeRuntime(
            results={
                "support": AgentResult(
                    output="Done",
                    status="COMPLETED",
                    events=[
                        AgentEvent(type=EventType.HANDOFF, target="billing"),
                        AgentEvent(type=EventType.DONE, output="Done"),
                    ],
                ),
            }
        )
        agent = FakeAgent(
            name="support",
            agents=[FakeSubAgent("billing"), FakeSubAgent("tech")],
        )

        eval = CorrectnessEval(runtime)
        results = eval.run(
            [
                EvalCase(
                    name="should_not_go_to_billing",
                    agent=agent,
                    prompt="Tech question",
                    expect_no_handoff_to=["billing"],
                ),
            ]
        )

        assert not results.all_passed

    def test_agent_execution_error(self):
        """Runtime raises exception — case should fail gracefully."""
        runtime = FakeRuntime(error=RuntimeError("Server down"))
        agent = FakeAgent(name="broken")

        eval = CorrectnessEval(runtime)
        results = eval.run(
            [
                EvalCase(
                    name="execution_fails",
                    agent=agent,
                    prompt="Hello",
                ),
            ]
        )

        assert not results.all_passed
        assert "Server down" in results.cases[0].error

    def test_strategy_validation_integrated(self):
        """validate_orchestration=True runs strategy validator."""
        runtime = FakeRuntime(
            results={
                "pipeline": AgentResult(
                    output="Done",
                    status="COMPLETED",
                    events=[
                        # Only step_b ran, step_a was skipped
                        AgentEvent(type=EventType.HANDOFF, target="step_b"),
                        AgentEvent(type=EventType.DONE, output="Done"),
                    ],
                ),
            }
        )
        agent = FakeAgent(
            name="pipeline",
            agents=[FakeSubAgent("step_a"), FakeSubAgent("step_b")],
            strategy="sequential",
        )

        eval = CorrectnessEval(runtime)
        results = eval.run(
            [
                EvalCase(
                    name="sequential_must_run_all",
                    agent=agent,
                    prompt="Do it",
                    validate_orchestration=True,
                ),
            ]
        )

        assert not results.all_passed
        strategy_check = [c for c in results.cases[0].checks if c.check == "strategy_validation"]
        assert len(strategy_check) == 1
        assert not strategy_check[0].passed

    def test_custom_assertions(self):
        """Custom assertion functions are called."""
        runtime = FakeRuntime(
            results={
                "test": AgentResult(
                    output="42",
                    status="COMPLETED",
                    events=[AgentEvent(type=EventType.DONE, output="42")],
                ),
            }
        )
        agent = FakeAgent(name="test")

        def check_numeric_output(result: AgentResult):
            assert result.output.isdigit(), f"Expected numeric output, got: {result.output}"

        eval = CorrectnessEval(runtime)
        results = eval.run(
            [
                EvalCase(
                    name="custom_check",
                    agent=agent,
                    prompt="What is 6*7?",
                    custom_assertions=[check_numeric_output],
                ),
            ]
        )

        assert results.all_passed

    def test_tag_filtering(self):
        """Only run cases matching specified tags."""
        runtime = FakeRuntime()
        agent = FakeAgent(name="test")

        eval = CorrectnessEval(runtime)
        results = eval.run(
            [
                EvalCase(name="billing", agent=agent, prompt="A", tags=["billing"]),
                EvalCase(name="tech", agent=agent, prompt="B", tags=["tech"]),
                EvalCase(name="both", agent=agent, prompt="C", tags=["billing", "tech"]),
            ],
            tags=["billing"],
        )

        assert results.total == 2
        names = [c.name for c in results.cases]
        assert "billing" in names
        assert "both" in names
        assert "tech" not in names

    def test_output_matches(self):
        """Verify regex output matching."""
        runtime = FakeRuntime(
            results={
                "math": AgentResult(
                    output="The answer is 42.",
                    status="COMPLETED",
                    events=[AgentEvent(type=EventType.DONE, output="The answer is 42.")],
                ),
            }
        )
        agent = FakeAgent(name="math")

        eval = CorrectnessEval(runtime)
        results = eval.run(
            [
                EvalCase(
                    name="numeric_answer",
                    agent=agent,
                    prompt="What is 6*7?",
                    expect_output_matches=r"\d+",
                ),
            ]
        )

        assert results.all_passed

    def test_print_summary_runs(self, capsys):
        """print_summary should produce output without errors."""
        suite = EvalSuiteResult(
            cases=[
                EvalCaseResult(name="passed_case", passed=True, checks=[]),
                EvalCaseResult(name="failed_case", passed=False, checks=[]),
            ]
        )
        suite.print_summary()
        captured = capsys.readouterr()
        assert "PASS" in captured.out
        assert "FAIL" in captured.out
        assert "1/2 passed" in captured.out
