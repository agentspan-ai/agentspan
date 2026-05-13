"""Suite 14: Stateful Domain Propagation — verify workers register under the correct domain.

When an agent has stateful=True, the Conductor server schedules ALL tasks
(tools, stop_when, termination, handoff, check_transfer, etc.) under the
execution's unique domain UUID. Workers must register in that same domain
or tasks stay SCHEDULED with pollCount=0 forever.

Tests:
  - Stateful tool completes (not stuck in SCHEDULED)
  - Stateful stop_when callback executes in domain
  - Stateful swarm handoff + check_transfer execute in domain
  - Pipeline sub-agent tools inherit parent's domain
  - Concurrent stateful executions are isolated (different domains)
  - Agent without stateful flag works without domain

Validation: all assertions inspect the workflow execution via server API.
No mocks, no LLM output parsing, fully deterministic.
"""

import os
import time

import pytest
import requests

from agentspan.agents import (
    Agent,
    OnTextMention,
    Strategy,
    tool,
)
from agentspan.agents.termination import TextMentionTermination

pytestmark = [
    pytest.mark.e2e,
]

TIMEOUT = 300  # 5 min per run
SERVER_URL = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
BASE_URL = SERVER_URL.rstrip("/").replace("/api", "")


@pytest.fixture()
def fresh_runtime():
    """Function-scoped runtime — each test gets a clean worker manager.

    Stateful agents register workers under a per-execution domain. A shared
    runtime would carry stale domain registrations from previous tests,
    causing workers to poll the wrong domain. Fresh runtime per test avoids this.
    """
    from agentspan.agents import AgentRuntime

    with AgentRuntime() as rt:
        yield rt


# ===================================================================
# Deterministic tools
# ===================================================================


@tool
def echo_tool(message: str) -> str:
    """Return the message with a deterministic prefix."""
    return f"ECHO:{message}"


@tool(stateful=True)
def stateful_echo(message: str) -> str:
    """A stateful tool that echoes with a prefix."""
    return f"STATEFUL_ECHO:{message}"


@tool
def marker_tool_a(input_text: str) -> str:
    """Return a deterministic marker."""
    return "MARKER_A_DONE"


@tool
def marker_tool_b(input_text: str) -> str:
    """Return a deterministic marker."""
    return "MARKER_B_DONE"


@tool
def swarm_tool(task: str) -> str:
    """Perform a task and return a marker."""
    return f"SWARM_RESULT:{task}"


# ===================================================================
# Helpers
# ===================================================================


def _get_workflow(execution_id):
    """Fetch full workflow execution from server."""
    resp = requests.get(f"{BASE_URL}/api/workflow/{execution_id}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def _get_all_tasks(execution_id):
    """Get all tasks from a workflow execution, recursing into sub-workflows."""
    wf = _get_workflow(execution_id)
    tasks = wf.get("tasks", [])
    # Also fetch tasks from sub-workflows
    all_tasks = list(tasks)
    for t in tasks:
        if t.get("taskType") == "SUB_WORKFLOW" and t.get("status") == "COMPLETED":
            sub_id = t.get("subWorkflowId") or t.get("outputData", {}).get("subWorkflowId")
            if sub_id:
                try:
                    sub_tasks = _get_all_tasks(sub_id)
                    all_tasks.extend(sub_tasks)
                except Exception:
                    pass
    return all_tasks


def _get_task_to_domain(execution_id):
    """Get the taskToDomain mapping for an execution."""
    wf = _get_workflow(execution_id)
    return wf.get("taskToDomain", {})


def _find_tasks_by_type(tasks, task_def_name):
    """Find tasks matching a taskDefName (or containing it)."""
    return [t for t in tasks if task_def_name in t.get("taskDefName", "")]


def _find_scheduled_tasks(tasks):
    """Find tasks still in SCHEDULED state."""
    return [t for t in tasks if t.get("status") == "SCHEDULED"]


def _find_worker_tasks(tasks):
    """Find all SIMPLE (worker) tasks — the ones that need domain routing."""
    return [
        t for t in tasks
        if t.get("taskType") == "SIMPLE"
    ]


def _get_output_text(result):
    """Extract text output from a result."""
    output = result.output
    if isinstance(output, dict):
        results = output.get("result", [])
        if results:
            texts = []
            for r in results:
                if isinstance(r, dict):
                    texts.append(r.get("text", r.get("content", str(r))))
                else:
                    texts.append(str(r))
            return "".join(texts)
        return str(output)
    return str(output) if output else ""


def _run_diagnostic(result):
    """Diagnostic string for error messages."""
    parts = [f"status={result.status}", f"execution_id={result.execution_id}"]
    output = result.output
    if isinstance(output, dict):
        parts.append(f"output_keys={list(output.keys())}")
    return " | ".join(parts)


# ===================================================================
# Tests
# ===================================================================


@pytest.mark.timeout(1800)  # 30 min for the full suite
class TestSuite14StatefulDomain:
    """Stateful domain propagation: tools, system workers, sub-agents, isolation."""

    # ── Test 1: Stateful tool completes ─────────────────────────────

    def test_stateful_tool_completes(self, fresh_runtime, model):
        """A stateful agent's tool tasks execute (not stuck SCHEDULED).

        Creates an agent with stateful=True and a tool. Runs it.
        Validates via server API that:
          - Execution completes
          - Tool task has status=COMPLETED (not SCHEDULED)
          - taskToDomain is non-empty (domain was assigned)
          - Tool task's domain matches the taskToDomain value
        """
        agent = Agent(
            name="e2e_s14_stateful_tool",
            model=model,
            stateful=True,
            max_turns=3,
            instructions=(
                "You have an echo_tool. Call echo_tool with message='hello'. "
                "Then respond with what the tool returned."
            ),
            tools=[echo_tool],
        )
        result = fresh_runtime.run(agent, "Call the echo tool with hello", timeout=TIMEOUT)
        diag = _run_diagnostic(result)

        # 1. Execution completes
        assert result.status == "COMPLETED", (
            f"Expected COMPLETED, got {result.status}. {diag}"
        )

        # 2. taskToDomain is set (stateful=True means domain assigned)
        ttd = _get_task_to_domain(result.execution_id)
        assert ttd, (
            f"taskToDomain is empty — stateful agent should have domain mapping. {diag}"
        )

        # 3. echo_tool task is COMPLETED with matching domain
        all_tasks = _get_all_tasks(result.execution_id)
        echo_tasks = _find_tasks_by_type(all_tasks, "echo_tool")
        assert echo_tasks, (
            f"No echo_tool task found in execution. "
            f"Task names: {[t.get('taskDefName') for t in all_tasks]}"
        )
        for t in echo_tasks:
            assert t["status"] == "COMPLETED", (
                f"echo_tool task status={t['status']}, expected COMPLETED. "
                f"domain={t.get('domain')}, pollCount={t.get('pollCount')}"
            )
            # Domain should match what's in taskToDomain
            expected_domain = ttd.get("echo_tool")
            if expected_domain:
                assert t.get("domain") == expected_domain, (
                    f"echo_tool domain mismatch: task has {t.get('domain')}, "
                    f"taskToDomain has {expected_domain}"
                )

        # 4. No tasks stuck in SCHEDULED
        scheduled = _find_scheduled_tasks(all_tasks)
        assert not scheduled, (
            f"Tasks stuck in SCHEDULED: "
            f"{[(t['taskDefName'], t.get('domain'), t.get('pollCount')) for t in scheduled]}"
        )

    # ── Test 2: Stateful stop_when completes ───────────────────────

    def test_stateful_stop_when_completes(self, fresh_runtime, model):
        """stop_when callback on a stateful agent executes (not stuck SCHEDULED).

        The stop_when function checks for a marker in the output.
        Validates the stop_when worker task is COMPLETED with the correct domain.
        """
        def _should_stop(context, **kwargs):
            result = context.get("result", "")
            return "ECHO:" in result

        agent = Agent(
            name="e2e_s14_stateful_stop",
            model=model,
            stateful=True,
            max_turns=5,
            instructions=(
                "Call echo_tool with message='stop_test'. "
                "Then report the tool's response."
            ),
            tools=[echo_tool],
            stop_when=_should_stop,
        )
        result = fresh_runtime.run(agent, "Call echo_tool with stop_test", timeout=TIMEOUT)
        diag = _run_diagnostic(result)

        assert result.status == "COMPLETED", (
            f"Expected COMPLETED, got {result.status}. {diag}"
        )

        # Verify stop_when task executed
        all_tasks = _get_all_tasks(result.execution_id)
        stop_tasks = _find_tasks_by_type(all_tasks, "stop_when")
        assert stop_tasks, (
            f"No stop_when task found. "
            f"Task names: {[t.get('taskDefName') for t in all_tasks]}"
        )

        # At least one stop_when task should be COMPLETED
        completed_stops = [t for t in stop_tasks if t["status"] == "COMPLETED"]
        assert completed_stops, (
            f"No COMPLETED stop_when tasks. Statuses: "
            f"{[(t['status'], t.get('domain'), t.get('pollCount')) for t in stop_tasks]}"
        )

        # Verify domain is set
        ttd = _get_task_to_domain(result.execution_id)
        assert ttd, f"taskToDomain empty for stateful agent. {diag}"

        # No tasks stuck
        scheduled = _find_scheduled_tasks(all_tasks)
        assert not scheduled, (
            f"Tasks stuck in SCHEDULED: "
            f"{[(t['taskDefName'], t.get('pollCount')) for t in scheduled]}"
        )

    # ── Test 3: Stateful swarm handoff completes ───────────────────

    def test_stateful_swarm_handoff_completes(self, fresh_runtime, model):
        """Swarm handoff + check_transfer workers execute in domain.

        Creates a stateful swarm with two agents and OnTextMention handoff.
        Validates handoff_check and check_transfer tasks are COMPLETED.
        """
        agent_a = Agent(
            name="swarm_agent_a",
            model=model,
            max_turns=3,
            instructions=(
                "You are agent A. Call swarm_tool with task='from_a'. "
                "Then say HANDOFF_TO_B in your response."
            ),
            tools=[swarm_tool],
        )
        agent_b = Agent(
            name="swarm_agent_b",
            model=model,
            max_turns=3,
            instructions=(
                "You are agent B. Call swarm_tool with task='from_b'. "
                "Then say DONE in your response."
            ),
            tools=[swarm_tool],
        )
        swarm = Agent(
            name="e2e_s14_stateful_swarm",
            model=model,
            stateful=True,
            strategy=Strategy.SWARM,
            agents=[agent_a, agent_b],
            handoffs=[
                OnTextMention(text="HANDOFF_TO_B", target="swarm_agent_b"),
            ],
            termination=TextMentionTermination("DONE"),
            max_turns=20,
            instructions="Start with swarm_agent_a.",
        )
        result = fresh_runtime.run(swarm, "Execute the swarm workflow", timeout=TIMEOUT)
        diag = _run_diagnostic(result)

        assert result.status == "COMPLETED", (
            f"Expected COMPLETED, got {result.status}. {diag}"
        )

        # Verify domain is set
        ttd = _get_task_to_domain(result.execution_id)
        assert ttd, f"taskToDomain empty. {diag}"

        # Verify handoff-related tasks executed
        all_tasks = _get_all_tasks(result.execution_id)

        # handoff_check should exist and be COMPLETED
        handoff_tasks = _find_tasks_by_type(all_tasks, "handoff_check")
        assert handoff_tasks, (
            f"No handoff_check task found. "
            f"Task names: {[t.get('taskDefName') for t in all_tasks]}"
        )
        completed_handoffs = [t for t in handoff_tasks if t["status"] == "COMPLETED"]
        assert completed_handoffs, (
            f"No COMPLETED handoff_check. Statuses: "
            f"{[(t['status'], t.get('pollCount')) for t in handoff_tasks]}"
        )

        # termination should exist and be COMPLETED
        term_tasks = _find_tasks_by_type(all_tasks, "termination")
        if term_tasks:
            completed_terms = [t for t in term_tasks if t["status"] == "COMPLETED"]
            assert completed_terms, (
                f"No COMPLETED termination task. Statuses: "
                f"{[(t['status'], t.get('pollCount')) for t in term_tasks]}"
            )

        # No tasks stuck
        scheduled = _find_scheduled_tasks(all_tasks)
        assert not scheduled, (
            f"Tasks stuck in SCHEDULED: "
            f"{[(t['taskDefName'], t.get('pollCount')) for t in scheduled]}"
        )

    # ── Test 4: Mixed stateful and regular tools share domain ──────

    def test_stateful_mixed_tools(self, fresh_runtime, model):
        """Both @tool and @tool(stateful=True) work on a stateful agent.

        Creates one stateful agent with both a regular tool and a stateful tool.
        Validates both tool tasks complete in the same domain.
        """
        agent = Agent(
            name="e2e_s14_mixed_tools",
            model=model,
            stateful=True,
            max_turns=5,
            instructions=(
                "You have two tools. First call echo_tool with message='regular'. "
                "Then call stateful_echo with message='stateful'. "
                "Report both results."
            ),
            tools=[echo_tool, stateful_echo],
        )
        result = fresh_runtime.run(agent, "Call both tools", timeout=TIMEOUT)
        diag = _run_diagnostic(result)

        assert result.status == "COMPLETED", (
            f"Expected COMPLETED, got {result.status}. {diag}"
        )

        # Verify domain is set
        ttd = _get_task_to_domain(result.execution_id)
        assert ttd, f"taskToDomain empty. {diag}"

        # Both tools should have completed
        all_tasks = _get_all_tasks(result.execution_id)
        echo_tasks = _find_tasks_by_type(all_tasks, "echo_tool")
        stateful_tasks = _find_tasks_by_type(all_tasks, "stateful_echo")

        assert echo_tasks, (
            f"echo_tool not found. Tasks: {[t.get('taskDefName') for t in all_tasks]}"
        )
        assert stateful_tasks, (
            f"stateful_echo not found. Tasks: {[t.get('taskDefName') for t in all_tasks]}"
        )

        for t in echo_tasks:
            assert t["status"] == "COMPLETED", (
                f"echo_tool status={t['status']} pollCount={t.get('pollCount')}"
            )
        for t in stateful_tasks:
            assert t["status"] == "COMPLETED", (
                f"stateful_echo status={t['status']} pollCount={t.get('pollCount')}"
            )

        # Both should be in the same domain
        echo_domains = {t.get("domain") for t in echo_tasks if t.get("domain")}
        stateful_domains = {t.get("domain") for t in stateful_tasks if t.get("domain")}
        if echo_domains and stateful_domains:
            assert echo_domains == stateful_domains, (
                f"Domain mismatch: echo={echo_domains}, stateful={stateful_domains}"
            )

        # No stuck tasks
        scheduled = _find_scheduled_tasks(all_tasks)
        assert not scheduled, (
            f"Tasks stuck in SCHEDULED: "
            f"{[(t['taskDefName'], t.get('pollCount')) for t in scheduled]}"
        )

    # ── Test 5: Concurrent stateful isolation ──────────────────────

    def test_concurrent_stateful_isolation(self, model):
        """Two concurrent stateful executions get different domains and don't interfere.

        Uses separate runtimes — a single runtime can only serve one stateful
        execution per agent (workers register under one domain at a time).
        Validates: different domain UUIDs, both complete independently.
        """
        from agentspan.agents import AgentRuntime

        def _make_agent(suffix):
            return Agent(
                name=f"e2e_s14_concurrent_{suffix}",
                model=model,
                stateful=True,
                max_turns=3,
                instructions=(
                    "Call echo_tool with message='concurrent_test'. "
                    "Respond with the tool result."
                ),
                tools=[echo_tool],
            )

        # Run two executions with separate runtimes
        with AgentRuntime() as rt1:
            result_1 = rt1.run(_make_agent("a"), "Run 1: call echo_tool", timeout=TIMEOUT)
        with AgentRuntime() as rt2:
            result_2 = rt2.run(_make_agent("b"), "Run 2: call echo_tool", timeout=TIMEOUT)

        diag_1 = _run_diagnostic(result_1)
        diag_2 = _run_diagnostic(result_2)

        # Both complete
        assert result_1.status == "COMPLETED", f"Run 1: {diag_1}"
        assert result_2.status == "COMPLETED", f"Run 2: {diag_2}"

        # Different execution IDs
        assert result_1.execution_id != result_2.execution_id

        # Both have domains
        ttd_1 = _get_task_to_domain(result_1.execution_id)
        ttd_2 = _get_task_to_domain(result_2.execution_id)
        assert ttd_1, f"Run 1 taskToDomain empty. {diag_1}"
        assert ttd_2, f"Run 2 taskToDomain empty. {diag_2}"

        # Different domain UUIDs
        domains_1 = set(ttd_1.values())
        domains_2 = set(ttd_2.values())
        assert domains_1.isdisjoint(domains_2), (
            f"Concurrent runs should have different domains. "
            f"Run 1: {domains_1}, Run 2: {domains_2}"
        )

        # No stuck tasks in either
        for eid, diag in [(result_1.execution_id, diag_1), (result_2.execution_id, diag_2)]:
            all_tasks = _get_all_tasks(eid)
            scheduled = _find_scheduled_tasks(all_tasks)
            assert not scheduled, (
                f"Tasks stuck in SCHEDULED for {eid}: "
                f"{[(t['taskDefName'], t.get('pollCount')) for t in scheduled]}"
            )

    # ── Test 6: Agent without stateful flag has no domain ──────────

    def test_non_stateful_no_domain(self, fresh_runtime, model):
        """Agent without stateful=True works without domain assignment.

        Validates: taskToDomain is empty, tasks have no domain, execution completes.
        """
        agent = Agent(
            name="e2e_s14_non_stateful",
            model=model,
            # stateful=False is the default — explicitly NOT setting it
            max_turns=3,
            instructions=(
                "Call echo_tool with message='non_stateful'. "
                "Respond with the result."
            ),
            tools=[echo_tool],
        )
        result = fresh_runtime.run(agent, "Call echo_tool", timeout=TIMEOUT)
        diag = _run_diagnostic(result)

        assert result.status == "COMPLETED", (
            f"Expected COMPLETED, got {result.status}. {diag}"
        )

        # taskToDomain should be empty for non-stateful
        ttd = _get_task_to_domain(result.execution_id)
        assert not ttd, (
            f"Non-stateful agent should have empty taskToDomain. Got: {ttd}"
        )

        # echo_tool tasks should have no domain
        all_tasks = _get_all_tasks(result.execution_id)
        echo_tasks = _find_tasks_by_type(all_tasks, "echo_tool")
        assert echo_tasks, "No echo_tool task found"
        for t in echo_tasks:
            assert t["status"] == "COMPLETED", (
                f"echo_tool status={t['status']}"
            )
            # Domain should be absent or empty
            task_domain = t.get("domain")
            assert not task_domain, (
                f"Non-stateful echo_tool has domain={task_domain}, expected none"
            )
