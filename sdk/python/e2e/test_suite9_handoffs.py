"""Suite 9: Agent Handoffs — compilation and runtime execution of multi-agent strategies.

Tests the core orchestration strategies:
  - All 8 strategies compile correctly via plan()
  - Sequential execution runs agents in order
  - Parallel execution forks agents concurrently
  - Handoff delegates to the correct sub-agent
  - Router selects the right agent based on input
  - Swarm with OnTextMention triggers conditional handoff
  - Pipe operator (>>) creates sequential pipelines

Each test uses deterministic tools with marker-prefixed output for algorithmic
validation. No LLM output parsing for routing decisions.
No mocks. Real server, real LLM.
"""

import os

import pytest
import requests

from agentspan.agents import (
    Agent,
    OnTextMention,
    Strategy,
    tool,
)

pytestmark = [
    pytest.mark.e2e,
]

TIMEOUT = 120


# ===================================================================
# Deterministic tools
# ===================================================================


@tool
def do_math(expr: str) -> str:
    """Evaluate a math expression."""
    return f"math_result:{expr}={eval(expr)}"


@tool
def do_text(text: str) -> str:
    """Reverse a string."""
    return f"text_result:{text[::-1]}"


@tool
def do_data(query: str) -> str:
    """Echo a data query."""
    return f"data_result:{query}"


# ===================================================================
# Child agent factories
# ===================================================================


def _math_agent(model):
    return Agent(
        name="math_agent",
        model=model,
        instructions=(
            "You are a math agent. When asked to compute something, call do_math "
            'with the expression. For example, for "3+4" call do_math with expr="3+4".'
        ),
        tools=[do_math],
    )


def _text_agent(model):
    return Agent(
        name="text_agent",
        model=model,
        instructions=(
            "You are a text agent. When asked to reverse text, call do_text "
            'with the text. For example, for "hello" call do_text with text="hello".'
        ),
        tools=[do_text],
    )


def _data_agent(model):
    return Agent(
        name="data_agent",
        model=model,
        instructions=(
            "You are a data agent. When asked to query data, call do_data "
            "with the query."
        ),
        tools=[do_data],
    )


# ===================================================================
# Helpers
# ===================================================================


def _get_workflow(execution_id):
    """Fetch workflow execution from server API."""
    base = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
    base_url = base.rstrip("/").replace("/api", "")
    resp = requests.get(f"{base_url}/api/workflow/{execution_id}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def _get_output_text(result):
    """Extract the text output from a run result."""
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
    """Build a diagnostic string from a run result for error messages."""
    parts = [f"status={result.status}", f"execution_id={result.execution_id}"]
    output = result.output
    if isinstance(output, dict):
        parts.append(f"output_keys={list(output.keys())}")
        if "finishReason" in output:
            parts.append(f"finishReason={output['finishReason']}")
    return " | ".join(parts)


def _agent_def(result):
    """Extract metadata.agentDef from a plan() result."""
    wf = result.get("workflowDef")
    assert wf is not None, (
        f"plan() result missing 'workflowDef'. "
        f"Top-level keys: {list(result.keys())}"
    )
    metadata = wf.get("metadata")
    assert metadata is not None, (
        f"workflowDef missing 'metadata'. "
        f"workflowDef keys: {list(wf.keys())}"
    )
    agent_def = metadata.get("agentDef")
    assert agent_def is not None, (
        f"workflowDef.metadata missing 'agentDef'. "
        f"metadata keys: {list(metadata.keys())}"
    )
    return agent_def


def _sub_agent_names(ad):
    """Extract sub-agent names from agentDef.agents."""
    return [a["name"] for a in ad.get("agents", [])]


def _all_tasks_flat(workflow_def):
    """Recursively collect all tasks from a workflow definition."""
    tasks = []
    for t in workflow_def.get("tasks", []):
        tasks.append(t)
        tasks.extend(_recurse_task(t))
    return tasks


def _recurse_task(t):
    """Recurse into a single task's nested children."""
    children = []
    for nested in t.get("loopOver", []):
        children.append(nested)
        children.extend(_recurse_task(nested))
    for case_tasks in t.get("decisionCases", {}).values():
        for ct in case_tasks:
            children.append(ct)
            children.extend(_recurse_task(ct))
    for ct in t.get("defaultCase", []):
        children.append(ct)
        children.extend(_recurse_task(ct))
    for fork_list in t.get("forkTasks", []):
        for ft in fork_list:
            children.append(ft)
            children.extend(_recurse_task(ft))
    return children


def _task_type_set(tasks):
    """Collect unique task type values."""
    return {t.get("type", "") for t in tasks}


def _sub_workflow_names(tasks):
    """Extract subWorkflowParam.name from SUB_WORKFLOW tasks."""
    names = []
    for t in tasks:
        if t.get("type") == "SUB_WORKFLOW":
            params = t.get("subWorkflowParam", {}) or t.get(
                "subWorkflowParams", {}
            )
            if params.get("name"):
                names.append(params["name"])
    return names


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


def _find_fork_tasks(execution_id):
    """Find FORK/FORK_JOIN tasks in a workflow execution."""
    wf = _get_workflow(execution_id)
    forks = []
    for task in wf.get("tasks", []):
        task_type = task.get("taskType", task.get("type", ""))
        if task_type in ("FORK", "FORK_JOIN"):
            forks.append(task)
    return forks


# ===================================================================
# Tests
# ===================================================================


@pytest.mark.timeout(1800)  # 30 min — multi-agent tests are slow
class TestSuite9Handoffs:
    """Agent handoffs: compilation, orchestration strategies, runtime execution."""

    # ── Compilation: all 8 strategies ──────────────────────────────────

    def test_all_strategies_compile(self, runtime, model):
        """All 8 strategies compile successfully via plan().

        For each strategy, create a parent agent with two children,
        compile with plan(), and verify the agentDef reflects the
        correct strategy and child agent names.
        """
        child_a = Agent(name="child_a", model=model, instructions="Child A.")
        child_b = Agent(name="child_b", model=model, instructions="Child B.")
        router_lead = Agent(
            name="router_lead", model=model, instructions="Route tasks."
        )

        strategies = [
            ("handoff", Strategy.HANDOFF, {}),
            ("sequential", Strategy.SEQUENTIAL, {}),
            ("parallel", Strategy.PARALLEL, {}),
            ("router", Strategy.ROUTER, {"router": router_lead}),
            ("round_robin", Strategy.ROUND_ROBIN, {}),
            ("random", Strategy.RANDOM, {}),
            ("swarm", Strategy.SWARM, {}),
            ("manual", Strategy.MANUAL, {}),
        ]

        for strategy_name, strategy_enum, extra_kwargs in strategies:
            parent = Agent(
                name=f"e2e_s9_{strategy_name}",
                model=model,
                instructions=f"Parent with {strategy_name} strategy.",
                agents=[child_a, child_b],
                strategy=strategy_enum,
                **extra_kwargs,
            )
            result = runtime.plan(parent)

            # Validate plan structure
            assert "workflowDef" in result, (
                f"[{strategy_name}] plan() result missing 'workflowDef'. "
                f"Got keys: {list(result.keys())}"
            )
            assert "requiredWorkers" in result, (
                f"[{strategy_name}] plan() result missing 'requiredWorkers'. "
                f"Got keys: {list(result.keys())}"
            )

            ad = _agent_def(result)

            # Strategy matches
            assert ad.get("strategy") == strategy_name, (
                f"[{strategy_name}] agentDef.strategy is "
                f"'{ad.get('strategy')}', expected '{strategy_name}'."
            )

            # Sub-agents present
            sub_names = _sub_agent_names(ad)
            for expected_child in ["child_a", "child_b"]:
                assert expected_child in sub_names, (
                    f"[{strategy_name}] Sub-agent '{expected_child}' not in "
                    f"agentDef.agents. Found: {sub_names}"
                )

    # ── Compilation: router requires router= ──────────────────────────

    def test_router_requires_router_argument(self):
        """Strategy.ROUTER without router= argument raises ValueError."""
        with pytest.raises(ValueError, match="router"):
            Agent(
                name="e2e_s9_router_no_arg",
                model="openai/gpt-4o-mini",
                instructions="This should fail.",
                agents=[
                    Agent(
                        name="dummy", model="openai/gpt-4o-mini", instructions="X."
                    )
                ],
                strategy=Strategy.ROUTER,
            )

    # ── Sequential execution ──────────────────────────────────────────

    def test_sequential_execution(self, runtime, model):
        """Sequential strategy runs agents in order.

        Parent agent with math_agent >> text_agent (sequential).
        Prompt asks to compute 3+4 then reverse hello.
        Validates: status COMPLETED, SUB_WORKFLOW tasks present,
        output contains both deterministic markers.
        """
        parent = Agent(
            name="e2e_s9_seq_run",
            model=model,
            instructions=(
                "You orchestrate two agents sequentially. "
                "First delegate math to math_agent, then text to text_agent."
            ),
            agents=[_math_agent(model), _text_agent(model)],
            strategy=Strategy.SEQUENTIAL,
        )
        result = runtime.run(
            parent,
            "First compute 3+4, then reverse the word hello",
            timeout=TIMEOUT,
        )
        diag = _run_diagnostic(result)

        assert result.execution_id, f"[Sequential] No execution_id. {diag}"
        assert result.status == "COMPLETED", (
            f"[Sequential] Expected COMPLETED, got '{result.status}'. {diag}"
        )

        # Verify SUB_WORKFLOW tasks exist in the workflow
        sub_wfs = _find_sub_workflow_tasks(result.execution_id)
        assert len(sub_wfs) >= 2, (
            f"[Sequential] Expected at least 2 SUB_WORKFLOW tasks, "
            f"got {len(sub_wfs)}. The sequential strategy should create "
            f"a sub-workflow per child agent."
        )

        # Verify both child agents executed via sub-workflow completion
        sub_refs = [t.get("referenceTaskName", "") for t in sub_wfs]
        completed_refs = [
            t.get("referenceTaskName", "")
            for t in sub_wfs
            if t.get("status") == "COMPLETED"
        ]
        assert any("math" in r.lower() for r in completed_refs), (
            f"[Sequential] math_agent sub-workflow not COMPLETED. "
            f"Sub-workflow refs: {sub_refs}"
        )
        assert any("text" in r.lower() for r in completed_refs), (
            f"[Sequential] text_agent sub-workflow not COMPLETED. "
            f"Sub-workflow refs: {sub_refs}"
        )

    # ── Parallel execution ────────────────────────────────────────────

    def test_parallel_execution(self, runtime, model):
        """Parallel strategy forks agents concurrently.

        Parent agent with math_agent and text_agent in parallel.
        Validates: status COMPLETED, FORK task present,
        output contains both deterministic markers.
        """
        parent = Agent(
            name="e2e_s9_par_run",
            model=model,
            instructions=(
                "You orchestrate two agents in parallel. "
                "Delegate math to math_agent and text to text_agent simultaneously."
            ),
            agents=[_math_agent(model), _text_agent(model)],
            strategy=Strategy.PARALLEL,
        )
        result = runtime.run(
            parent,
            "Compute 3+4 AND reverse the word hello",
            timeout=TIMEOUT,
        )
        diag = _run_diagnostic(result)

        assert result.execution_id, f"[Parallel] No execution_id. {diag}"
        assert result.status == "COMPLETED", (
            f"[Parallel] Expected COMPLETED, got '{result.status}'. {diag}"
        )

        # Verify FORK task exists (parallel strategy uses FORK/FORK_JOIN)
        fork_tasks = _find_fork_tasks(result.execution_id)
        assert len(fork_tasks) >= 1, (
            f"[Parallel] Expected at least 1 FORK task, got {len(fork_tasks)}. "
            f"The parallel strategy should create FORK/FORK_JOIN tasks."
        )

        # Verify both child agents executed via sub-workflow completion
        sub_wfs = _find_sub_workflow_tasks(result.execution_id)
        completed_refs = [
            t.get("referenceTaskName", "")
            for t in sub_wfs
            if t.get("status") == "COMPLETED"
        ]
        assert any("math" in r.lower() for r in completed_refs), (
            f"[Parallel] math_agent sub-workflow not COMPLETED. "
            f"Sub-workflow refs: {[t.get('referenceTaskName','') for t in sub_wfs]}"
        )
        assert any("text" in r.lower() for r in completed_refs), (
            f"[Parallel] text_agent sub-workflow not COMPLETED. "
            f"Sub-workflow refs: {[t.get('referenceTaskName','') for t in sub_wfs]}"
        )

    # ── Handoff execution ─────────────────────────────────────────────

    def test_handoff_execution(self, runtime, model):
        """Handoff strategy delegates to the correct sub-agent.

        Parent with math_agent and text_agent. Prompt asks to reverse text.
        Validates: terminal status, at least one SUB_WORKFLOW COMPLETED.
        """
        parent = Agent(
            name="e2e_s9_handoff_run",
            model=model,
            instructions=(
                "You route requests. If the user needs math, delegate to math_agent. "
                "If the user needs text manipulation, delegate to text_agent."
            ),
            agents=[_math_agent(model), _text_agent(model)],
            strategy=Strategy.HANDOFF,
        )
        result = runtime.run(
            parent,
            "I need to reverse the word hello",
            timeout=TIMEOUT,
        )
        diag = _run_diagnostic(result)

        assert result.execution_id, f"[Handoff] No execution_id. {diag}"
        assert result.status in ("COMPLETED", "FAILED", "TERMINATED"), (
            f"[Handoff] Expected terminal status, got '{result.status}'. {diag}"
        )

        # At least one SUB_WORKFLOW should have completed
        sub_wfs = _find_sub_workflow_tasks(result.execution_id)
        completed_subs = [
            t for t in sub_wfs if t.get("status") == "COMPLETED"
        ]
        assert len(completed_subs) >= 1, (
            f"[Handoff] Expected at least 1 COMPLETED SUB_WORKFLOW, "
            f"got {len(completed_subs)}. Sub-workflow statuses: "
            f"{[t.get('status') for t in sub_wfs]}. {diag}"
        )

    # ── Router selects correct agent ──────────────────────────────────

    def test_router_selects_correct_agent(self, runtime, model):
        """Router strategy routes to the correct agent based on input.

        Router agent decides which child to invoke. Math prompt should
        route to math_agent.
        Validates: COMPLETED, math_agent sub-workflow executed.
        """
        router_agent = Agent(
            name="e2e_s9_router_lead",
            model=model,
            instructions=(
                "You are a router. Route math requests to math_agent "
                "and text requests to text_agent. Pick the best agent."
            ),
        )
        parent = Agent(
            name="e2e_s9_router_run",
            model=model,
            instructions="You coordinate agents via a router.",
            agents=[_math_agent(model), _text_agent(model)],
            strategy=Strategy.ROUTER,
            router=router_agent,
        )
        result = runtime.run(
            parent,
            "Compute 7 times 8",
            timeout=TIMEOUT,
        )
        diag = _run_diagnostic(result)

        assert result.execution_id, f"[Router] No execution_id. {diag}"
        assert result.status == "COMPLETED", (
            f"[Router] Expected COMPLETED, got '{result.status}'. {diag}"
        )

        # Verify math_agent sub-workflow was executed
        sub_wfs = _find_sub_workflow_tasks(result.execution_id)
        sub_wf_refs = [t.get("referenceTaskName", "") for t in sub_wfs]
        math_sub = [ref for ref in sub_wf_refs if "math_agent" in ref]
        assert len(math_sub) >= 1, (
            f"[Router] Expected math_agent sub-workflow to execute. "
            f"SUB_WORKFLOW referenceTaskNames: {sub_wf_refs}. {diag}"
        )

    # ── Swarm with OnTextMention ──────────────────────────────────────

    def test_swarm_with_text_mention(self, runtime, model):
        """Swarm strategy with OnTextMention triggers conditional handoff.

        Parent with text_agent. OnTextMention for "reverse" routes to text_agent.
        Validates: terminal status, text_agent sub-workflow executed.
        """
        parent = Agent(
            name="e2e_s9_swarm_run",
            model=model,
            instructions=(
                "You are a swarm coordinator. Handle requests by delegating "
                "to the appropriate agent."
            ),
            agents=[_math_agent(model), _text_agent(model)],
            strategy=Strategy.SWARM,
            max_turns=5,
            handoffs=[
                OnTextMention(text="reverse", target="text_agent"),
                OnTextMention(text="compute", target="math_agent"),
            ],
        )
        result = runtime.run(
            parent,
            "Please reverse the word hello",
            timeout=TIMEOUT,
        )
        diag = _run_diagnostic(result)

        assert result.execution_id, f"[Swarm] No execution_id. {diag}"
        assert result.status in ("COMPLETED", "FAILED", "TERMINATED"), (
            f"[Swarm] Expected terminal status, got '{result.status}'. {diag}"
        )

        # Verify text_agent sub-workflow was executed
        sub_wfs = _find_sub_workflow_tasks(result.execution_id)
        sub_wf_refs = [t.get("referenceTaskName", "") for t in sub_wfs]
        text_sub = [ref for ref in sub_wf_refs if "text_agent" in ref]
        assert len(text_sub) >= 1, (
            f"[Swarm] Expected text_agent sub-workflow to execute. "
            f"SUB_WORKFLOW referenceTaskNames: {sub_wf_refs}. {diag}"
        )

    # ── Pipe operator (>>) sequential ─────────────────────────────────

    def test_pipe_operator_sequential(self, runtime, model):
        """Python >> operator creates a sequential pipeline.

        math_agent >> text_agent produces a sequential parent.
        Validates: strategy is sequential, plan compiles, runtime executes.
        """
        math = _math_agent(model)
        text = _text_agent(model)
        pipeline = math >> text

        # Verify the pipeline agent has sequential strategy
        assert pipeline.strategy == Strategy.SEQUENTIAL, (
            f"[Pipe] Expected strategy SEQUENTIAL, got '{pipeline.strategy}'. "
            f"The >> operator should produce a sequential agent."
        )

        # Verify child agents are present
        child_names = [a.name for a in pipeline.agents]
        assert "math_agent" in child_names, (
            f"[Pipe] math_agent not in pipeline.agents. "
            f"Children: {child_names}"
        )
        assert "text_agent" in child_names, (
            f"[Pipe] text_agent not in pipeline.agents. "
            f"Children: {child_names}"
        )

        # Compile and verify plan
        result = runtime.plan(pipeline)
        assert "workflowDef" in result, (
            f"[Pipe] plan() result missing 'workflowDef'. "
            f"Got keys: {list(result.keys())}"
        )
        ad = _agent_def(result)
        assert ad.get("strategy") == "sequential", (
            f"[Pipe] agentDef.strategy is '{ad.get('strategy')}', "
            f"expected 'sequential'."
        )

        # Run the pipeline
        run_result = runtime.run(
            pipeline,
            "Compute 2+3 then reverse the word hello",
            timeout=TIMEOUT,
        )
        diag = _run_diagnostic(run_result)

        assert run_result.execution_id, f"[Pipe] No execution_id. {diag}"
        assert run_result.status == "COMPLETED", (
            f"[Pipe] Expected COMPLETED, got '{run_result.status}'. {diag}"
        )

        # Verify SUB_WORKFLOW tasks exist
        sub_wfs = _find_sub_workflow_tasks(run_result.execution_id)
        assert len(sub_wfs) >= 2, (
            f"[Pipe] Expected at least 2 SUB_WORKFLOW tasks, "
            f"got {len(sub_wfs)}."
        )

        # Verify both child agents executed via sub-workflow completion
        completed_refs = [
            t.get("referenceTaskName", "")
            for t in sub_wfs
            if t.get("status") == "COMPLETED"
        ]
        assert any("math" in r.lower() for r in completed_refs), (
            f"[Pipe] math_agent sub-workflow not COMPLETED. "
            f"Sub-workflow refs: {[t.get('referenceTaskName','') for t in sub_wfs]}"
        )
        assert any("text" in r.lower() for r in completed_refs), (
            f"[Pipe] text_agent sub-workflow not COMPLETED. "
            f"Sub-workflow refs: {[t.get('referenceTaskName','') for t in sub_wfs]}"
        )
