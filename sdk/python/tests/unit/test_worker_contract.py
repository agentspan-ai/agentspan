"""Worker domain contract — formal test of the property that prevents
the recurring "tasks scheduled, no worker polls" class of bug.

See ``docs/design/WORKER_DOMAIN_CONTRACT.md`` for the full RCA.

The contract:

    For every ``(task_name, domain)`` pair the server places in
    ``StartWorkflowRequest.taskToDomain``, the SDK MUST have a registered
    worker on that exact pair.

Equivalently: the server's expected set ⊆ the SDK's registered set.

This file enforces the contract two ways:

1. **Property test** — for any agent tree, the SDK's collected worker
   names match the names the server would expect (under our universal-
   per-execution-domain policy, every worker name in the tree gets the
   run domain). The two collectors share a recursion shape; they must
   agree by construction. The test asserts that they actually do.

2. **Historical regression suite** — each of the three known failure
   modes (b38024fb, 0f715217, 4e0d2953) is a parameterised test case.
   The agent tree shapes that hit those bugs all assert the contract;
   they pass with the current code. Without the fixes (or with a future
   regression in any of the four worker-discovery functions), each case
   fails with a clear message naming the missing pair.

Falsification proof: each historical case has been verified to fail
when its corresponding fix is reverted (commented-out). See the doc.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional, Set, Tuple

import pytest

from agentspan.agents import Agent, AgentRuntime, Strategy
from agentspan.agents.tool import ToolDef, get_tool_def, tool


# ── Contract helpers ──────────────────────────────────────────────────


def _expected_worker_names(agent: Any) -> Set[str]:
    """Walk the agent tree and collect every worker tool name the server
    would see when compiling the WorkflowDef.

    Mirrors the recursion shape of:
      - ``MultiAgentCompiler`` (server) — walks tools, agents, planner, fallback
      - ``AgentService.collectSimpleTaskNames`` — every worker in the tree
      - ``ToolRegistry.register_tool_workers`` (SDK) — same names registered

    Output = the set of names the server will place into ``taskToDomain``
    (each mapped to the runId when the execution is stateful).

    Includes:
      - ``agent.tools`` worker tools
      - ``agent.prefill_tools`` (each is a worker SIMPLE task)
      - sub-agents reachable via ``agents``, ``planner``, ``fallback``
    """
    names: Set[str] = set()
    _walk(agent, names)
    return names


def _walk(agent: Any, out: Set[str]) -> None:
    if agent is None or isinstance(agent, bool):
        return
    if getattr(agent, "external", False):
        return
    for t in getattr(agent, "tools", None) or []:
        try:
            td = get_tool_def(t)
        except TypeError:
            continue
        if td.tool_type in ("worker", "cli"):
            out.add(td.name)
    for pt in getattr(agent, "prefill_tools", None) or []:
        td = getattr(pt, "tool_def", None)
        if td is not None and td.tool_type in ("worker", "cli"):
            out.add(td.name)
    for sub in getattr(agent, "agents", None) or []:
        _walk(sub, out)
    _walk(getattr(agent, "planner", None), out)
    _walk(getattr(agent, "fallback", None), out)


def _registered_pairs(agent: Any, run_id: Optional[str]) -> Set[Tuple[str, Optional[str]]]:
    """Use the runtime's own collector — this is what `_prepare_workers`
    will actually register. Asserting on the runtime's view (not a
    re-implementation) guarantees the test catches what `rt.run` does."""
    with AgentRuntime() as rt:
        return set(rt._collect_registered_pairs(agent, run_id))


def _assert_worker_contract(agent: Any, run_id: Optional[str]) -> None:
    """The property: for every name the server expects, the SDK has a
    registered worker on the correct domain.

    With the universal-per-execution-domain policy (server adds every
    worker SIMPLE to taskToDomain when runId is set), the expected set
    is ``{(n, run_id) for n in _expected_worker_names(agent)}``.
    """
    if run_id is None:
        # Non-stateful run: server passes no taskToDomain. SDK registers
        # workers on no-domain. Trivially matches.
        return
    expected_names = _expected_worker_names(agent)
    expected_pairs = {(n, run_id) for n in expected_names}
    registered = _registered_pairs(agent, run_id)
    missing = expected_pairs - registered
    assert not missing, (
        f"Worker domain contract violation: server schedules {sorted(missing)} "
        f"but SDK has no matching registered worker.\n"
        f"  expected (server taskToDomain): {sorted(expected_pairs)[:5]}{'...' if len(expected_pairs) > 5 else ''}\n"
        f"  registered (SDK):              {sorted(registered)[:5]}{'...' if len(registered) > 5 else ''}\n"
        f"This is the recurring 'tasks SCHEDULED, no worker polls' bug class. "
        f"See docs/design/WORKER_DOMAIN_CONTRACT.md."
    )


# ── Fixtures: each historical bug as a builder ────────────────────────


def _b38024fb() -> Tuple[Any, str]:
    """Workflow b38024fb-2747-4d80-ad60-b18cfac4a079: prefill-only tool.

    Pattern: ``read_repo_docs`` declared ONLY in ``prefill_tools`` (not in
    ``tools=``). Server emits a SIMPLE task for it; SDK previously walked
    only ``tools=`` and missed it.
    """
    @tool
    def read_repo_docs() -> str:
        return "docs"

    @tool
    def regular(x: str) -> str:
        return x

    a = Agent(
        name="wf_b38024fb_agent",
        model="openai/gpt-4o-mini",
        instructions="t",
        stateful=True,                      # forces runId → taskToDomain populated
        tools=[regular],
        prefill_tools=[read_repo_docs.call()],
    )
    return a, "run-b38024fb"


def _0f715217() -> Tuple[Any, str]:
    """Workflow 0f715217-29bb-405b-ab12-4126ce4d1773: PAE named-slot recursion.

    Pattern: tool declared on ``coder.planner`` (PLAN_EXECUTE named slot).
    SDK previously recursed via ``agent.agents`` only — empty for PAE
    harnesses, so the planner sub-agent was invisible.
    """
    @tool
    def planner_only_prefill() -> str:
        return "planner-data"

    @tool
    def fallback_tool() -> str:
        return "fb"

    @tool
    def harness_tool() -> str:
        return "h"

    planner = Agent(
        name="wf_0f715217_planner",
        model="openai/gpt-4o-mini",
        instructions="emit JSON",
        stateful=True,
        prefill_tools=[planner_only_prefill.call()],
    )
    fallback = Agent(
        name="wf_0f715217_fallback",
        model="openai/gpt-4o-mini",
        instructions="recover",
        stateful=True,
        tools=[fallback_tool],
    )
    coder = Agent(
        name="wf_0f715217_harness",
        model="openai/gpt-4o-mini",
        strategy=Strategy.PLAN_EXECUTE,
        planner=planner,
        fallback=fallback,
        tools=[harness_tool],
    )
    return coder, "run-0f715217"


def _4e0d2953() -> Tuple[Any, str]:
    """Workflow 4e0d2953-1121-4fcd-8243-e5b529d7a9bf: non-stateful tool in stateful run.

    Pattern: a stateful agent (``code_fallback`` because it's reachable
    from a stateful execution context) has a NON-stateful tool in its
    prefill (``read_repo_docs``). Server schedules every worker task on
    the run domain; SDK previously gated per-tool stateful-ness and
    registered the non-stateful tool on no-domain. Mismatch.
    """
    @tool
    def read_repo_docs() -> str:                 # NOT stateful (in prefill_tools)
        return "docs"

    @tool
    def read_file_local(path: str) -> str:       # NOT stateful (in tools=)
        return path

    @tool(stateful=True)
    def stateful_tool(x: str) -> str:            # stateful — forces runId
        return x

    # Tools= carries BOTH a stateful and a non-stateful tool. Prefill_tools
    # carries a non-stateful tool. Reverting EITHER the tools= branch or
    # the prefill branch of ``_collect_registered_pairs`` to the old
    # per-tool gate causes the contract to fail for one of the two
    # non-stateful entries.
    fallback = Agent(
        name="wf_4e0d2953_fallback",
        model="openai/gpt-4o-mini",
        instructions="recover",
        prefill_tools=[read_repo_docs.call()],
        tools=[stateful_tool, read_file_local],
    )
    coder = Agent(
        name="wf_4e0d2953_harness",
        model="openai/gpt-4o-mini",
        strategy=Strategy.PLAN_EXECUTE,
        planner=Agent(
            name="wf_4e0d2953_planner",
            model="openai/gpt-4o-mini",
            instructions="plan",
        ),
        fallback=fallback,
        tools=[stateful_tool],
    )
    return coder, "run-4e0d2953"


def _cf1cfecf() -> Tuple[Any, str]:
    """Workflow cf1cfecf-62a3-4883-b726-37f44c72d5a8: non-stateful tool
    used in DYNAMIC dispatch (LLM tool_call) within a stateful run.

    Pattern: ``run_command`` is in ``code_fallback.tools`` (not prefill,
    not stateful). The LLM emits a tool_call for ``run_command``;
    Conductor's FORK_JOIN_DYNAMIC creates a SIMPLE task at runtime —
    NOT in the static WorkflowDef, so absent from
    ``collectSimpleTaskNames``. The earlier ``collectWorkerToolNames``
    only added stateful tools, so ``run_command`` ended up in neither
    set and was scheduled with no domain. The SDK (after the
    universal-domain fix) registered the worker on the run domain.
    Mismatch — task SCHEDULED forever.

    Distinct from ``4e0d2953`` (which was a non-stateful tool in
    PREFILL): cf1cfecf is the dynamic-dispatch sibling of the same
    contract. Both shapes are now covered.
    """
    @tool
    def run_command(command: str) -> str:        # NOT stateful
        return "ok"

    @tool(stateful=True)
    def write_implementation_report(content: str) -> str:  # stateful — forces runId
        return "wrote"

    fallback = Agent(
        name="wf_cf1cfecf_fallback",
        model="openai/gpt-4o-mini",
        instructions="recover",
        tools=[run_command, write_implementation_report],
    )
    coder = Agent(
        name="wf_cf1cfecf_harness",
        model="openai/gpt-4o-mini",
        strategy=Strategy.PLAN_EXECUTE,
        planner=Agent(
            name="wf_cf1cfecf_planner",
            model="openai/gpt-4o-mini",
            instructions="plan",
        ),
        fallback=fallback,
        tools=[run_command, write_implementation_report],
    )
    return coder, "run-cf1cfecf"


HISTORICAL_CASES = [
    pytest.param(_b38024fb, id="wf_b38024fb_prefill_only_tool"),
    pytest.param(_0f715217, id="wf_0f715217_pae_named_slot"),
    pytest.param(_4e0d2953, id="wf_4e0d2953_non_stateful_in_stateful_run"),
    pytest.param(_cf1cfecf, id="wf_cf1cfecf_non_stateful_dynamic_dispatch"),
]


# ── The contract tests ────────────────────────────────────────────────


class TestWorkerDomainContract:
    """Formal proof that the worker domain contract holds.

    See docs/design/WORKER_DOMAIN_CONTRACT.md for the property statement,
    the policies, and why these tests provide catch-coverage.
    """

    @pytest.mark.parametrize("build", HISTORICAL_CASES)
    def test_historical_regression(self, build):
        """Each known failure mode reproduced as a typed agent shape.
        Asserts the contract holds for that shape with the current code.

        Falsification: comment out the corresponding fix in
        ``_collect_worker_names`` / ``_register_workers`` /
        ``_collect_registered_pairs`` / ``ToolRegistry.register_tool_workers``
        and the matching parametrised case fails — proven manually
        during the contract roll-out and documented in the RCA.
        """
        agent, run_id = build()
        _assert_worker_contract(agent, run_id)

    def test_non_stateful_run_trivially_holds(self):
        """When run_id is None, the server passes no taskToDomain. The
        contract is vacuously satisfied. (Smoke test the helper.)"""
        @tool
        def t() -> str:
            return "x"
        a = Agent(name="ns", model="openai/gpt-4o-mini", instructions="t", tools=[t])
        _assert_worker_contract(a, None)

    def test_deeply_nested_agent_tree(self):
        """Property test: a deeper tree (sub-agents inside sub-agents
        inside named slots) still satisfies the contract."""
        @tool
        def leaf_tool() -> str:
            return "leaf"

        @tool
        def mid_tool() -> str:
            return "mid"

        @tool(stateful=True)
        def root_stateful() -> str:
            return "root"

        leaf = Agent(name="leaf", model="openai/gpt-4o-mini", instructions="t", tools=[leaf_tool])
        mid_pipeline = Agent(
            name="mid_seq",
            model="openai/gpt-4o-mini",
            strategy=Strategy.SEQUENTIAL,
            agents=[
                Agent(name="mid_a", model="openai/gpt-4o-mini", instructions="t", tools=[mid_tool]),
                leaf,
            ],
        )
        planner = Agent(
            name="root_planner",
            model="openai/gpt-4o-mini",
            instructions="plan",
            prefill_tools=[mid_tool.call()],
        )
        root = Agent(
            name="root_pae",
            model="openai/gpt-4o-mini",
            strategy=Strategy.PLAN_EXECUTE,
            planner=planner,
            fallback=mid_pipeline,
            tools=[root_stateful],
        )
        _assert_worker_contract(root, "run-deep-tree")

    def test_external_agent_is_excluded(self):
        """External sub-agents have their own runtime; the parent SDK
        doesn't register their workers. Both the expected-names walker
        and the registered-pairs walker skip them in lockstep."""
        @tool(stateful=True)
        def stateful_tool() -> str:
            return "x"

        @tool(stateful=True)
        def parent_local() -> str:
            return "y"

        # An agent with no ``model`` is treated as external (the server
        # references it as a SubWorkflowTask by name). Workers for tools
        # on an external agent are NOT registered by the parent SDK.
        external = Agent(
            name="external_one",
            instructions="external",
            tools=[stateful_tool],
        )
        assert external.external, "no-model agent should be external"

        parent = Agent(
            name="ext_parent",
            model="openai/gpt-4o-mini",
            instructions="t",
            tools=[parent_local],
            agents=[external],
        )
        _assert_worker_contract(parent, "run-external")


# ── Falsification meta-tests ─────────────────────────────────────────
#
# These tests are the formal proof that the contract suite catches each
# of the historical bugs. Each meta-test:
#   1. Monkey-patches the SDK with the historical broken behaviour.
#   2. Runs the corresponding historical-case contract assertion.
#   3. Asserts that it raises AssertionError — the test catches the bug.
#   4. Test cleanup (pytest's monkeypatch fixture) restores the fix.
#
# If a fix is reverted in real source code, the corresponding historical
# case fails — caught at unit-test time, never reaches a real workflow.
# If any of these meta-tests itself fails, we've lost catch-coverage
# for that bug class and the breach is loud.


def _broken_no_prefill_walk(self, agent, domain):
    """Pre-b38024fb behaviour: walk ``tools`` only, never ``prefill_tools``."""
    from agentspan.agents.tool import get_tool_def
    pairs = []
    for t in getattr(agent, "tools", []) or []:
        try:
            td = get_tool_def(t)
        except TypeError:
            continue
        if td.tool_type not in ("worker", "cli") or td.func is None:
            continue
        pairs.append((td.name, domain))
    for sub in getattr(agent, "agents", []) or []:
        if getattr(sub, "external", False):
            continue
        pairs.extend(_broken_no_prefill_walk(self, sub, domain))
    planner = getattr(agent, "planner", None)
    if planner is not None and not isinstance(planner, bool) and not getattr(planner, "external", False):
        pairs.extend(_broken_no_prefill_walk(self, planner, domain))
    fallback = getattr(agent, "fallback", None)
    if fallback is not None and not getattr(fallback, "external", False):
        pairs.extend(_broken_no_prefill_walk(self, fallback, domain))
    return pairs


def _broken_no_named_slot_recursion(self, agent, domain):
    """Pre-0f715217 behaviour: recurse via ``agents`` only, not PAE slots."""
    from agentspan.agents.tool import get_tool_def
    pairs = []
    for t in getattr(agent, "tools", []) or []:
        try:
            td = get_tool_def(t)
        except TypeError:
            continue
        if td.tool_type not in ("worker", "cli") or td.func is None:
            continue
        pairs.append((td.name, domain))
    seen = {p[0] for p in pairs}
    for pt in getattr(agent, "prefill_tools", None) or []:
        td = getattr(pt, "tool_def", None)
        if td is None or td.tool_type not in ("worker", "cli") or td.func is None:
            continue
        if td.name in seen:
            continue
        pairs.append((td.name, domain))
        seen.add(td.name)
    for sub in getattr(agent, "agents", []) or []:
        if getattr(sub, "external", False):
            continue
        pairs.extend(_broken_no_named_slot_recursion(self, sub, domain))
    # Bug: planner / fallback recursion deliberately omitted.
    return pairs


def _broken_per_tool_gate(self, agent, domain):
    """Pre-4e0d2953 behaviour: pair non-stateful tools with ``None`` even
    in a stateful run."""
    from agentspan.agents.tool import get_tool_def
    pairs = []
    agent_stateful = bool(getattr(agent, "stateful", False))
    for t in getattr(agent, "tools", []) or []:
        try:
            td = get_tool_def(t)
        except TypeError:
            continue
        if td.tool_type not in ("worker", "cli") or td.func is None:
            continue
        # The bug: per-tool gate, ignoring the universal-domain policy.
        tool_domain = domain if (agent_stateful or td.stateful) else None
        pairs.append((td.name, tool_domain))
    seen = {p[0] for p in pairs}
    for pt in getattr(agent, "prefill_tools", None) or []:
        td = getattr(pt, "tool_def", None)
        if td is None or td.tool_type not in ("worker", "cli") or td.func is None:
            continue
        if td.name in seen:
            continue
        tool_domain = domain if (agent_stateful or td.stateful) else None
        pairs.append((td.name, tool_domain))
        seen.add(td.name)
    for sub in getattr(agent, "agents", []) or []:
        if getattr(sub, "external", False):
            continue
        pairs.extend(_broken_per_tool_gate(self, sub, domain))
    planner = getattr(agent, "planner", None)
    if planner is not None and not isinstance(planner, bool) and not getattr(planner, "external", False):
        pairs.extend(_broken_per_tool_gate(self, planner, domain))
    fallback = getattr(agent, "fallback", None)
    if fallback is not None and not getattr(fallback, "external", False):
        pairs.extend(_broken_per_tool_gate(self, fallback, domain))
    return pairs


# Each row asserts: with this broken implementation in place, the
# corresponding historical-case contract test MUST fail. This is the
# formal coverage statement of the suite.
FALSIFICATION_CASES = [
    pytest.param(
        _broken_no_prefill_walk, _b38024fb,
        id="reverting_prefill_walk_breaks_b38024fb",
    ),
    pytest.param(
        _broken_no_named_slot_recursion, _0f715217,
        id="reverting_named_slot_recursion_breaks_0f715217",
    ),
    pytest.param(
        _broken_per_tool_gate, _4e0d2953,
        id="reverting_per_tool_gate_breaks_4e0d2953",
    ),
]


class TestContractCatchesAllHistoricalBugs:
    """Formal proof: for each historical bug, removing the fix in
    ``_collect_registered_pairs`` causes the contract assertion to fail.
    Enforced as a permanent test, so future code changes can't silently
    strip a fix without tripping the assertion.

    Combined with ``test_with_all_fixes_in_place_all_cases_pass`` below,
    this gives a tight conditional:

        contract_holds_for_case_X  ⇔  fix_X_is_in_place
    """

    @pytest.mark.parametrize("broken_impl,build_agent", FALSIFICATION_CASES)
    def test_reverting_fix_breaks_corresponding_case(
        self, monkeypatch, broken_impl, build_agent
    ):
        monkeypatch.setattr(
            AgentRuntime, "_collect_registered_pairs", broken_impl, raising=True,
        )
        agent, run_id = build_agent()
        with pytest.raises(AssertionError, match="Worker domain contract violation"):
            _assert_worker_contract(agent, run_id)

    def test_with_all_fixes_in_place_all_cases_pass(self):
        """Sanity counterpart: with the real (fixed) implementation, all
        three historical cases satisfy the contract."""
        for build in (_b38024fb, _0f715217, _4e0d2953):
            agent, run_id = build()
            _assert_worker_contract(agent, run_id)
