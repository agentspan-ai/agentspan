#!/usr/bin/env python3
"""
05 — Advanced Patterns
=======================

Swarm strategy, constrained transitions, nested strategies,
strategy validation, record/replay, and the CorrectnessEval runner.

Covers:
  - Strategy.SWARM — LLM-driven transfers with OnTextMention conditions
  - Constrained transitions with allowed_transitions
  - Nested strategies (parallel >> sequential)
  - validate_strategy() for structural correctness
  - StrategyViolation detection (skipped agents, wrong order, loops)
  - record() / replay() for regression testing
  - CorrectnessEval + EvalCase for live evaluation (integration)

Run:
    pytest examples/mock_tests/05_advanced_patterns.py -v
"""

import pytest

from agentspan.agents import Agent, OnTextMention, Strategy, tool
from agentspan.agents.result import EventType
from agentspan.agents.testing import (
    MockEvent,
    StrategyViolation,
    assert_agent_ran,
    assert_event_sequence,
    assert_handoff_to,
    assert_no_errors,
    assert_tool_not_used,
    assert_tool_used,
    expect,
    mock_run,
    record,
    replay,
    validate_strategy,
)


# ── Tools ────────────────────────────────────────────────────────────


@tool
def check_inventory(product_id: str) -> dict:
    """Check product inventory."""
    return {"product_id": product_id, "in_stock": True, "quantity": 50}


@tool
def process_return(order_id: str, reason: str) -> str:
    """Process a product return."""
    return f"Return initiated for {order_id}: {reason}"


@tool
def track_shipment(tracking_id: str) -> dict:
    """Track a shipment."""
    return {"tracking_id": tracking_id, "status": "in_transit", "eta": "2 days"}


@tool
def escalate_to_manager(issue: str) -> str:
    """Escalate an issue to a human manager."""
    return f"Escalated: {issue}"


# ═══════════════════════════════════════════════════════════════════════
# 1. SWARM STRATEGY — dynamic transfers with condition-based handoffs
# ═══════════════════════════════════════════════════════════════════════

inventory_agent = Agent(
    name="inventory_specialist",
    model="openai/gpt-4o",
    instructions="Handle inventory and stock questions.",
    tools=[check_inventory],
)

returns_agent = Agent(
    name="returns_specialist",
    model="openai/gpt-4o",
    instructions="Handle returns and refunds.",
    tools=[process_return],
)

shipping_agent = Agent(
    name="shipping_specialist",
    model="openai/gpt-4o",
    instructions="Handle shipping and tracking questions.",
    tools=[track_shipment],
)

swarm_support = Agent(
    name="ecommerce_support",
    model="openai/gpt-4o",
    instructions="Front-line support. Transfer to the right specialist.",
    agents=[inventory_agent, returns_agent, shipping_agent],
    strategy=Strategy.SWARM,
    handoffs=[
        OnTextMention(text="stock", target="inventory_specialist"),
        OnTextMention(text="return", target="returns_specialist"),
        OnTextMention(text="tracking", target="shipping_specialist"),
    ],
    max_turns=5,
)


class TestSwarmStrategy:
    """LLM-driven transfers with OnTextMention condition fallbacks."""

    def test_transfer_via_tool(self):
        """Agent uses transfer_to_* tool to route explicitly."""
        result = mock_run(
            swarm_support,
            "I need to return order #456",
            events=[
                MockEvent.tool_call("transfer_to_returns_specialist", args={}),
                MockEvent.tool_result("transfer_to_returns_specialist", result="Transferred"),
                MockEvent.handoff("returns_specialist"),
                MockEvent.tool_call(
                    "process_return",
                    args={"order_id": "456", "reason": "defective"},
                ),
                MockEvent.tool_result("process_return", result="Return initiated"),
                MockEvent.done("Your return for order #456 has been initiated."),
            ],
            auto_execute_tools=False,
        )

        assert_tool_used(result, "transfer_to_returns_specialist")
        assert_handoff_to(result, "returns_specialist")
        assert_tool_used(result, "process_return")
        assert_tool_not_used(result, "check_inventory")
        assert_tool_not_used(result, "track_shipment")

    def test_condition_based_fallback(self):
        """OnTextMention triggers when transfer tool isn't used."""
        result = mock_run(
            swarm_support,
            "Is item X in stock?",
            events=[
                # No transfer tool — "stock" keyword triggers OnTextMention
                MockEvent.handoff("inventory_specialist"),
                MockEvent.tool_call("check_inventory", args={"product_id": "X"}),
                MockEvent.tool_result(
                    "check_inventory", result={"in_stock": True, "quantity": 50}
                ),
                MockEvent.done("Yes, item X is in stock with 50 units available."),
            ],
            auto_execute_tools=False,
        )

        assert_handoff_to(result, "inventory_specialist")
        assert_tool_not_used(result, "transfer_to_inventory_specialist")

    def test_shipping_transfer(self):
        """Tracking question routes to shipping specialist."""
        result = mock_run(
            swarm_support,
            "Where's my package? Tracking number TRK-789",
            events=[
                MockEvent.handoff("shipping_specialist"),
                MockEvent.tool_call("track_shipment", args={"tracking_id": "TRK-789"}),
                MockEvent.tool_result(
                    "track_shipment",
                    result={"status": "in_transit", "eta": "2 days"},
                ),
                MockEvent.done("Your package is in transit. ETA: 2 days."),
            ],
            auto_execute_tools=False,
        )

        (
            expect(result)
            .completed()
            .handoff_to("shipping_specialist")
            .used_tool("track_shipment")
            .did_not_use_tool("check_inventory")
            .did_not_use_tool("process_return")
            .no_errors()
        )


# ═══════════════════════════════════════════════════════════════════════
# 2. CONSTRAINED TRANSITIONS
# ═══════════════════════════════════════════════════════════════════════

l1_support = Agent(
    name="l1_support",
    model="openai/gpt-4o",
    instructions="First-line support. Handle simple questions, escalate complex ones.",
)

l2_engineer = Agent(
    name="l2_engineer",
    model="openai/gpt-4o",
    instructions="Handle technical issues escalated from L1.",
    tools=[track_shipment],
)

l3_manager = Agent(
    name="l3_manager",
    model="openai/gpt-4o",
    instructions="Handle escalations requiring management approval.",
    tools=[escalate_to_manager],
)

escalation_flow = Agent(
    name="escalation",
    model="openai/gpt-4o",
    agents=[l1_support, l2_engineer, l3_manager],
    strategy=Strategy.ROUND_ROBIN,
    max_turns=6,
    allowed_transitions={
        "l1_support": ["l2_engineer"],         # L1 can only escalate to L2
        "l2_engineer": ["l1_support", "l3_manager"],  # L2 can go back or escalate
        "l3_manager": ["l2_engineer"],         # L3 can only send back to L2
    },
)


class TestConstrainedTransitions:
    """allowed_transitions restricts which agent can follow which."""

    def test_valid_escalation_path(self):
        """L1 → L2 → L3 is a valid escalation path."""
        result = mock_run(
            escalation_flow,
            "Complex billing issue",
            events=[
                MockEvent.handoff("l1_support"),
                MockEvent.message("This needs engineering review."),
                MockEvent.handoff("l2_engineer"),
                MockEvent.message("This needs manager approval."),
                MockEvent.handoff("l3_manager"),
                MockEvent.tool_call(
                    "escalate_to_manager", args={"issue": "Complex billing dispute"}
                ),
                MockEvent.tool_result("escalate_to_manager", result="Escalated"),
                MockEvent.done("Your issue has been escalated to management."),
            ],
            auto_execute_tools=False,
        )

        assert_agent_ran(result, "l1_support")
        assert_agent_ran(result, "l2_engineer")
        assert_agent_ran(result, "l3_manager")

        # Verify transition sequence respects constraints
        handoffs = [ev.target for ev in result.events if ev.type == EventType.HANDOFF]
        allowed = {
            "l1_support": {"l2_engineer"},
            "l2_engineer": {"l1_support", "l3_manager"},
            "l3_manager": {"l2_engineer"},
        }
        for i in range(len(handoffs) - 1):
            src, dst = handoffs[i], handoffs[i + 1]
            assert dst in allowed[src], f"Invalid: {src} → {dst}"

    def test_bounce_back_from_l2(self):
        """L2 sends it back to L1 — valid transition."""
        result = mock_run(
            escalation_flow,
            "Simple question mistakenly escalated",
            events=[
                MockEvent.handoff("l1_support"),
                MockEvent.handoff("l2_engineer"),
                MockEvent.message("This is simple, sending back to L1."),
                MockEvent.handoff("l1_support"),
                MockEvent.done("Here's your answer."),
            ],
        )

        handoffs = [ev.target for ev in result.events if ev.type == EventType.HANDOFF]
        assert handoffs == ["l1_support", "l2_engineer", "l1_support"]


# ═══════════════════════════════════════════════════════════════════════
# 3. NESTED STRATEGIES — parallel into sequential
# ═══════════════════════════════════════════════════════════════════════

market_researcher = Agent(
    name="market_researcher",
    model="openai/gpt-4o",
    instructions="Research market trends.",
)

competitor_analyst = Agent(
    name="competitor_analyst",
    model="openai/gpt-4o",
    instructions="Analyze competitors.",
)

parallel_research = Agent(
    name="research_phase",
    model="openai/gpt-4o",
    agents=[market_researcher, competitor_analyst],
    strategy=Strategy.PARALLEL,
)

report_writer = Agent(
    name="report_writer",
    model="openai/gpt-4o",
    instructions="Write a synthesis report from multiple analyses.",
)

# Nested: parallel research → sequential report writing
research_pipeline = parallel_research >> report_writer


class TestNestedStrategies:
    """Compose strategies: parallel research feeds into sequential summary."""

    def test_parallel_then_sequential(self):
        result = mock_run(
            research_pipeline,
            "Analyze the cloud computing market",
            events=[
                # Parallel phase — both researchers run
                MockEvent.handoff("market_researcher"),
                MockEvent.handoff("competitor_analyst"),
                # Sequential phase — report writer synthesizes
                MockEvent.handoff("report_writer"),
                MockEvent.done(
                    "Market is growing 20% YoY. "
                    "Top competitor: AWS with 32% share. "
                    "Opportunity: edge computing niche."
                ),
            ],
        )

        assert_agent_ran(result, "market_researcher")
        assert_agent_ran(result, "competitor_analyst")
        assert_agent_ran(result, "report_writer")

        # Report writer comes AFTER both researchers
        assert_event_sequence(
            result,
            [
                EventType.HANDOFF,  # market_researcher
                EventType.HANDOFF,  # competitor_analyst
                EventType.HANDOFF,  # report_writer (must be after both)
                EventType.DONE,
            ],
        )

        (
            expect(result)
            .completed()
            .output_contains("Market")
            .output_contains("competitor")
            .no_errors()
        )


# ═══════════════════════════════════════════════════════════════════════
# 4. STRATEGY VALIDATION — structural correctness
# ═══════════════════════════════════════════════════════════════════════


class TestStrategyValidation:
    """
    validate_strategy() checks that the execution trace matches
    the strategy rules — catches bugs the individual assertions miss.
    """

    # ── Sequential: all agents, in order ──────────────────────────

    def test_sequential_valid(self):
        result = mock_run(
            research_pipeline,
            "Research topic",
            events=[
                MockEvent.handoff("market_researcher"),
                MockEvent.handoff("competitor_analyst"),
                MockEvent.handoff("report_writer"),
                MockEvent.done("Report complete."),
            ],
        )
        validate_strategy(research_pipeline, result)  # No exception = pass

    def test_sequential_catches_skipped_agent(self):
        """Report writer was skipped — validation catches it."""
        result = mock_run(
            research_pipeline,
            "Research",
            events=[
                MockEvent.handoff("market_researcher"),
                MockEvent.handoff("competitor_analyst"),
                # report_writer is MISSING
                MockEvent.done("Incomplete."),
            ],
        )
        with pytest.raises(StrategyViolation, match="skipped"):
            validate_strategy(research_pipeline, result)

    # ── Parallel: all agents must run ─────────────────────────────

    def test_parallel_valid(self):
        result = mock_run(
            parallel_research,
            "Research",
            events=[
                MockEvent.handoff("competitor_analyst"),
                MockEvent.handoff("market_researcher"),
                MockEvent.done("Done."),
            ],
        )
        validate_strategy(parallel_research, result)

    def test_parallel_catches_missing_agent(self):
        result = mock_run(
            parallel_research,
            "Research",
            events=[
                MockEvent.handoff("market_researcher"),
                # competitor_analyst is MISSING
                MockEvent.done("Partial."),
            ],
        )
        with pytest.raises(StrategyViolation, match="competitor_analyst"):
            validate_strategy(parallel_research, result)

    # ── Swarm: valid transfers, no loops ──────────────────────────

    def test_swarm_valid(self):
        result = mock_run(
            swarm_support,
            "I need to return something",
            events=[
                MockEvent.handoff("returns_specialist"),
                MockEvent.done("Return processed."),
            ],
        )
        validate_strategy(swarm_support, result)

    def test_swarm_catches_transfer_loop(self):
        """Agents ping-pong back and forth — loop detected."""
        result = mock_run(
            swarm_support,
            "Confusing request",
            events=[
                MockEvent.handoff("inventory_specialist"),
                MockEvent.handoff("returns_specialist"),
                MockEvent.handoff("inventory_specialist"),
                MockEvent.handoff("returns_specialist"),
                MockEvent.handoff("inventory_specialist"),
                MockEvent.handoff("returns_specialist"),
                MockEvent.done("Finally resolved."),
            ],
        )
        with pytest.raises(StrategyViolation, match="loop"):
            validate_strategy(swarm_support, result)

    # ── Constrained transitions ───────────────────────────────────

    def test_constrained_catches_invalid_transition(self):
        """L1 → L3 is invalid (must go through L2)."""
        from agentspan.agents.testing.strategy_validators import (
            validate_constrained_transitions,
        )

        result = mock_run(
            escalation_flow,
            "Quick escalation",
            events=[
                MockEvent.handoff("l1_support"),
                MockEvent.handoff("l3_manager"),  # INVALID: L1 can only go to L2
                MockEvent.done("Done."),
            ],
        )
        with pytest.raises(StrategyViolation, match="Invalid transition"):
            validate_constrained_transitions(escalation_flow, result)


# ═══════════════════════════════════════════════════════════════════════
# 5. RECORD / REPLAY — fixture-based regression tests
# ═══════════════════════════════════════════════════════════════════════


class TestRecordReplay:
    """Save an execution to a file, replay it later for regression tests."""

    def test_record_and_replay(self, tmp_path):
        """Record a mock result to JSON, replay it, re-assert."""
        fixture_path = tmp_path / "support_run.json"

        # Record
        result = mock_run(
            swarm_support,
            "Track my package TRK-001",
            events=[
                MockEvent.handoff("shipping_specialist"),
                MockEvent.tool_call("track_shipment", args={"tracking_id": "TRK-001"}),
                MockEvent.tool_result(
                    "track_shipment", result={"status": "delivered"}
                ),
                MockEvent.done("Your package has been delivered!"),
            ],
            auto_execute_tools=False,
        )
        record(result, fixture_path)

        # Replay
        replayed = replay(fixture_path)

        # Same assertions pass on the replayed result
        (
            expect(replayed)
            .completed()
            .handoff_to("shipping_specialist")
            .used_tool("track_shipment")
            .output_contains("delivered")
            .no_errors()
        )
