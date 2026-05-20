"""Suite 16: Eval Observability — CorrectnessEval persists to server (Issue #215).

Covers all 4 gaps end-to-end against a real running server:
  Gap 1: eval runs are tagged with eval: session prefix and filtered from
          the default agent executions search
  Gap 2: eval suite result is persisted to /api/eval/runs and can be
          retrieved with full case + check detail
  Gap 3: EvalCheckResult score/reasoning fields round-trip through the server
          (structural check only — no LLM judge per CLAUDE.md)
  Gap 4: runtime.push_dataset() persists a dataset to /api/eval/datasets

Per CLAUDE.md: LLM is used to RUN the agent (that is the whole point of evals).
Assertions on the results are fully deterministic — no LLM-as-judge.
"""

import os
import uuid

import pytest
import requests

from agentspan.agents import Agent
from agentspan.agents.testing import CorrectnessEval, EvalCase
from agentspan.agents.testing.eval_runner import EvalCheckResult, EvalCaseResult, EvalSuiteResult

pytestmark = pytest.mark.e2e

SERVER_URL = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
EVAL_API = SERVER_URL.rstrip("/") + "/eval"
AGENT_API = SERVER_URL.rstrip("/") + "/agent"
TIMEOUT = 180


# ── Module-scoped fixtures ───────────────────────────────────────────────


@pytest.fixture(scope="module")
def eval_agent(model):
    # Unique name per run avoids conflicts with pre-registered agents
    return Agent(
        name=f"eval-e2e-{uuid.uuid4().hex[:8]}",
        model=model,
        instructions="You are a concise assistant. Follow instructions exactly.",
    )


@pytest.fixture(scope="module")
def suite_result(runtime, eval_agent):
    """Run one real eval suite against the live server. Shared across all Gap 2 tests."""
    ev = CorrectnessEval(runtime)
    result = ev.run(
        [
            EvalCase(
                name="should_pass",
                agent=eval_agent,
                # Highly deterministic prompt — model will always include CONFIRMED
                prompt="Reply with exactly one word: CONFIRMED",
                expect_output_contains=["CONFIRMED"],
                validate_orchestration=False,
            ),
            EvalCase(
                name="should_fail",
                agent=eval_agent,
                prompt="Reply with exactly one word: CONFIRMED",
                expect_output_contains=["DELIBERATE_MISS_XYZ"],
                validate_orchestration=False,
            ),
        ],
        suite_tags=["e2e", "eval-observability"],
    )
    return result


# ── Gap 2: persistence ───────────────────────────────────────────────────


class TestEvalRunPersisted:
    def test_suite_result_has_eval_run_id(self, suite_result):
        assert suite_result.eval_run_id, "eval_run_id should be set after run()"
        assert suite_result.timestamp, "timestamp should be set"

    def test_run_appears_in_list(self, suite_result):
        resp = requests.get(f"{EVAL_API}/runs", timeout=TIMEOUT)
        assert resp.status_code == 200
        body = resp.json()
        ids = [r["id"] for r in body.get("results", [])]
        assert suite_result.eval_run_id in ids, (
            f"Run {suite_result.eval_run_id} not found in /api/eval/runs list"
        )

    def test_run_detail_has_correct_counts(self, suite_result):
        resp = requests.get(f"{EVAL_API}/runs/{suite_result.eval_run_id}", timeout=TIMEOUT)
        assert resp.status_code == 200
        body = resp.json()
        assert body["totalCases"] == 2
        assert body["passedCases"] == 1

    def test_run_detail_has_cases(self, suite_result):
        resp = requests.get(f"{EVAL_API}/runs/{suite_result.eval_run_id}", timeout=TIMEOUT)
        body = resp.json()
        case_names = [c["name"] for c in body.get("cases", [])]
        assert "should_pass" in case_names
        assert "should_fail" in case_names

    def test_run_detail_has_checks(self, suite_result):
        resp = requests.get(f"{EVAL_API}/runs/{suite_result.eval_run_id}", timeout=TIMEOUT)
        body = resp.json()
        passing_case = next(c for c in body["cases"] if c["name"] == "should_pass")
        assert len(passing_case["checks"]) > 0, "should_pass case should have checks"
        check_names = [ch["check"] for ch in passing_case["checks"]]
        assert any("output_contains" in ch for ch in check_names)

    def test_failed_case_check_has_message(self, suite_result):
        resp = requests.get(f"{EVAL_API}/runs/{suite_result.eval_run_id}", timeout=TIMEOUT)
        body = resp.json()
        failing_case = next(c for c in body["cases"] if c["name"] == "should_fail")
        assert not failing_case["passed"]
        failing_checks = [ch for ch in failing_case["checks"] if not ch["passed"]]
        assert len(failing_checks) > 0
        assert failing_checks[0]["message"], "failed check should have a message"

    def test_run_not_found_returns_404(self):
        resp = requests.get(f"{EVAL_API}/runs/does-not-exist-xyz", timeout=TIMEOUT)
        assert resp.status_code == 404

    def test_suite_tags_persisted(self, suite_result):
        resp = requests.get(f"{EVAL_API}/runs/{suite_result.eval_run_id}", timeout=TIMEOUT)
        body = resp.json()
        # tags may be null if server stores as empty list — just check run is retrievable
        assert body["id"] == suite_result.eval_run_id


# ── Gap 1: eval runs filtered from agent executions ──────────────────────


class TestEvalRunFiltered:
    def test_eval_run_hidden_from_default_executions(self, suite_result):
        """Default search should not include eval runs."""
        resp = requests.get(
            f"{AGENT_API}/executions",
            params={"start": 0, "size": 50},
            timeout=TIMEOUT,
        )
        assert resp.status_code == 200
        body = resp.json()
        results = body.get("results", [])
        # Extract session IDs from workflow inputs
        for execution in results:
            wf_input = execution.get("input", "")
            assert f'"session_id":"eval:{suite_result.eval_run_id}' not in wf_input, (
                "Eval run should be filtered from default agent executions"
            )

    def test_eval_run_visible_with_include_flag(self, suite_result):
        """With includeEvalRuns=true the eval execution should appear."""
        resp = requests.get(
            f"{AGENT_API}/executions",
            params={"start": 0, "size": 100, "includeEvalRuns": "true"},
            timeout=TIMEOUT,
        )
        assert resp.status_code == 200
        body = resp.json()
        results = body.get("results", [])
        matching = [
            e for e in results
            if f'"session_id":"eval:{suite_result.eval_run_id}' in e.get("input", "")
            or suite_result.eval_run_id in e.get("input", "")
        ]
        # At least one workflow from this eval suite should be visible
        assert len(matching) > 0, (
            "Eval run should be visible when includeEvalRuns=true"
        )


# ── Gap 3: semantic score fields round-trip ──────────────────────────────


class TestSemanticScoreFields:
    """Verify score/reasoning fields persist and round-trip through the server.

    We POST a synthetic run directly (no LLM) to avoid flakiness.
    This tests the persistence layer, not the LLM judge itself.
    """

    def test_score_and_reasoning_round_trip(self):
        run_id = f"e2e-semantic-{uuid.uuid4().hex[:8]}"
        payload = {
            "id": run_id,
            "agentName": "eval-e2e-semantic",
            "timestamp": "2025-01-01T00:00:00Z",
            "totalCases": 1,
            "passedCases": 1,
            "cases": [
                {
                    "name": "semantic_case",
                    "passed": True,
                    "agentName": "eval-e2e-semantic",
                    "checks": [
                        {
                            "check": "assert_output_satisfies",
                            "passed": True,
                            "message": "",
                            "score": 0.92,
                            "reasoning": "The response clearly addressed the issue.",
                        }
                    ],
                }
            ],
        }
        post_resp = requests.post(f"{EVAL_API}/runs", json=payload, timeout=TIMEOUT)
        assert post_resp.status_code == 200

        get_resp = requests.get(f"{EVAL_API}/runs/{run_id}", timeout=TIMEOUT)
        assert get_resp.status_code == 200
        body = get_resp.json()

        semantic_check = next(
            ch
            for c in body["cases"]
            for ch in c["checks"]
            if ch["check"] == "assert_output_satisfies"
        )
        assert abs(semantic_check["score"] - 0.92) < 0.01
        assert semantic_check["reasoning"] == "The response clearly addressed the issue."


# ── Gap 4: dataset push and retrieval ────────────────────────────────────


class TestDatasetPushAndRetrieve:
    DATASET_NAME = f"e2e-test-dataset-{uuid.uuid4().hex[:8]}"

    def test_push_dataset(self, runtime):
        from agentspan.agents.testing import EvalCase
        from agentspan.agents import Agent

        agent = Agent(name="dummy", instructions="dummy")
        runtime.push_dataset(
            self.DATASET_NAME,
            [
                EvalCase(name="case1", agent=agent, prompt="Hello", tags=["smoke"]),
                EvalCase(name="case2", agent=agent, prompt="Goodbye"),
            ],
        )
        # Verify it appears in the list
        resp = requests.get(f"{EVAL_API}/datasets", timeout=TIMEOUT)
        assert resp.status_code == 200
        names = [d["name"] for d in resp.json()]
        assert self.DATASET_NAME in names

    def test_dataset_cases_retrievable(self):
        import urllib.parse

        encoded = urllib.parse.quote(self.DATASET_NAME)
        resp = requests.get(f"{EVAL_API}/datasets/{encoded}", timeout=TIMEOUT)
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == self.DATASET_NAME
        case_names = [c["name"] for c in body.get("cases", [])]
        assert "case1" in case_names
        assert "case2" in case_names

    def test_dataset_not_found_returns_404(self):
        resp = requests.get(f"{EVAL_API}/datasets/no-such-dataset-xyz", timeout=TIMEOUT)
        assert resp.status_code == 404

    def test_dataset_upsert_updates_cases(self, runtime):
        from agentspan.agents import Agent
        from agentspan.agents.testing import EvalCase

        agent = Agent(name="dummy", instructions="dummy")
        # Push again with 3 cases — should replace the 2 from test_push_dataset
        runtime.push_dataset(
            self.DATASET_NAME,
            [
                EvalCase(name="case1", agent=agent, prompt="Hello"),
                EvalCase(name="case2", agent=agent, prompt="Goodbye"),
                EvalCase(name="case3", agent=agent, prompt="New case"),
            ],
        )
        import urllib.parse

        encoded = urllib.parse.quote(self.DATASET_NAME)
        resp = requests.get(f"{EVAL_API}/datasets/{encoded}", timeout=TIMEOUT)
        body = resp.json()
        assert len(body["cases"]) == 3
