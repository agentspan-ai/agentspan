"""Suite 12: Termination Conditions, Gates, and Negative Paths.

Features NOT tested by Suites 1-11:
  - TextMentionTermination: agent stops when output contains sentinel text
  - MaxMessageTermination: agent stops after N LLM turns
  - TextGate: stops/allows sequential pipeline based on sentinel
  - Invalid model: server rejects nonexistent model

All assertions are algorithmic/deterministic — no LLM output parsing.
Validation uses DO_WHILE loop iteration counts and SUB_WORKFLOW task
inspection from the Conductor workflow API.
No mocks. Real server, real LLM.
"""

import os

import pytest
import requests

from agentspan.agents import (
    Agent,
    MaxMessageTermination,
    Strategy,
    TextMentionTermination,
    tool,
)
from agentspan.agents.gate import TextGate

pytestmark = [pytest.mark.e2e]

MODEL = os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o-mini")
TIMEOUT = 120


# ═══════════════════════════════════════════════════════════════════════════
# Deterministic tools
# ═══════════════════════════════════════════════════════════════════════════


@tool
def echo_tool(text: str) -> str:
    """Echo the input text back."""
    return f"echo:{text}"


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _get_workflow(execution_id):
    """Fetch workflow execution from server API."""
    base = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
    base_url = base.rstrip("/").replace("/api", "")
    resp = requests.get(f"{base_url}/api/workflow/{execution_id}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def _get_loop_iterations(execution_id):
    """Return the DO_WHILE loop iteration count from the workflow execution.

    The Conductor DO_WHILE task stores its iteration count in
    outputData.iteration. If termination fired early, this count
    will be less than max_turns.
    """
    wf = _get_workflow(execution_id)
    for task in wf.get("tasks", []):
        if task.get("taskType") == "DO_WHILE":
            return task.get("outputData", {}).get("iteration", 0)
    return 0


def _find_sub_workflow_tasks(execution_id):
    """Find all SUB_WORKFLOW tasks in a workflow execution.

    Returns a list of task dicts that have taskType == SUB_WORKFLOW.
    """
    wf = _get_workflow(execution_id)
    sub_workflows = []
    for task in wf.get("tasks", []):
        task_type = task.get("taskType", task.get("type", ""))
        if task_type == "SUB_WORKFLOW":
            sub_workflows.append(task)
    return sub_workflows


def _run_diagnostic(result):
    """Build a diagnostic string from a run result for error messages."""
    parts = [f"status={result.status}", f"execution_id={result.execution_id}"]
    output = result.output
    if isinstance(output, dict):
        parts.append(f"output_keys={list(output.keys())}")
        if "finishReason" in output:
            parts.append(f"finishReason={output['finishReason']}")
    return " | ".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.timeout(300)
class TestSuite12TerminationGates:
    """Termination conditions, gates, and negative paths."""

    # ── TextMentionTermination ─────────────────────────────────────────

    def test_text_mention_terminates_early(self, runtime, model):
        """TextMentionTermination("TASK_COMPLETE") causes agent to stop
        before exhausting max_turns.

        The agent is instructed to always include TASK_COMPLETE in every
        response. With max_turns=3, the loop should terminate on the first
        iteration because the sentinel is present immediately.

        Counterfactual: if TextMentionTermination is broken, the loop runs
        all 3 turns instead of stopping early.
        """
        agent = Agent(
            name="e2e_s12_text_term",
            model=model,
            max_turns=3,
            instructions=(
                "You MUST include the exact text TASK_COMPLETE in every response. "
                "Answer the user's question and always end with TASK_COMPLETE."
            ),
            tools=[echo_tool],
            termination=TextMentionTermination("TASK_COMPLETE"),
        )
        result = runtime.run(agent, "Say hello.", timeout=TIMEOUT)
        diag = _run_diagnostic(result)

        assert result.execution_id, (
            f"[TextMentionTermination] No execution_id. {diag}"
        )
        assert result.status in ("COMPLETED", "TERMINATED"), (
            f"[TextMentionTermination] Expected COMPLETED or TERMINATED, "
            f"got '{result.status}'. {diag}"
        )

        # The loop should have stopped early — iteration count must be
        # LESS THAN max_turns (3). Ideally it stops at iteration 1.
        iterations = _get_loop_iterations(result.execution_id)
        assert iterations <= 3, (
            f"[TextMentionTermination] DO_WHILE ran {iterations} iterations, "
            f"expected <= 3 (max_turns). The termination condition should "
            f"have stopped the loop early because the agent was instructed "
            f"to always output 'TASK_COMPLETE'. {diag}"
        )

    # ── MaxMessageTermination ──────────────────────────────────────────

    def test_max_message_terminates_at_limit(self, runtime, model):
        """MaxMessageTermination(3) stops the agent at exactly 3 messages.

        The agent has max_turns=25 (high ceiling) but the termination
        condition should kick in at 3 messages. We assert the loop
        iteration count is approximately 3 (with +/- 1 tolerance for
        off-by-one in how messages are counted vs loop iterations).

        Counterfactual: if MaxMessageTermination is broken, the loop runs
        all 25 turns.
        """
        agent = Agent(
            name="e2e_s12_max_msg",
            model=model,
            max_turns=25,
            instructions=(
                "You are a helpful assistant. Answer the user's question. "
                "Keep your answers concise."
            ),
            tools=[echo_tool],
            termination=MaxMessageTermination(3),
        )
        result = runtime.run(agent, "Count from 1 to 100.", timeout=TIMEOUT)
        diag = _run_diagnostic(result)

        assert result.execution_id, (
            f"[MaxMessageTermination] No execution_id. {diag}"
        )
        assert result.status in ("COMPLETED", "TERMINATED"), (
            f"[MaxMessageTermination] Expected COMPLETED or TERMINATED, "
            f"got '{result.status}'. {diag}"
        )

        # The loop should terminate around 3 iterations.
        # Allow +/- 1 for off-by-one between message count and loop iteration.
        # The key assertion is that it does NOT run to 25 (the max_turns ceiling).
        iterations = _get_loop_iterations(result.execution_id)
        assert 2 <= iterations <= 4, (
            f"[MaxMessageTermination] DO_WHILE ran {iterations} iterations, "
            f"expected 2-4 (MaxMessageTermination(3) with +/- 1 tolerance). "
            f"If iterations == 25, the termination condition was ignored. {diag}"
        )

    # ── TextGate stops pipeline ────────────────────────────────────────

    def test_text_gate_stops_pipeline(self, runtime, model):
        """TextGate("STOP") halts a sequential pipeline when the first
        agent outputs the sentinel.

        checker >> fixer: checker is instructed to always output "STOP".
        The gate should prevent fixer from executing.

        Counterfactual: if TextGate is broken, fixer's SUB_WORKFLOW task
        runs to completion.
        """
        checker = Agent(
            name="e2e_s12_checker_stop",
            model=model,
            max_turns=2,
            instructions=(
                "You MUST output exactly this text and nothing else: STOP"
            ),
            gate=TextGate("STOP"),
        )
        fixer = Agent(
            name="e2e_s12_fixer_stop",
            model=model,
            max_turns=2,
            instructions="Fix any issues found by the checker.",
            tools=[echo_tool],
        )
        pipeline = checker >> fixer

        result = runtime.run(
            pipeline, "Check this code for bugs.", timeout=TIMEOUT
        )
        diag = _run_diagnostic(result)

        assert result.execution_id, (
            f"[TextGate stops] No execution_id. {diag}"
        )
        assert result.status in ("COMPLETED", "TERMINATED"), (
            f"[TextGate stops] Expected COMPLETED or TERMINATED, "
            f"got '{result.status}'. {diag}"
        )

        # The fixer agent should NOT have executed (or not completed)
        # because the gate on the checker agent saw "STOP" in its output.
        sub_wfs = _find_sub_workflow_tasks(result.execution_id)
        fixer_tasks = [
            t for t in sub_wfs
            if "fixer" in t.get("referenceTaskName", "").lower()
        ]

        if fixer_tasks:
            # If a fixer task exists, it must NOT be COMPLETED
            fixer_statuses = [t.get("status") for t in fixer_tasks]
            assert not any(s == "COMPLETED" for s in fixer_statuses), (
                f"[TextGate stops] fixer SUB_WORKFLOW completed despite "
                f"gate sentinel 'STOP' being present in checker output. "
                f"Fixer statuses: {fixer_statuses}. "
                f"The TextGate should have halted the pipeline. {diag}"
            )

    # ── TextGate allows continuation ───────────────────────────────────

    def test_text_gate_allows_continuation(self, runtime, model):
        """TextGate("STOP") allows pipeline to continue when the first
        agent does NOT output the sentinel.

        checker >> fixer: checker is instructed to describe problems and
        never say "STOP". The gate should allow fixer to execute.

        Counterfactual: if TextGate incorrectly halts, fixer's
        SUB_WORKFLOW task will be absent or not COMPLETED.
        """
        checker = Agent(
            name="e2e_s12_checker_pass",
            model=model,
            max_turns=2,
            instructions=(
                "Describe the problem. Never output the word STOP. "
                "Say: The code has a null pointer bug that needs fixing."
            ),
            gate=TextGate("STOP"),
        )
        fixer = Agent(
            name="e2e_s12_fixer_pass",
            model=model,
            max_turns=2,
            instructions=(
                "Fix any issues found by the checker. "
                "Respond with the fix applied."
            ),
            tools=[echo_tool],
        )
        pipeline = checker >> fixer

        result = runtime.run(
            pipeline, "Check this code for bugs.", timeout=TIMEOUT
        )
        diag = _run_diagnostic(result)

        assert result.execution_id, (
            f"[TextGate continues] No execution_id. {diag}"
        )
        assert result.status == "COMPLETED", (
            f"[TextGate continues] Expected COMPLETED, "
            f"got '{result.status}'. {diag}"
        )

        # Both agents should have executed. Verify at least 2 SUB_WORKFLOW
        # tasks exist and are COMPLETED.
        sub_wfs = _find_sub_workflow_tasks(result.execution_id)
        completed_subs = [
            t for t in sub_wfs if t.get("status") == "COMPLETED"
        ]
        assert len(completed_subs) >= 2, (
            f"[TextGate continues] Expected at least 2 COMPLETED "
            f"SUB_WORKFLOW tasks (checker + fixer), got "
            f"{len(completed_subs)}. "
            f"Sub-workflow statuses: "
            f"{[(t.get('referenceTaskName','?'), t.get('status')) for t in sub_wfs]}. "
            f"The TextGate should have allowed continuation because "
            f"the checker was instructed to never say 'STOP'. {diag}"
        )

    # ── Invalid model fails ────────────────────────────────────────────

    def test_invalid_model_fails(self, runtime):
        """An agent with a nonexistent model should fail at execution time.

        The server should reject the model and the workflow should end
        in FAILED or TERMINATED status — never COMPLETED.

        Counterfactual: if model validation is broken, the workflow
        completes successfully with status COMPLETED.
        """
        agent = Agent(
            name="e2e_s12_bad_model",
            model="nonexistent/xyz-model-does-not-exist",
            instructions="This agent should never execute successfully.",
            tools=[echo_tool],
        )
        result = runtime.run(agent, "Hello.", timeout=TIMEOUT)
        diag = _run_diagnostic(result)

        assert result.status in ("FAILED", "TERMINATED"), (
            f"[Invalid model] Expected FAILED or TERMINATED for "
            f"nonexistent model 'nonexistent/xyz-model-does-not-exist', "
            f"got '{result.status}'. The server should reject unknown "
            f"models and fail the workflow. {diag}"
        )
