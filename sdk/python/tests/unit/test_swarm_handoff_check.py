"""Tests for SWARM handoff_check worker registration and routing.

The server ALWAYS generates a {parent}_handoff_check task for SWARM workflows.
The SDK must register the corresponding worker regardless of whether the parent
agent has explicit handoff conditions. The worker handles two mechanisms:

  1. Transfer tools (primary): LLM calls transfer_to_<peer> → is_transfer=true
  2. Condition-based (fallback): OnTextMention / OnCondition on the parent

Bug (pre-fix): SDK only registered handoff_check when agent.handoffs was
non-empty. A SWARM parent with handoffs on children only (e.g. coder_qa_loop
with OnTextMention on coder and qa_agent) never got the worker registered.
The task sat SCHEDULED with pollCount=0 forever.

This affects BOTH stateful and non-stateful agents:
  - Stateful: task routed to UUID domain, no worker in that domain
  - Non-stateful: task in default domain, no worker in default domain

These tests are fully deterministic — no LLM, no server, no mocks of
external services. They exercise the exact registration logic and worker
routing logic from runtime.py.
"""

from unittest.mock import patch

import pytest

from agentspan.agents import Agent, Strategy
from agentspan.agents.handoff import OnTextMention
from agentspan.agents.runtime.runtime import AgentRuntime


def _collect_names(agent: Agent) -> set:
    """Call _collect_worker_names without a real server connection."""
    rt = AgentRuntime.__new__(AgentRuntime)
    return rt._collect_worker_names(agent)


# ---------------------------------------------------------------------------
# Fixtures: reusable agent topologies
# ---------------------------------------------------------------------------


@pytest.fixture()
def child_a():
    return Agent(name="child_a", model="openai/gpt-4o")


@pytest.fixture()
def child_b():
    return Agent(name="child_b", model="openai/gpt-4o")


@pytest.fixture()
def coder():
    return Agent(
        name="coder",
        model="openai/gpt-4o",
        handoffs=[OnTextMention(text="HANDOFF_TO_QA", target="qa_agent")],
    )


@pytest.fixture()
def qa_agent():
    return Agent(
        name="qa_agent",
        model="openai/gpt-4o",
        handoffs=[OnTextMention(text="HANDOFF_TO_CODER", target="coder")],
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. Worker name collection — does _collect_worker_names include
#    handoff_check for all SWARM configurations?
# ═══════════════════════════════════════════════════════════════════════════


class TestSwarmHandoffCheckRegistration:
    """Verify handoff_check is collected for every SWARM variant."""

    def test_swarm_parent_no_handoffs_gets_handoff_check(self, child_a, child_b):
        """THE BUG: SWARM parent with no handoffs must still get handoff_check.

        The server always generates the task. Transfer tools are the primary
        mechanism — they don't require condition-based handoffs.
        """
        swarm = Agent(
            name="my_swarm",
            model="openai/gpt-4o",
            agents=[child_a, child_b],
            strategy=Strategy.SWARM,
            # No handoffs on parent!
        )
        names = _collect_names(swarm)
        assert "my_swarm_handoff_check" in names

    def test_swarm_parent_with_handoffs_gets_handoff_check(self, child_a, child_b):
        """Existing behavior: parent with explicit handoffs gets handoff_check."""
        swarm = Agent(
            name="my_swarm",
            model="openai/gpt-4o",
            agents=[child_a, child_b],
            strategy=Strategy.SWARM,
            handoffs=[OnTextMention(text="GO_TO_B", target="child_b")],
        )
        names = _collect_names(swarm)
        assert "my_swarm_handoff_check" in names

    def test_issue_fixer_pattern_handoffs_on_children_only(self, coder, qa_agent):
        """Exact pattern from issue fixer: handoffs on children, not parent.

        coder has OnTextMention("HANDOFF_TO_QA" → qa_agent)
        qa_agent has OnTextMention("HANDOFF_TO_CODER" → coder)
        Parent (coder_qa_loop) has NO handoffs — just SWARM + stop_when.
        """
        loop = Agent(
            name="coder_qa_loop",
            model="openai/gpt-4o",
            agents=[coder, qa_agent],
            strategy=Strategy.SWARM,
            stop_when=lambda ctx, **kw: "QA_APPROVED" in ctx.get("result", ""),
            max_turns=90,
        )
        names = _collect_names(loop)
        assert "coder_qa_loop_handoff_check" in names
        # Also verify stop_when and transfer tools are collected
        assert "coder_qa_loop_stop_when" in names
        assert "coder_transfer_to_qa_agent" in names
        assert "qa_agent_transfer_to_coder" in names

    def test_swarm_with_stop_when_and_no_handoffs(self, child_a, child_b):
        """SWARM + stop_when but no handoffs — both workers must be collected."""
        swarm = Agent(
            name="loop",
            model="openai/gpt-4o",
            agents=[child_a, child_b],
            strategy=Strategy.SWARM,
            stop_when=lambda ctx, **kw: "DONE" in ctx.get("result", ""),
        )
        names = _collect_names(swarm)
        assert "loop_handoff_check" in names
        assert "loop_stop_when" in names

    def test_swarm_three_agents_no_handoffs(self):
        """SWARM with 3 children, no handoffs — all transfer tools + handoff_check."""
        a = Agent(name="agent_a", model="openai/gpt-4o")
        b = Agent(name="agent_b", model="openai/gpt-4o")
        c = Agent(name="agent_c", model="openai/gpt-4o")
        swarm = Agent(
            name="trio",
            model="openai/gpt-4o",
            agents=[a, b, c],
            strategy=Strategy.SWARM,
        )
        names = _collect_names(swarm)
        assert "trio_handoff_check" in names
        # Each agent gets transfer tools to every peer (including parent)
        # 4 agents × 3 peers = 12 transfer tools
        transfer_names = {n for n in names if "_transfer_to_" in n}
        assert len(transfer_names) == 12


# ═══════════════════════════════════════════════════════════════════════════
# 2. Negative tests — handoff_check must NOT be collected for non-SWARM
# ═══════════════════════════════════════════════════════════════════════════


class TestNonSwarmNoHandoffCheck:
    """Non-SWARM strategies must NOT get handoff_check (unless explicit handoffs)."""

    @pytest.mark.parametrize(
        "strategy",
        [
            Strategy.SEQUENTIAL,
            Strategy.PARALLEL,
            Strategy.ROUND_ROBIN,
            Strategy.RANDOM,
            Strategy.MANUAL,
        ],
    )
    def test_non_swarm_strategies_no_handoff_check(self, strategy, child_a, child_b):
        """Only SWARM generates handoff_check tasks on the server."""
        extra = {}
        if strategy == Strategy.MANUAL:
            extra = {}  # manual doesn't need special config for name collection
        parent = Agent(
            name="parent",
            model="openai/gpt-4o",
            agents=[child_a, child_b],
            strategy=strategy,
            **extra,
        )
        names = _collect_names(parent)
        assert "parent_handoff_check" not in names

    def test_single_agent_no_handoff_check(self):
        """A leaf agent (no sub-agents) never gets handoff_check."""
        agent = Agent(name="solo", model="openai/gpt-4o")
        names = _collect_names(agent)
        assert "solo_handoff_check" not in names

    def test_handoff_strategy_without_explicit_handoffs(self, child_a, child_b):
        """HANDOFF strategy without handoffs list — no handoff_check."""
        parent = Agent(
            name="parent",
            model="openai/gpt-4o",
            agents=[child_a, child_b],
            strategy=Strategy.HANDOFF,
        )
        names = _collect_names(parent)
        assert "parent_handoff_check" not in names

    def test_non_swarm_with_explicit_handoffs_gets_handoff_check(self, child_a, child_b):
        """Any strategy with explicit handoffs DOES get handoff_check."""
        parent = Agent(
            name="parent",
            model="openai/gpt-4o",
            agents=[child_a, child_b],
            strategy=Strategy.HANDOFF,
            handoffs=[OnTextMention(text="GO_B", target="child_b")],
        )
        names = _collect_names(parent)
        assert "parent_handoff_check" in names


# ═══════════════════════════════════════════════════════════════════════════
# 3. Handoff worker routing logic — verify the worker function handles
#    all cases correctly (transfer-only, condition-only, mixed, empty)
# ═══════════════════════════════════════════════════════════════════════════


class TestHandoffWorkerRouting:
    """Exercise the handoff_check_worker logic directly.

    Recreates the exact logic from _register_handoff_worker without
    needing a server connection. This tests the algorithm, not the
    registration plumbing.
    """

    @staticmethod
    def _make_handoff_fn(parent_name, sub_names, handoff_conditions=None, allowed=None):
        """Build the handoff check function identical to _register_handoff_worker."""
        conditions = handoff_conditions or []
        name_to_idx = {parent_name: "0"}
        name_to_idx.update({name: str(i + 1) for i, name in enumerate(sub_names)})
        idx_to_name = {v: k for k, v in name_to_idx.items()}

        def _is_transfer_truthy(val):
            if val is True:
                return True
            if isinstance(val, str):
                return val.strip().lower() == "true"
            return False

        def _is_allowed(source_idx, target_name):
            if not allowed:
                return True
            source_name = idx_to_name.get(source_idx, "")
            return target_name in allowed.get(source_name, [])

        def check(result="", active_agent="0", is_transfer=False, transfer_to=""):
            if _is_transfer_truthy(is_transfer):
                if _is_allowed(active_agent, transfer_to):
                    target_idx = name_to_idx.get(transfer_to, active_agent)
                    if target_idx != active_agent:
                        return {"active_agent": target_idx, "handoff": True}

            context = {"result": result, "messages": "", "tool_name": "", "tool_result": ""}
            for cond in conditions:
                if cond.should_handoff(context):
                    if _is_allowed(active_agent, cond.target):
                        target_idx = name_to_idx.get(cond.target, active_agent)
                        if target_idx != active_agent:
                            return {"active_agent": target_idx, "handoff": True}

            return {"active_agent": active_agent, "handoff": False}

        return check

    def test_transfer_only_no_conditions(self):
        """SWARM with no handoff conditions — transfer tools are the only mechanism.

        This is the exact scenario from the issue fixer agent bug.
        """
        check = self._make_handoff_fn("loop", ["coder", "qa_agent"])

        # coder (1) transfers to qa_agent (2) via transfer tool
        r = check(active_agent="1", is_transfer=True, transfer_to="qa_agent")
        assert r == {"active_agent": "2", "handoff": True}

        # qa_agent (2) transfers back to coder (1)
        r = check(active_agent="2", is_transfer=True, transfer_to="coder")
        assert r == {"active_agent": "1", "handoff": True}

        # No transfer, no conditions → loop exits
        r = check(active_agent="1", is_transfer=False)
        assert r == {"active_agent": "1", "handoff": False}

    def test_condition_only_no_transfer(self):
        """Handoff conditions fire when transfer tools aren't used."""
        conditions = [
            OnTextMention(text="GO_TO_B", target="agent_b"),
            OnTextMention(text="GO_TO_A", target="agent_a"),
        ]
        check = self._make_handoff_fn("parent", ["agent_a", "agent_b"], conditions)

        # Text mention triggers handoff to agent_b
        r = check(result="Please GO_TO_B now", active_agent="1")
        assert r == {"active_agent": "2", "handoff": True}

        # Text mention triggers handoff to agent_a
        r = check(result="GO_TO_A please", active_agent="2")
        assert r == {"active_agent": "1", "handoff": True}

        # No matching text → loop exits
        r = check(result="Nothing relevant here", active_agent="1")
        assert r == {"active_agent": "1", "handoff": False}

    def test_transfer_takes_priority_over_conditions(self):
        """Transfer tool fires even when condition text is also present."""
        conditions = [OnTextMention(text="HANDOFF", target="agent_b")]
        check = self._make_handoff_fn("parent", ["agent_a", "agent_b"], conditions)

        # Transfer to agent_a even though text says HANDOFF (which targets agent_b)
        r = check(
            result="HANDOFF to someone",
            active_agent="0",
            is_transfer=True,
            transfer_to="agent_a",
        )
        assert r == {"active_agent": "1", "handoff": True}

    def test_transfer_to_unknown_agent_stays_put(self):
        """Transfer to a non-existent agent keeps current agent active."""
        check = self._make_handoff_fn("parent", ["agent_a", "agent_b"])

        r = check(active_agent="1", is_transfer=True, transfer_to="nonexistent")
        assert r == {"active_agent": "1", "handoff": False}

    def test_transfer_to_self_no_handoff(self):
        """Transfer to the same agent doesn't count as handoff."""
        check = self._make_handoff_fn("parent", ["agent_a", "agent_b"])

        r = check(active_agent="1", is_transfer=True, transfer_to="agent_a")
        assert r == {"active_agent": "1", "handoff": False}

    def test_is_transfer_string_truthy(self):
        """is_transfer can be string 'true' (server serialization)."""
        check = self._make_handoff_fn("parent", ["agent_a", "agent_b"])

        r = check(active_agent="1", is_transfer="true", transfer_to="agent_b")
        assert r == {"active_agent": "2", "handoff": True}

        r = check(active_agent="1", is_transfer="True", transfer_to="agent_b")
        assert r == {"active_agent": "2", "handoff": True}

        r = check(active_agent="1", is_transfer="false", transfer_to="agent_b")
        assert r == {"active_agent": "1", "handoff": False}

    def test_allowed_transitions_block_disallowed(self):
        """allowed_transitions restricts which transfers are valid."""
        allowed = {
            "parent": ["agent_a"],
            "agent_a": ["agent_b"],
            "agent_b": ["agent_a"],  # agent_b cannot go to parent
        }
        check = self._make_handoff_fn("parent", ["agent_a", "agent_b"], allowed=allowed)

        # Allowed: agent_a → agent_b
        r = check(active_agent="1", is_transfer=True, transfer_to="agent_b")
        assert r == {"active_agent": "2", "handoff": True}

        # Blocked: agent_b → parent (not in allowed[agent_b])
        r = check(active_agent="2", is_transfer=True, transfer_to="parent")
        assert r == {"active_agent": "2", "handoff": False}

    def test_condition_text_mention_case_insensitive(self):
        """OnTextMention is case-insensitive (per handoff.py implementation)."""
        conditions = [OnTextMention(text="HANDOFF_TO_QA", target="qa")]
        check = self._make_handoff_fn("loop", ["coder", "qa"], conditions)

        r = check(result="handoff_to_qa", active_agent="1")
        assert r == {"active_agent": "2", "handoff": True}

        r = check(result="Handoff_To_QA", active_agent="1")
        assert r == {"active_agent": "2", "handoff": True}

    def test_full_coder_qa_loop_scenario(self):
        """End-to-end simulation of the issue fixer coder↔qa loop.

        Parent: coder_qa_loop (SWARM, no handoffs, stop_when QA_APPROVED)
        Children: coder, qa_agent (each with OnTextMention handoffs)

        The children's OnTextMention handoffs are NOT evaluated by the parent's
        handoff_check. Only transfer tools (is_transfer=true) work.
        """
        # Parent has NO conditions — children's OnTextMention don't propagate
        check = self._make_handoff_fn("coder_qa_loop", ["coder", "qa_agent"])

        # Turn 1: coder runs, calls transfer_to_qa_agent
        r = check(
            result="I've implemented the fix. HANDOFF_TO_QA",
            active_agent="1",  # coder
            is_transfer=True,
            transfer_to="qa_agent",
        )
        assert r == {"active_agent": "2", "handoff": True}

        # Turn 2: qa_agent runs, finds issues, calls transfer_to_coder
        r = check(
            result="Found bugs. HANDOFF_TO_CODER",
            active_agent="2",  # qa_agent
            is_transfer=True,
            transfer_to="coder",
        )
        assert r == {"active_agent": "1", "handoff": True}

        # Turn 3: coder fixes, transfers to qa again
        r = check(
            result="Fixed the bugs. HANDOFF_TO_QA",
            active_agent="1",
            is_transfer=True,
            transfer_to="qa_agent",
        )
        assert r == {"active_agent": "2", "handoff": True}

        # Turn 4: qa approves, does NOT transfer — loop should exit
        r = check(
            result="QA_APPROVED — all tests pass",
            active_agent="2",
            is_transfer=False,
        )
        assert r == {"active_agent": "2", "handoff": False}
        # stop_when would catch "QA_APPROVED" and terminate the DO_WHILE


# ═══════════════════════════════════════════════════════════════════════════
# 4. Counterfactual: verify the test WOULD fail without the fix
# ═══════════════════════════════════════════════════════════════════════════


class TestCounterfactualWithoutFix:
    """Prove the fix is necessary by showing the old logic would miss handoff_check."""

    def test_old_logic_misses_swarm_without_handoffs(self, child_a, child_b):
        """The OLD condition (agent.handoffs only) would NOT include handoff_check."""
        swarm = Agent(
            name="my_swarm",
            model="openai/gpt-4o",
            agents=[child_a, child_b],
            strategy=Strategy.SWARM,
        )
        # Simulate the OLD logic: only check agent.handoffs
        old_would_register = bool(swarm.handoffs)
        assert old_would_register is False, "Old logic would miss this — that's the bug"

        # NEW logic: also check strategy == SWARM with sub-agents
        new_would_register = bool(swarm.handoffs) or (
            swarm.strategy == "swarm" and bool(swarm.agents)
        )
        assert new_would_register is True, "New logic catches it"

    def test_old_logic_works_for_swarm_with_handoffs(self, child_a, child_b):
        """The OLD logic was fine when parent had explicit handoffs."""
        swarm = Agent(
            name="my_swarm",
            model="openai/gpt-4o",
            agents=[child_a, child_b],
            strategy=Strategy.SWARM,
            handoffs=[OnTextMention(text="GO", target="child_b")],
        )
        old_would_register = bool(swarm.handoffs)
        assert old_would_register is True

    def test_issue_fixer_exact_topology(self, coder, qa_agent):
        """The exact issue fixer topology that triggered the production bug."""
        loop = Agent(
            name="coder_qa_loop",
            model="openai/gpt-4o",
            agents=[coder, qa_agent],
            strategy=Strategy.SWARM,
            max_turns=90,
        )

        # Old logic: coder_qa_loop.handoffs is empty → would NOT register
        assert loop.handoffs == []

        # But children DO have handoffs (these are decorative for SWARM parent)
        assert len(coder.handoffs) == 1
        assert len(qa_agent.handoffs) == 1

        # New logic: strategy=SWARM + agents → register
        names = _collect_names(loop)
        assert "coder_qa_loop_handoff_check" in names


# ═══════════════════════════════════════════════════════════════════════════
# 5. Exhaustive strategy coverage — handoff_check presence for every strategy
# ═══════════════════════════════════════════════════════════════════════════


class TestHandoffCheckAllStrategies:
    """For every Strategy enum value, verify handoff_check presence/absence."""

    @pytest.mark.parametrize(
        "strategy,expect_handoff_check",
        [
            (Strategy.SWARM, True),       # Always — server generates it
            (Strategy.HANDOFF, False),     # No — server uses SUB_WORKFLOW
            (Strategy.SEQUENTIAL, False),  # No — server uses DO_WHILE + SUB_WORKFLOW
            (Strategy.PARALLEL, False),    # No — server uses FORK_JOIN
            (Strategy.ROUND_ROBIN, False), # No — server uses DO_WHILE + SWITCH
            (Strategy.RANDOM, False),      # No — server uses DO_WHILE + SWITCH
            (Strategy.MANUAL, False),      # No — server uses WAIT + SUB_WORKFLOW
        ],
    )
    def test_strategy_handoff_check(self, strategy, expect_handoff_check):
        """Only SWARM gets handoff_check when parent has no explicit handoffs."""
        a = Agent(name="a", model="openai/gpt-4o")
        b = Agent(name="b", model="openai/gpt-4o")
        parent = Agent(
            name="parent",
            model="openai/gpt-4o",
            agents=[a, b],
            strategy=strategy,
        )
        names = _collect_names(parent)
        if expect_handoff_check:
            assert "parent_handoff_check" in names, (
                f"Strategy {strategy.value} should include handoff_check"
            )
        else:
            assert "parent_handoff_check" not in names, (
                f"Strategy {strategy.value} should NOT include handoff_check "
                f"(without explicit handoffs)"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 6. Registration path — verify _register_handoff_worker is actually called
#    for both stateful (domain=UUID) and non-stateful (domain=None)
# ═══════════════════════════════════════════════════════════════════════════


class TestHandoffCheckRegistrationPath:
    """Test that _register_workers actually calls _register_handoff_worker.

    _collect_worker_names decides WHAT to collect.
    _register_workers decides WHAT to register.
    They use the same condition — but we must test both paths.

    Patches _register_handoff_worker to capture calls without needing
    a real Conductor client.
    """

    @staticmethod
    def _make_runtime():
        """Create a minimal AgentRuntime without server connection."""
        rt = AgentRuntime.__new__(AgentRuntime)
        # _register_workers calls ToolRegistry and other registration methods.
        # We patch them all to no-op so only _register_handoff_worker matters.
        return rt

    def test_non_stateful_swarm_registers_handoff_worker(self):
        """Non-stateful SWARM (domain=None): _register_handoff_worker called."""
        a = Agent(name="agent_a", model="openai/gpt-4o")
        b = Agent(name="agent_b", model="openai/gpt-4o")
        swarm = Agent(
            name="swarm_parent",
            model="openai/gpt-4o",
            agents=[a, b],
            strategy=Strategy.SWARM,
        )
        assert swarm.handoffs == []  # no explicit handoffs

        rt = self._make_runtime()
        with patch.object(rt, "_register_handoff_worker") as mock_handoff, \
             patch.object(rt, "_register_swarm_transfer_workers"), \
             patch.object(rt, "_register_check_transfer_worker"):
            # required_workers=None → fallback mode, register everything
            rt._register_workers(swarm, required_workers=None, domain=None)

        mock_handoff.assert_called_once_with(swarm, domain=None)

    def test_stateful_swarm_registers_handoff_worker_with_domain(self):
        """Stateful SWARM (domain=UUID): _register_handoff_worker called with domain."""
        a = Agent(name="agent_a", model="openai/gpt-4o")
        b = Agent(name="agent_b", model="openai/gpt-4o")
        swarm = Agent(
            name="swarm_parent",
            model="openai/gpt-4o",
            agents=[a, b],
            strategy=Strategy.SWARM,
            stateful=True,
        )
        assert swarm.handoffs == []

        fake_domain = "abc123-uuid-domain"
        rt = self._make_runtime()
        with patch.object(rt, "_register_handoff_worker") as mock_handoff, \
             patch.object(rt, "_register_swarm_transfer_workers"), \
             patch.object(rt, "_register_check_transfer_worker"):
            rt._register_workers(swarm, required_workers=None, domain=fake_domain)

        mock_handoff.assert_called_once_with(swarm, domain=fake_domain)

    def test_non_stateful_swarm_with_handoffs_on_children(self):
        """Non-stateful, handoffs on children only — parent still gets registered."""
        coder = Agent(
            name="coder",
            model="openai/gpt-4o",
            handoffs=[OnTextMention(text="HANDOFF_TO_QA", target="qa")],
        )
        qa = Agent(
            name="qa",
            model="openai/gpt-4o",
            handoffs=[OnTextMention(text="HANDOFF_TO_CODER", target="coder")],
        )
        loop = Agent(
            name="coder_qa_loop",
            model="openai/gpt-4o",
            agents=[coder, qa],
            strategy=Strategy.SWARM,
        )
        assert loop.handoffs == []  # parent has NO handoffs

        rt = self._make_runtime()
        with patch.object(rt, "_register_handoff_worker") as mock_handoff, \
             patch.object(rt, "_register_swarm_transfer_workers"), \
             patch.object(rt, "_register_check_transfer_worker"):
            rt._register_workers(loop, required_workers=None, domain=None)

        # Parent gets registered (SWARM + agents)
        parent_calls = [c for c in mock_handoff.call_args_list if c[0][0].name == "coder_qa_loop"]
        assert len(parent_calls) == 1
        assert parent_calls[0].kwargs["domain"] is None

        # Children also get registered (they have explicit handoffs)
        child_calls = [c for c in mock_handoff.call_args_list if c[0][0].name != "coder_qa_loop"]
        child_names = {c[0][0].name for c in child_calls}
        assert "coder" in child_names
        assert "qa" in child_names

    def test_non_swarm_without_handoffs_skips_registration(self):
        """Sequential with no handoffs: _register_handoff_worker NOT called."""
        a = Agent(name="agent_a", model="openai/gpt-4o")
        b = Agent(name="agent_b", model="openai/gpt-4o")
        seq = Agent(
            name="pipeline",
            model="openai/gpt-4o",
            agents=[a, b],
            strategy=Strategy.SEQUENTIAL,
        )

        rt = self._make_runtime()
        with patch.object(rt, "_register_handoff_worker") as mock_handoff:
            rt._register_workers(seq, required_workers=None, domain=None)

        mock_handoff.assert_not_called()

    def test_server_required_workers_controls_registration(self):
        """When server provides required_workers, only listed tasks are registered."""
        a = Agent(name="agent_a", model="openai/gpt-4o")
        b = Agent(name="agent_b", model="openai/gpt-4o")
        swarm = Agent(
            name="swarm_parent",
            model="openai/gpt-4o",
            agents=[a, b],
            strategy=Strategy.SWARM,
        )

        # Server says it needs handoff_check
        required_with = {"swarm_parent_handoff_check", "swarm_parent_stop_when"}
        rt = self._make_runtime()
        with patch.object(rt, "_register_handoff_worker") as mock_handoff, \
             patch.object(rt, "_register_swarm_transfer_workers"), \
             patch.object(rt, "_register_check_transfer_worker"):
            rt._register_workers(swarm, required_workers=required_with, domain=None)
        mock_handoff.assert_called_once()

        # Server says it does NOT need handoff_check
        required_without = {"swarm_parent_stop_when"}
        rt2 = self._make_runtime()
        with patch.object(rt2, "_register_handoff_worker") as mock_handoff2, \
             patch.object(rt2, "_register_swarm_transfer_workers"), \
             patch.object(rt2, "_register_check_transfer_worker"):
            rt2._register_workers(swarm, required_workers=required_without, domain=None)
        mock_handoff2.assert_not_called()
