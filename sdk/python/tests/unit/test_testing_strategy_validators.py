# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tests for conductor.ai.agents.testing.strategy_validators."""

import pytest

from conductor.ai.agents.result import AgentEvent, AgentResult, EventType
from conductor.ai.agents.testing.mock import MockEvent, mock_run
from conductor.ai.agents.testing.strategy_validators import (
    StrategyViolation,
    validate_constrained_transitions,
    validate_handoff,
    validate_parallel,
    validate_round_robin,
    validate_router,
    validate_sequential,
    validate_strategy,
    validate_swarm,
)

# ── Helpers ────────────────────────────────────────────────────────────


class FakeAgent:
    """Minimal Agent-like object for validator testing."""

    def __init__(
        self, name="test", agents=None, strategy="handoff", max_turns=25, allowed_transitions=None
    ):
        self.name = name
        self.agents = agents or []
        self.strategy = strategy
        self.max_turns = max_turns
        self.allowed_transitions = allowed_transitions


class FakeSubAgent:
    """Minimal sub-agent with a name."""

    def __init__(self, name):
        self.name = name


def _agents(*names):
    return [FakeSubAgent(n) for n in names]


def _result_with_handoffs(*targets, output="Done", extra_events=None):
    events = []
    for t in targets:
        events.append(AgentEvent(type=EventType.HANDOFF, target=t))
    if extra_events:
        events.extend(extra_events)
    events.append(AgentEvent(type=EventType.DONE, output=output))
    return AgentResult(output=output, events=events, status="COMPLETED")


# ═══════════════════════════════════════════════════════════════════════
# SEQUENTIAL
# ═══════════════════════════════════════════════════════════════════════


class TestValidateSequential:
    def test_valid_sequence(self):
        """All agents in order, once each — should pass."""
        agent = FakeAgent(agents=_agents("a", "b", "c"), strategy="sequential")
        result = _result_with_handoffs("a", "b", "c")
        validate_sequential(agent, result)  # no exception

    def test_agent_skipped(self):
        """Agent 'b' never ran — violation."""
        agent = FakeAgent(agents=_agents("a", "b", "c"), strategy="sequential")
        result = _result_with_handoffs("a", "c")
        with pytest.raises(StrategyViolation, match="skipped"):
            validate_sequential(agent, result)

    def test_wrong_order(self):
        """Agents ran but in wrong order — violation."""
        agent = FakeAgent(agents=_agents("a", "b", "c"), strategy="sequential")
        result = _result_with_handoffs("a", "c", "b")
        with pytest.raises(StrategyViolation, match="order"):
            validate_sequential(agent, result)

    def test_agent_ran_twice(self):
        """Agent 'a' ran twice — violation."""
        agent = FakeAgent(agents=_agents("a", "b"), strategy="sequential")
        result = _result_with_handoffs("a", "a", "b")
        with pytest.raises(StrategyViolation, match="multiple times"):
            validate_sequential(agent, result)

    def test_no_sub_agents(self):
        """Agent with no sub-agents — nothing to validate."""
        agent = FakeAgent(agents=[], strategy="sequential")
        result = _result_with_handoffs()
        validate_sequential(agent, result)  # no exception


# ═══════════════════════════════════════════════════════════════════════
# PARALLEL
# ═══════════════════════════════════════════════════════════════════════


class TestValidateParallel:
    def test_all_agents_ran(self):
        """All agents present — should pass."""
        agent = FakeAgent(agents=_agents("x", "y", "z"), strategy="parallel")
        result = _result_with_handoffs("x", "y", "z")
        validate_parallel(agent, result)  # no exception

    def test_agent_missing(self):
        """Agent 'z' never ran — violation."""
        agent = FakeAgent(agents=_agents("x", "y", "z"), strategy="parallel")
        result = _result_with_handoffs("x", "y")
        with pytest.raises(StrategyViolation, match="skipped"):
            validate_parallel(agent, result)

    def test_order_doesnt_matter(self):
        """Parallel doesn't care about order — should pass."""
        agent = FakeAgent(agents=_agents("x", "y", "z"), strategy="parallel")
        result = _result_with_handoffs("z", "x", "y")
        validate_parallel(agent, result)  # no exception

    def test_single_agent_missing_from_three(self):
        """Catches exactly which agent was skipped."""
        agent = FakeAgent(agents=_agents("market", "risk", "compliance"), strategy="parallel")
        result = _result_with_handoffs("market", "risk")
        with pytest.raises(StrategyViolation, match="compliance"):
            validate_parallel(agent, result)


# ═══════════════════════════════════════════════════════════════════════
# ROUND_ROBIN
# ═══════════════════════════════════════════════════════════════════════


class TestValidateRoundRobin:
    def test_valid_alternation_two_agents(self):
        """A→B→A→B — correct round-robin."""
        agent = FakeAgent(agents=_agents("a", "b"), strategy="round_robin", max_turns=4)
        result = _result_with_handoffs("a", "b", "a", "b")
        validate_round_robin(agent, result)  # no exception

    def test_valid_alternation_three_agents(self):
        """A→B→C→A→B→C — correct 3-agent round-robin."""
        agent = FakeAgent(agents=_agents("a", "b", "c"), strategy="round_robin", max_turns=6)
        result = _result_with_handoffs("a", "b", "c", "a", "b", "c")
        validate_round_robin(agent, result)  # no exception

    def test_agent_never_gets_turn(self):
        """Agent 'b' never ran — violation."""
        agent = FakeAgent(agents=_agents("a", "b"), strategy="round_robin")
        result = _result_with_handoffs("a", "a", "a")
        with pytest.raises(StrategyViolation, match="never got a turn"):
            validate_round_robin(agent, result)

    def test_wrong_rotation_order(self):
        """B→A instead of A→B — pattern broken."""
        agent = FakeAgent(agents=_agents("a", "b"), strategy="round_robin")
        result = _result_with_handoffs("b", "a", "b", "a")
        with pytest.raises(StrategyViolation, match="pattern broken"):
            validate_round_robin(agent, result)

    def test_same_agent_twice_in_a_row(self):
        """A→A is not valid round-robin."""
        agent = FakeAgent(agents=_agents("a", "b"), strategy="round_robin")
        result = _result_with_handoffs("a", "a", "b")
        with pytest.raises(StrategyViolation, match="twice in a row"):
            validate_round_robin(agent, result)

    def test_exceeds_max_turns(self):
        """More turns than max_turns — violation."""
        agent = FakeAgent(agents=_agents("a", "b"), strategy="round_robin", max_turns=2)
        result = _result_with_handoffs("a", "b", "a", "b")
        with pytest.raises(StrategyViolation, match="max_turns"):
            validate_round_robin(agent, result)

    def test_within_max_turns(self):
        """Exactly at max_turns — should pass."""
        agent = FakeAgent(agents=_agents("a", "b"), strategy="round_robin", max_turns=4)
        result = _result_with_handoffs("a", "b", "a", "b")
        validate_round_robin(agent, result)  # no exception


# ═══════════════════════════════════════════════════════════════════════
# ROUTER
# ═══════════════════════════════════════════════════════════════════════


class TestValidateRouter:
    def test_one_agent_selected(self):
        """Router picks exactly one agent — should pass."""
        agent = FakeAgent(agents=_agents("coder", "reviewer"), strategy="router")
        result = _result_with_handoffs("coder")
        validate_router(agent, result)  # no exception

    def test_no_agent_selected(self):
        """Router didn't route to any sub-agent — violation."""
        agent = FakeAgent(agents=_agents("coder", "reviewer"), strategy="router")
        result = _result_with_handoffs()  # no handoffs
        with pytest.raises(StrategyViolation, match="No sub-agent was selected"):
            validate_router(agent, result)

    def test_multiple_agents_selected(self):
        """Router picked two different agents — violation."""
        agent = FakeAgent(agents=_agents("coder", "reviewer"), strategy="router")
        result = _result_with_handoffs("coder", "reviewer")
        with pytest.raises(StrategyViolation, match="multiple agents"):
            validate_router(agent, result)

    def test_same_agent_twice_ok(self):
        """Same agent selected twice (retry) — OK for router, it's still one agent."""
        agent = FakeAgent(agents=_agents("coder", "reviewer"), strategy="router")
        result = _result_with_handoffs("coder", "coder")
        validate_router(agent, result)  # no exception, same agent


# ═══════════════════════════════════════════════════════════════════════
# HANDOFF
# ═══════════════════════════════════════════════════════════════════════


class TestValidateHandoff:
    def test_valid_handoff(self):
        """Parent delegates to sub-agent — should pass."""
        agent = FakeAgent(agents=_agents("billing", "tech"), strategy="handoff")
        result = _result_with_handoffs("billing")
        validate_handoff(agent, result)  # no exception

    def test_no_handoff_at_all(self):
        """Parent handled everything itself — violation."""
        agent = FakeAgent(agents=_agents("billing", "tech"), strategy="handoff")
        result = _result_with_handoffs()  # no handoffs
        with pytest.raises(StrategyViolation, match="No handoff"):
            validate_handoff(agent, result)


# ═══════════════════════════════════════════════════════════════════════
# SWARM
# ═══════════════════════════════════════════════════════════════════════


class TestValidateSwarm:
    def test_valid_single_transfer(self):
        """Front-line transfers to specialist — should pass."""
        agent = FakeAgent(agents=_agents("refund", "tech"), strategy="swarm", max_turns=5)
        result = _result_with_handoffs("refund")
        validate_swarm(agent, result)  # no exception

    def test_no_agent_handled(self):
        """No agent handled the request — violation."""
        agent = FakeAgent(agents=_agents("refund", "tech"), strategy="swarm")
        result = _result_with_handoffs()
        with pytest.raises(StrategyViolation, match="No agent handled"):
            validate_swarm(agent, result)

    def test_transfer_loop_detected(self):
        """Same transfer pair repeats excessively — violation."""
        agent = FakeAgent(agents=_agents("a", "b"), strategy="swarm", max_turns=20)
        # a→b→a→b→a→b = 3 times the (a,b) pair
        result = _result_with_handoffs("a", "b", "a", "b", "a", "b")
        with pytest.raises(StrategyViolation, match="loop"):
            validate_swarm(agent, result)

    def test_exceeds_max_turns(self):
        """More transfers than max_turns — violation."""
        agent = FakeAgent(agents=_agents("a", "b"), strategy="swarm", max_turns=2)
        result = _result_with_handoffs("a", "b", "a")
        with pytest.raises(StrategyViolation, match="Too many transfers"):
            validate_swarm(agent, result)

    def test_valid_multi_hop(self):
        """a→b→a is valid if within limits and no excessive looping."""
        agent = FakeAgent(agents=_agents("a", "b"), strategy="swarm", max_turns=5)
        result = _result_with_handoffs("a", "b")
        validate_swarm(agent, result)  # no exception


# ═══════════════════════════════════════════════════════════════════════
# CONSTRAINED TRANSITIONS
# ═══════════════════════════════════════════════════════════════════════


class TestValidateConstrainedTransitions:
    def test_valid_transitions(self):
        """All transitions respect constraints — should pass."""
        agent = FakeAgent(
            agents=_agents("dev", "review", "approve"),
            strategy="round_robin",
            allowed_transitions={
                "dev": ["review"],
                "review": ["dev", "approve"],
                "approve": ["dev"],
            },
        )
        result = _result_with_handoffs("dev", "review", "approve")
        validate_constrained_transitions(agent, result)  # no exception

    def test_invalid_transition(self):
        """dev → approve is not allowed — violation."""
        agent = FakeAgent(
            agents=_agents("dev", "review", "approve"),
            strategy="round_robin",
            allowed_transitions={
                "dev": ["review"],
                "review": ["dev", "approve"],
                "approve": ["dev"],
            },
        )
        result = _result_with_handoffs("dev", "approve")
        with pytest.raises(StrategyViolation, match="Invalid transition.*dev.*approve"):
            validate_constrained_transitions(agent, result)

    def test_multiple_invalid_transitions(self):
        """Multiple constraint violations detected."""
        agent = FakeAgent(
            agents=_agents("a", "b", "c"),
            strategy="round_robin",
            allowed_transitions={
                "a": ["b"],
                "b": ["c"],
                "c": ["a"],
            },
        )
        # a→c is invalid (should be a→b)
        result = _result_with_handoffs("a", "c")
        with pytest.raises(StrategyViolation, match="Invalid transition"):
            validate_constrained_transitions(agent, result)

    def test_no_constraints(self):
        """No allowed_transitions — nothing to validate."""
        agent = FakeAgent(agents=_agents("a", "b"), allowed_transitions=None)
        result = _result_with_handoffs("a", "b")
        validate_constrained_transitions(agent, result)  # no exception


# ═══════════════════════════════════════════════════════════════════════
# validate_strategy DISPATCH
# ═══════════════════════════════════════════════════════════════════════


class TestValidateStrategy:
    def test_dispatches_to_sequential(self):
        agent = FakeAgent(agents=_agents("a", "b"), strategy="sequential")
        result = _result_with_handoffs("a", "b")
        validate_strategy(agent, result)  # no exception

    def test_dispatches_to_parallel(self):
        agent = FakeAgent(agents=_agents("x", "y"), strategy="parallel")
        result = _result_with_handoffs("x", "y")
        validate_strategy(agent, result)

    def test_dispatches_to_round_robin(self):
        agent = FakeAgent(agents=_agents("a", "b"), strategy="round_robin", max_turns=4)
        result = _result_with_handoffs("a", "b", "a", "b")
        validate_strategy(agent, result)

    def test_dispatches_to_router(self):
        agent = FakeAgent(agents=_agents("coder", "reviewer"), strategy="router")
        result = _result_with_handoffs("coder")
        validate_strategy(agent, result)

    def test_dispatches_to_swarm(self):
        agent = FakeAgent(agents=_agents("a", "b"), strategy="swarm", max_turns=5)
        result = _result_with_handoffs("a")
        validate_strategy(agent, result)

    def test_also_validates_constraints(self):
        """validate_strategy should also check allowed_transitions."""
        agent = FakeAgent(
            agents=_agents("a", "b"),
            strategy="round_robin",
            max_turns=4,
            allowed_transitions={"a": ["b"], "b": ["a"]},
        )
        # Valid round-robin AND valid transitions
        result = _result_with_handoffs("a", "b", "a", "b")
        validate_strategy(agent, result)  # no exception

    def test_catches_constraint_violation_via_dispatch(self):
        """validate_strategy catches transition violations even when strategy passes."""
        agent = FakeAgent(
            agents=_agents("a", "b", "c"),
            strategy="round_robin",
            max_turns=6,
            allowed_transitions={"a": ["b"], "b": ["c"], "c": ["a"]},
        )
        # Valid round-robin order but a→c violates constraints
        result = _result_with_handoffs("a", "c")
        with pytest.raises(StrategyViolation):
            validate_strategy(agent, result)


# ═══════════════════════════════════════════════════════════════════════
# INTEGRATION: mock_run + validate_strategy
# ═══════════════════════════════════════════════════════════════════════


class TestMockRunWithValidation:
    """Show how validate_strategy works with mock_run results."""

    def test_sequential_mock_valid(self):
        from conductor.ai.agents import Agent

        a = Agent(name="step_a", model="openai/gpt-4o", instructions="Step A")
        b = Agent(name="step_b", model="openai/gpt-4o", instructions="Step B")
        pipeline = a >> b

        result = mock_run(
            pipeline,
            "Do the thing",
            events=[
                MockEvent.handoff("step_a"),
                MockEvent.handoff("step_b"),
                MockEvent.done("All done"),
            ],
        )
        validate_strategy(pipeline, result)  # passes

    def test_sequential_mock_violation(self):
        from conductor.ai.agents import Agent

        a = Agent(name="step_a", model="openai/gpt-4o", instructions="Step A")
        b = Agent(name="step_b", model="openai/gpt-4o", instructions="Step B")
        pipeline = a >> b

        # b runs but a is skipped
        result = mock_run(
            pipeline,
            "Do the thing",
            events=[
                MockEvent.handoff("step_b"),
                MockEvent.done("Skipped step A"),
            ],
        )
        with pytest.raises(StrategyViolation, match="skipped"):
            validate_strategy(pipeline, result)

    def test_parallel_mock_valid(self):
        from conductor.ai.agents import Agent, Strategy

        analyst1 = Agent(name="market", model="openai/gpt-4o", instructions="Market")
        analyst2 = Agent(name="risk", model="openai/gpt-4o", instructions="Risk")
        team = Agent(
            name="team",
            model="openai/gpt-4o",
            agents=[analyst1, analyst2],
            strategy=Strategy.PARALLEL,
        )

        result = mock_run(
            team,
            "Evaluate",
            events=[
                MockEvent.handoff("market"),
                MockEvent.handoff("risk"),
                MockEvent.done("Both analyzed"),
            ],
        )
        validate_strategy(team, result)  # passes

    def test_parallel_mock_violation(self):
        from conductor.ai.agents import Agent, Strategy

        analyst1 = Agent(name="market", model="openai/gpt-4o", instructions="Market")
        analyst2 = Agent(name="risk", model="openai/gpt-4o", instructions="Risk")
        team = Agent(
            name="team",
            model="openai/gpt-4o",
            agents=[analyst1, analyst2],
            strategy=Strategy.PARALLEL,
        )

        # Only market ran, risk was skipped
        result = mock_run(
            team,
            "Evaluate",
            events=[
                MockEvent.handoff("market"),
                MockEvent.done("Only market analyzed"),
            ],
        )
        with pytest.raises(StrategyViolation, match="risk"):
            validate_strategy(team, result)

    def test_round_robin_mock_wrong_pattern(self):
        from conductor.ai.agents import Agent, Strategy

        opt = Agent(name="optimist", model="openai/gpt-4o", instructions="Positive")
        skp = Agent(name="skeptic", model="openai/gpt-4o", instructions="Negative")
        debate = Agent(
            name="debate",
            model="openai/gpt-4o",
            agents=[opt, skp],
            strategy=Strategy.ROUND_ROBIN,
            max_turns=4,
        )

        # skeptic goes first instead of optimist — wrong rotation
        result = mock_run(
            debate,
            "Debate AI",
            events=[
                MockEvent.handoff("skeptic"),
                MockEvent.handoff("optimist"),
                MockEvent.done("Debated"),
            ],
        )
        with pytest.raises(StrategyViolation, match="pattern broken"):
            validate_strategy(debate, result)

    def test_router_mock_multiple_agents(self):
        from conductor.ai.agents import Agent, Strategy

        coder = Agent(name="coder", model="openai/gpt-4o", instructions="Code")
        reviewer = Agent(name="reviewer", model="openai/gpt-4o", instructions="Review")
        router_agent = Agent(name="router", model="openai/gpt-4o", instructions="Route")
        team = Agent(
            name="team",
            model="openai/gpt-4o",
            agents=[coder, reviewer],
            strategy=Strategy.ROUTER,
            router=router_agent,
        )

        # Router sent to BOTH agents — violation
        result = mock_run(
            team,
            "Do stuff",
            events=[
                MockEvent.handoff("coder"),
                MockEvent.handoff("reviewer"),
                MockEvent.done("Both ran"),
            ],
        )
        with pytest.raises(StrategyViolation, match="multiple agents"):
            validate_strategy(team, result)
