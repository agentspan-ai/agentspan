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

from agentspan.agents import Agent, Strategy, tool

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
