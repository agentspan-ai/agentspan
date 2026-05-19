# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Suite 20: Plan-Execute (PAC/PAE) — workflow scheduling regression guard.

Catches the conductor-side bug where ``subWorkflowParam.workflowDefinition``
held as a runtime expression string (``${plan_and_compile.output.workflowDef}``)
was not resolved at scheduleTask time, surfacing as:

    Error scheduling tasks: [...]
    Caused by: IllegalArgumentException: Cannot construct instance of
    `WorkflowDef`: no String-argument constructor/factory method to
    deserialize from String value ('${...output.workflowDef}')

Fixed in conductor-oss PR #1068 (v3.30.0.rc12+). This suite asserts that a
minimal PLAN_EXECUTE agent submits, schedules, and progresses past the
plan-compile → plan-exec handoff — i.e. ``Error scheduling tasks`` never
appears in ``reasonForIncompletion``.

We do not assert COMPLETED status. The planner is LLM-driven and may
produce malformed plans; what we care about here is that the conductor
runtime can wire and dispatch the compiled SUB_WORKFLOW. The test passes
as long as the workflow reaches a terminal status WITHOUT the scheduling
error.
"""

from __future__ import annotations

import os

import pytest
import requests

from agentspan.agents import Agent, Op, Plan, Ref, Step, Strategy, plan_execute, tool

pytestmark = pytest.mark.e2e

SERVER_URL = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
BASE_URL = SERVER_URL.rstrip("/").replace("/api", "")
MODEL = os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o-mini")

PLAN_EXEC_TIMEOUT = 300  # 5 min — plan + compile + execute + (optional) fallback


# ── Minimal tool the plan can call (deterministic, no external calls) ──


@tool
def append_line(path: str, line: str) -> str:
    """Append a single line to a file at path; returns 'ok'."""
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    return "ok"


# ── Helpers ────────────────────────────────────────────────────────────


def _get_workflow(execution_id: str) -> dict:
    resp = requests.get(
        f"{BASE_URL}/api/workflow/{execution_id}", params={"includeTasks": "true"}, timeout=10
    )
    resp.raise_for_status()
    return resp.json()


def _has_scheduling_error(wf: dict) -> bool:
    """The exact failure mode this suite guards against."""
    reason = (wf.get("reasonForIncompletion") or "").lower()
    return "error scheduling tasks" in reason


# ── Tests ──────────────────────────────────────────────────────────────


class TestSuite20PlanExecute:
    """PLAN_EXECUTE strategy — workflow scheduling regression."""

    def test_plan_execute_submits_and_schedules(self, runtime, model):
        """A PLAN_EXECUTE agent compiles, starts, and schedules the inner DAG.

        The bug we guard against: the inner ``plan_exec`` SUB_WORKFLOW failed
        to schedule because its ``workflowDefinition`` was an unresolved
        ``${...output.workflowDef}`` string template. The workflow finished
        in FAILED status with ``Error scheduling tasks`` in seconds.

        Passing means:
          - HTTP /agent/start returns 200 + executionId.
          - The workflow reaches a terminal status (COMPLETED / FAILED /
            TERMINATED / TIMED_OUT) within the timeout.
          - ``reasonForIncompletion`` does NOT contain
            ``Error scheduling tasks``.
        """
        planner = Agent(
            name="s20_planner",
            model=model,
            max_turns=3,
            instructions=(
                "Produce a JSON plan inside a ```json fence describing exactly one "
                "step that calls the ``append_line`` tool with path='/tmp/agentspan_s20.txt' "
                "and line='hello'. Use this exact shape:\n"
                '```json\n{"steps": [{"tool": "append_line", '
                '"args": {"path": "/tmp/agentspan_s20.txt", "line": "hello"}}]}\n```'
            ),
        )

        fallback = Agent(
            name="s20_fallback",
            model=model,
            max_turns=3,
            instructions="If you receive this, just say 'fallback ok'.",
            tools=[append_line],
        )

        harness = Agent(
            name="e2e_s20_plan_execute_smoke",
            model=model,
            tools=[append_line],
            planner=planner,
            fallback=fallback,
            strategy=Strategy.PLAN_EXECUTE,
            fallback_max_turns=3,
        )

        result = runtime.run(
            harness, "Append 'hello' to /tmp/agentspan_s20.txt", timeout=PLAN_EXEC_TIMEOUT
        )

        assert result.execution_id, f"start failed; result={result!r}"

        # Status must be terminal — RUNNING means the test timeout hit before
        # the workflow finished. Indicates a hang (e.g., worker not polling).
        assert result.status in ("COMPLETED", "FAILED", "TERMINATED", "TIMED_OUT"), (
            f"Workflow did not reach terminal status. status={result.status} "
            f"execution_id={result.execution_id} error={result.error!r}"
        )

        # The scheduling-error regression: workflows that hit this bug fail
        # in <10s with this exact reason in seconds. Verify it's absent.
        wf = _get_workflow(result.execution_id)
        reason = wf.get("reasonForIncompletion") or ""
        assert "error scheduling tasks" not in reason.lower(), (
            f"Scheduling regression detected: 'Error scheduling tasks' appeared "
            f"in reasonForIncompletion. This indicates the conductor template-"
            f"resolution fix (conductor-oss #1068, rc12+) is not in effect.\n"
            f"  status={result.status}\n"
            f"  execution_id={result.execution_id}\n"
            f"  reasonForIncompletion={reason}"
        )

        # Also assert the inner plan_exec was either COMPLETED, RUNNING,
        # FAILED-on-content (not CANCELED due to scheduling). CANCELED on
        # plan_exec specifically is the smoking-gun symptom of the bug.
        tasks = wf.get("tasks") or []
        plan_exec_tasks = [t for t in tasks if t.get("referenceTaskName", "").endswith("_plan_exec")]
        for t in plan_exec_tasks:
            assert t.get("status") != "CANCELED", (
                f"plan_exec SUB_WORKFLOW is CANCELED — usually means the parent "
                f"sweeper failed to schedule it. taskId={t.get('taskId')} "
                f"task_reason={(t.get('reasonForIncompletion') or '')[:200]}"
            )


# ── Captured state for deterministic Ref test ────────────────────────────


CAPTURED_PIPELINE: dict = {}


@tool
def s20_produce(record_id: str) -> dict:
    """Step A — emit a known record."""
    return {"record_id": record_id, "value": 42, "tags": ["alpha", "beta"]}


@tool
def s20_enrich(record: dict) -> dict:
    """Step B — read Step A's whole dict via Ref('a'). Algorithmic only."""
    return {**record, "value_squared": (record.get("value", 0)) ** 2}


@tool
def s20_report(record: dict, enriched: dict) -> dict:
    """Step C — read BOTH upstream steps via two Refs in the same args map."""
    return {
        "id": record.get("record_id"),
        "original_value": record.get("value"),
        "squared": enriched.get("value_squared"),
        "tags_joined": ", ".join(record.get("tags") or []),
    }


class TestSuite20PlanExecuteRefs:
    """Deterministic PAC/PAE tests — no LLM in the assertion path.

    The planner sub-agent is built but its output is discarded by the
    static-plan path (``runtime.run(plan=...)``). All assertions are
    algorithmic — per CLAUDE.md, we never use LLM output for validation.
    """

    def _build_harness(self, model: str) -> Agent:
        return plan_execute(
            name="e2e_s20_refs_det",
            tools=[s20_produce, s20_enrich, s20_report],
            planner_instructions="(planner unused; static plan supplied)",
            model=model,
        )

    def _fetch_step_outputs(self, execution_id: str) -> dict:
        """Return {tool_name: outputData_dict} from the plan_exec sub-workflow."""
        wf = _get_workflow(execution_id)
        sub_id = None
        for t in wf.get("tasks") or []:
            if t.get("referenceTaskName", "").endswith("_plan_exec"):
                sub_id = (t.get("outputData") or {}).get("subWorkflowId")
                break
        assert sub_id, f"no plan_exec sub-workflow found in {execution_id}"
        sub = _get_workflow(sub_id)
        out = {}
        for t in sub.get("tasks") or []:
            name = t.get("taskDefName")
            if name in ("s20_produce", "s20_enrich", "s20_report"):
                out[name] = t.get("outputData") or {}
        return out

    def test_ref_pipes_whole_output_across_steps(self, runtime, model):
        """Ref('a') wires step A's whole dict into step B's `record` arg.

        Counterfactual: if the SDK didn't rewrite ``{"$ref":"a"}`` to a
        Conductor template, step B would receive the literal marker dict
        and ``record.get("value", 0) ** 2`` would be 0 (not 1764). Asserting
        on the exact squared value rules that out.
        """
        harness = self._build_harness(model)
        plan = Plan(
            steps=[
                Step("a", operations=[Op("s20_produce", args={"record_id": "r-001"})]),
                Step(
                    "b",
                    depends_on=["a"],
                    operations=[Op("s20_enrich", args={"record": Ref("a")})],
                ),
            ],
        )

        result = runtime.run(harness, "go", plan=plan, timeout=PLAN_EXEC_TIMEOUT)
        assert result.execution_id
        assert str(result.status) in ("COMPLETED", "completed", "Status.COMPLETED"), (
            f"workflow did not COMPLETE: status={result.status} error={result.error!r}"
        )

        outputs = self._fetch_step_outputs(result.execution_id)
        # Step A — emitted the seed dict.
        assert outputs["s20_produce"] == {
            "record_id": "r-001",
            "value": 42,
            "tags": ["alpha", "beta"],
        }, f"unexpected produce output: {outputs['s20_produce']!r}"

        # Step B — proves Ref('a') delivered the whole upstream dict.
        enrich = outputs["s20_enrich"]
        assert enrich.get("value_squared") == 1764, (
            f"value_squared must be 1764 (= 42²) — got {enrich.get('value_squared')!r}. "
            f"If Ref didn't carry the dict, enrich would have received the literal "
            f"{{'$ref':'a'}} marker and squared 0. Full enrich output: {enrich!r}"
        )
        # Original fields survived the merge.
        assert enrich.get("value") == 42
        assert enrich.get("record_id") == "r-001"
        assert enrich.get("tags") == ["alpha", "beta"]

    def test_two_refs_in_same_args_resolve_independently(self, runtime, model):
        """A single Op.args map with two Refs resolves both correctly.

        Counterfactual: if the recursive serializer collapsed both Refs to
        the same upstream, step C would see record == enriched and
        ``squared`` would equal ``original_value`` (both 42). Asserting
        squared=1764 ≠ original_value=42 rules that out.
        """
        harness = self._build_harness(model)
        plan = Plan(
            steps=[
                Step("a", operations=[Op("s20_produce", args={"record_id": "r-001"})]),
                Step(
                    "b",
                    depends_on=["a"],
                    operations=[Op("s20_enrich", args={"record": Ref("a")})],
                ),
                Step(
                    "c",
                    depends_on=["a", "b"],
                    operations=[
                        Op("s20_report", args={"record": Ref("a"), "enriched": Ref("b")}),
                    ],
                ),
            ],
        )

        result = runtime.run(harness, "go", plan=plan, timeout=PLAN_EXEC_TIMEOUT)
        assert str(result.status) in ("COMPLETED", "completed", "Status.COMPLETED")

        outputs = self._fetch_step_outputs(result.execution_id)
        report = outputs["s20_report"]
        assert report == {
            "id": "r-001",
            "original_value": 42,
            "squared": 1764,
            "tags_joined": "alpha, beta",
        }, f"unexpected report output: {report!r}"

    def test_ref_to_unknown_step_fails_at_compile_time(self, runtime, model):
        """A Ref to a step not in depends_on must fail with a clear PAC error.

        Counterfactual: silent acceptance would let the workflow run with
        an unresolved Conductor template, surfacing later as a hard-to-debug
        runtime failure deep in the worker. Compile-time rejection is the
        contract we want.
        """
        harness = self._build_harness(model)
        plan = Plan(
            steps=[
                Step("a", operations=[Op("s20_produce", args={"record_id": "r"})]),
                Step(
                    "b",
                    # depends_on intentionally MISSING — must fail
                    operations=[Op("s20_enrich", args={"record": Ref("a")})],
                ),
            ],
        )
        result = runtime.run(harness, "go", plan=plan, timeout=PLAN_EXEC_TIMEOUT)
        # Server validates at compile time and emits an error on the PAC
        # SystemTask; the harness then routes to fallback or terminates.
        # The full execution is FAILED/TERMINATED, NOT COMPLETED with the
        # report tool actually having run.
        outputs = self._fetch_step_outputs_if_any(result.execution_id)
        assert "s20_enrich" not in outputs, (
            f"enrich should never run when Ref points outside depends_on; "
            f"got outputs={outputs!r}"
        )

    def _fetch_step_outputs_if_any(self, execution_id: str) -> dict:
        """Like _fetch_step_outputs but tolerant of missing plan_exec sub-wf."""
        wf = _get_workflow(execution_id)
        sub_id = None
        for t in wf.get("tasks") or []:
            if t.get("referenceTaskName", "").endswith("_plan_exec"):
                sub_id = (t.get("outputData") or {}).get("subWorkflowId")
                break
        if not sub_id:
            return {}
        sub = _get_workflow(sub_id)
        out = {}
        for t in sub.get("tasks") or []:
            name = t.get("taskDefName")
            if name in ("s20_produce", "s20_enrich", "s20_report"):
                out[name] = t.get("outputData") or {}
        return out
