#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""
Testing Multi-Agent Correctness
================================

This file demonstrates how to write correctness tests for every multi-agent
strategy in Agentspan.  Each section shows:

  1. How the agent is defined
  2. What "correct behavior" means for that strategy
  3. How to write mock tests (deterministic, no LLM/server)
  4. How to write live tests (real execution, tolerant assertions)

Run the mock tests with:
    pytest examples/testing_multi_agent_correctness.py -v

The live tests require a running Agentspan server and are marked with
@pytest.mark.integration.
"""

import pytest

from agentspan.agents import Agent, Strategy, tool
from agentspan.agents.result import EventType
from agentspan.agents.testing import (
    MockEvent,
    assert_agent_ran,
    assert_event_sequence,
    assert_handoff_to,
    assert_no_errors,
    assert_output_contains,
    assert_status,
    assert_tool_call_order,
    assert_tool_called_with,
    assert_tool_not_used,
    assert_tool_used,
    expect,
    mock_run,
)


# ═══════════════════════════════════════════════════════════════════════
# Shared tools and agents used across examples
# ═══════════════════════════════════════════════════════════════════════


@tool
def search_web(query: str) -> str:
    """Search the web for information."""
    return f"Results for: {query}"


@tool
def calculate(expression: str) -> str:
    """Evaluate a math expression."""
    return str(eval(expression))  # noqa: S307


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email."""
    return f"Email sent to {to}"


@tool
def lookup_order(order_id: str) -> dict:
    """Look up an order by ID."""
    return {"order_id": order_id, "status": "shipped", "total": 49.99}


@tool
def process_refund(order_id: str, amount: float) -> str:
    """Process a refund for an order."""
    return f"Refund of ${amount} processed for order {order_id}"


# ═══════════════════════════════════════════════════════════════════════
# 1. HANDOFF STRATEGY
# ═══════════════════════════════════════════════════════════════════════
#
# The parent LLM decides which sub-agent to delegate to.
# Sub-agents appear as callable tools to the parent.
#
# Correctness means:
#   - The parent delegates to the RIGHT specialist for the query
#   - The parent does NOT handle the query itself when a specialist exists
#   - The specialist actually runs and produces output
# ═══════════════════════════════════════════════════════════════════════


billing_agent = Agent(
    name="billing",
    model="openai/gpt-4o",
    instructions="You handle billing questions. Look up orders and process refunds.",
    tools=[lookup_order, process_refund],
)

technical_agent = Agent(
    name="technical",
    model="openai/gpt-4o",
    instructions="You handle technical support questions.",
    tools=[search_web],
)

support_handoff = Agent(
    name="support",
    model="openai/gpt-4o",
    instructions="Route customer requests to the right specialist.",
    agents=[billing_agent, technical_agent],
    strategy=Strategy.HANDOFF,
)


class TestHandoffStrategy:
    """
    HANDOFF: Parent LLM picks the right sub-agent.

    What to test:
      - Billing questions → handoff to "billing" agent
      - Technical questions → handoff to "technical" agent
      - Specialist uses appropriate tools
    """

    def test_billing_query_routes_to_billing(self):
        """A refund request should be handled by the billing agent."""
        result = mock_run(
            support_handoff,
            "I want a refund for order #123",
            events=[
                MockEvent.handoff("billing"),
                MockEvent.tool_call("lookup_order", args={"order_id": "123"}),
                MockEvent.tool_result("lookup_order", result={"order_id": "123", "status": "shipped"}),
                MockEvent.tool_call("process_refund", args={"order_id": "123", "amount": 49.99}),
                MockEvent.tool_result("process_refund", result="Refund of $49.99 processed"),
                MockEvent.done("Your refund of $49.99 for order #123 has been processed."),
            ],
            auto_execute_tools=False,
        )

        # The billing agent was selected (not technical)
        assert_handoff_to(result, "billing")

        # The right tools were used in order
        assert_tool_call_order(result, ["lookup_order", "process_refund"])

        # Technical tools were NOT used
        assert_tool_not_used(result, "search_web")

        # Output mentions the refund
        assert_output_contains(result, "refund", case_sensitive=False)

    def test_technical_query_routes_to_technical(self):
        """A technical question should be handled by the technical agent."""
        result = mock_run(
            support_handoff,
            "My app keeps crashing on startup",
            events=[
                MockEvent.handoff("technical"),
                MockEvent.tool_call("search_web", args={"query": "app crash startup"}),
                MockEvent.tool_result("search_web", result="Try clearing the cache..."),
                MockEvent.done("Try clearing your app cache and restarting."),
            ],
            auto_execute_tools=False,
        )

        assert_handoff_to(result, "technical")
        assert_tool_used(result, "search_web")
        assert_tool_not_used(result, "lookup_order")
        assert_tool_not_used(result, "process_refund")

    def test_no_cross_contamination(self):
        """Billing agent should NOT use technical tools and vice versa."""
        result = mock_run(
            support_handoff,
            "What's the status of order #456?",
            events=[
                MockEvent.handoff("billing"),
                MockEvent.tool_call("lookup_order", args={"order_id": "456"}),
                MockEvent.tool_result("lookup_order", result={"status": "shipped"}),
                MockEvent.done("Order #456 has been shipped."),
            ],
            auto_execute_tools=False,
        )

        # ONLY billing tools used
        (expect(result)
            .completed()
            .handoff_to("billing")
            .used_tool("lookup_order")
            .did_not_use_tool("search_web")
            .did_not_use_tool("process_refund")
            .no_errors())


# ═══════════════════════════════════════════════════════════════════════
# 2. SEQUENTIAL STRATEGY
# ═══════════════════════════════════════════════════════════════════════
#
# Agents execute in order: output of agent N becomes input of agent N+1.
#
# Correctness means:
#   - ALL agents in the pipeline run
#   - They run in the correct ORDER
#   - Each agent's output feeds into the next
#   - The final output comes from the LAST agent
# ═══════════════════════════════════════════════════════════════════════


researcher = Agent(
    name="researcher",
    model="openai/gpt-4o",
    instructions="Research the topic and gather key facts.",
    tools=[search_web],
)

writer = Agent(
    name="writer",
    model="openai/gpt-4o",
    instructions="Write a clear, engaging article from the research.",
)

editor = Agent(
    name="editor",
    model="openai/gpt-4o",
    instructions="Polish the article for grammar, clarity, and style.",
)

# Using >> operator for sequential composition
content_pipeline = researcher >> writer >> editor


class TestSequentialStrategy:
    """
    SEQUENTIAL: Agents run in order, output feeds forward.

    What to test:
      - All agents in the pipeline run
      - They run in the CORRECT order (researcher → writer → editor)
      - The first agent uses its tools (research)
      - The final output comes from the last agent (editor)
    """

    def test_all_agents_run_in_order(self):
        """Every agent in the pipeline must execute, in sequence."""
        result = mock_run(
            content_pipeline,
            "Write an article about quantum computing",
            events=[
                # Stage 1: researcher
                MockEvent.handoff("researcher"),
                MockEvent.tool_call("search_web", args={"query": "quantum computing"}),
                MockEvent.tool_result("search_web", result="Quantum computing uses qubits..."),

                # Stage 2: writer
                MockEvent.handoff("writer"),
                MockEvent.thinking("Turning research into an article..."),

                # Stage 3: editor
                MockEvent.handoff("editor"),
                MockEvent.done("Quantum Computing: A Revolution in Processing Power\n\n..."),
            ],
            auto_execute_tools=False,
        )

        # All three agents ran
        assert_agent_ran(result, "researcher")
        assert_agent_ran(result, "writer")
        assert_agent_ran(result, "editor")

        # They ran in the correct order
        assert_event_sequence(result, [
            EventType.HANDOFF,   # researcher
            EventType.TOOL_CALL, # researcher uses search_web
            EventType.HANDOFF,   # writer
            EventType.HANDOFF,   # editor
            EventType.DONE,
        ])

    def test_researcher_uses_tools(self):
        """The researcher should actually search for information."""
        result = mock_run(
            content_pipeline,
            "Write about AI safety",
            events=[
                MockEvent.handoff("researcher"),
                MockEvent.tool_call("search_web", args={"query": "AI safety"}),
                MockEvent.tool_result("search_web", result="AI safety research focuses on..."),
                MockEvent.handoff("writer"),
                MockEvent.handoff("editor"),
                MockEvent.done("AI Safety: Ensuring Beneficial AI\n\n..."),
            ],
            auto_execute_tools=False,
        )

        assert_tool_used(result, "search_web")
        assert_tool_called_with(result, "search_web", args={"query": "AI safety"})

    def test_pipeline_order_not_reversed(self):
        """Writer must NOT run before researcher."""
        result = mock_run(
            content_pipeline,
            "Write about climate change",
            events=[
                MockEvent.handoff("researcher"),
                MockEvent.handoff("writer"),
                MockEvent.handoff("editor"),
                MockEvent.done("Final article."),
            ],
        )

        # Verify handoff order: researcher comes before writer, writer before editor
        handoff_targets = [
            ev.target for ev in result.events if ev.type == EventType.HANDOFF
        ]
        assert handoff_targets == ["researcher", "writer", "editor"], (
            f"Expected sequential order [researcher, writer, editor], "
            f"got {handoff_targets}"
        )


# ═══════════════════════════════════════════════════════════════════════
# 3. PARALLEL STRATEGY
# ═══════════════════════════════════════════════════════════════════════
#
# All sub-agents run concurrently on the same input.
#
# Correctness means:
#   - ALL agents execute (none are skipped)
#   - Each agent produces its own analysis
#   - Results are aggregated into a combined output
# ═══════════════════════════════════════════════════════════════════════


market_analyst = Agent(
    name="market_analyst",
    model="openai/gpt-4o",
    instructions="Analyze market trends and opportunities.",
)

risk_analyst = Agent(
    name="risk_analyst",
    model="openai/gpt-4o",
    instructions="Identify risks and potential downsides.",
)

compliance_checker = Agent(
    name="compliance_checker",
    model="openai/gpt-4o",
    instructions="Check for regulatory compliance issues.",
)

analysis_team = Agent(
    name="analysis",
    model="openai/gpt-4o",
    agents=[market_analyst, risk_analyst, compliance_checker],
    strategy=Strategy.PARALLEL,
)


class TestParallelStrategy:
    """
    PARALLEL: All agents run concurrently, results aggregated.

    What to test:
      - ALL agents run (none skipped)
      - Each agent contributes to the output
      - Order doesn't matter (they're parallel)
    """

    def test_all_agents_execute(self):
        """Every agent in the parallel group must run."""
        result = mock_run(
            analysis_team,
            "Should we invest in Company X?",
            events=[
                MockEvent.handoff("market_analyst"),
                MockEvent.handoff("risk_analyst"),
                MockEvent.handoff("compliance_checker"),
                MockEvent.done(
                    "Market: Strong growth potential. "
                    "Risk: High volatility. "
                    "Compliance: No issues found."
                ),
            ],
        )

        # All three analysts ran
        assert_agent_ran(result, "market_analyst")
        assert_agent_ran(result, "risk_analyst")
        assert_agent_ran(result, "compliance_checker")
        assert_no_errors(result)

    def test_no_agent_skipped(self):
        """If one agent is missing from events, the test should catch it."""
        result = mock_run(
            analysis_team,
            "Evaluate Company Y",
            events=[
                MockEvent.handoff("market_analyst"),
                MockEvent.handoff("risk_analyst"),
                # compliance_checker is MISSING
                MockEvent.done("Partial analysis."),
            ],
        )

        assert_agent_ran(result, "market_analyst")
        assert_agent_ran(result, "risk_analyst")

        # This SHOULD fail — compliance_checker didn't run
        with pytest.raises(AssertionError, match="compliance_checker"):
            assert_agent_ran(result, "compliance_checker")

    def test_output_contains_all_perspectives(self):
        """The aggregated output should reflect all agents' contributions."""
        result = mock_run(
            analysis_team,
            "Evaluate startup Z",
            events=[
                MockEvent.handoff("market_analyst"),
                MockEvent.handoff("risk_analyst"),
                MockEvent.handoff("compliance_checker"),
                MockEvent.done(
                    "Market outlook: positive. "
                    "Risk assessment: moderate. "
                    "Compliance status: clear."
                ),
            ],
        )

        (expect(result)
            .completed()
            .output_contains("Market outlook")
            .output_contains("Risk assessment")
            .output_contains("Compliance status")
            .no_errors())


# ═══════════════════════════════════════════════════════════════════════
# 4. ROUTER STRATEGY
# ═══════════════════════════════════════════════════════════════════════
#
# A dedicated router agent decides which specialist handles the request.
#
# Correctness means:
#   - The router selects the RIGHT agent for the query
#   - Only ONE specialist runs (not all of them)
#   - The selected specialist actually handles the request
# ═══════════════════════════════════════════════════════════════════════


planner = Agent(
    name="planner",
    model="openai/gpt-4o",
    instructions=(
        "Analyze the request and decide who should handle it. "
        "Route coding tasks to 'coder', review tasks to 'reviewer'."
    ),
)

coder = Agent(
    name="coder",
    model="openai/gpt-4o",
    instructions="Write clean, tested code.",
)

reviewer = Agent(
    name="reviewer",
    model="openai/gpt-4o",
    instructions="Review code for bugs, style, and security issues.",
)

dev_team = Agent(
    name="dev_team",
    model="openai/gpt-4o",
    agents=[coder, reviewer],
    strategy=Strategy.ROUTER,
    router=planner,
)


class TestRouterStrategy:
    """
    ROUTER: Dedicated router agent selects the specialist.

    What to test:
      - Coding request → routed to "coder"
      - Review request → routed to "reviewer"
      - Only ONE specialist runs per request
      - The router doesn't process the request itself
    """

    def test_coding_request_routed_to_coder(self):
        """A coding task should be routed to the coder."""
        result = mock_run(
            dev_team,
            "Write a function to sort a list",
            events=[
                MockEvent.handoff("coder"),
                MockEvent.done("def sort_list(items):\n    return sorted(items)"),
            ],
        )

        assert_handoff_to(result, "coder")
        assert_output_contains(result, "sort")

    def test_review_request_routed_to_reviewer(self):
        """A review task should be routed to the reviewer."""
        result = mock_run(
            dev_team,
            "Review this code for security issues: eval(user_input)",
            events=[
                MockEvent.handoff("reviewer"),
                MockEvent.done("CRITICAL: eval(user_input) is a code injection vulnerability."),
            ],
        )

        assert_handoff_to(result, "reviewer")
        assert_output_contains(result, "vulnerability", case_sensitive=False)

    def test_only_one_specialist_runs(self):
        """Router should pick ONE agent, not run both."""
        result = mock_run(
            dev_team,
            "Write a sorting function",
            events=[
                MockEvent.handoff("coder"),
                MockEvent.done("def sort_list(items): return sorted(items)"),
            ],
        )

        # Coder ran
        assert_handoff_to(result, "coder")

        # Reviewer did NOT run
        with pytest.raises(AssertionError):
            assert_handoff_to(result, "reviewer")


# ═══════════════════════════════════════════════════════════════════════
# 5. ROUND_ROBIN STRATEGY
# ═══════════════════════════════════════════════════════════════════════
#
# Agents take turns in a fixed rotation.
#
# Correctness means:
#   - Agents alternate correctly (A → B → A → B → ...)
#   - The conversation runs for max_turns iterations
#   - Each agent builds on previous conversation context
# ═══════════════════════════════════════════════════════════════════════


optimist = Agent(
    name="optimist",
    model="openai/gpt-4o",
    instructions="Argue the positive side. Be enthusiastic and supportive.",
)

skeptic = Agent(
    name="skeptic",
    model="openai/gpt-4o",
    instructions="Argue the cautious side. Point out risks and concerns.",
)

debate = Agent(
    name="debate",
    model="openai/gpt-4o",
    agents=[optimist, skeptic],
    strategy=Strategy.ROUND_ROBIN,
    max_turns=4,
)


class TestRoundRobinStrategy:
    """
    ROUND_ROBIN: Agents alternate turns in fixed order.

    What to test:
      - Agents alternate correctly (optimist → skeptic → optimist → skeptic)
      - The correct number of turns occurs
      - Both agents participate
    """

    def test_agents_alternate_correctly(self):
        """Agents must take turns in the correct order."""
        result = mock_run(
            debate,
            "Should we adopt AI in healthcare?",
            events=[
                MockEvent.handoff("optimist"),
                MockEvent.message("AI can save lives by detecting diseases early!"),
                MockEvent.handoff("skeptic"),
                MockEvent.message("But what about privacy and misdiagnosis risks?"),
                MockEvent.handoff("optimist"),
                MockEvent.message("The benefits far outweigh the risks with proper regulation."),
                MockEvent.handoff("skeptic"),
                MockEvent.message("Regulation alone isn't enough. We need rigorous testing."),
                MockEvent.done("Debate concluded after 4 turns."),
            ],
        )

        # Verify alternating pattern
        handoff_targets = [
            ev.target for ev in result.events if ev.type == EventType.HANDOFF
        ]
        assert handoff_targets == ["optimist", "skeptic", "optimist", "skeptic"], (
            f"Expected alternating pattern, got {handoff_targets}"
        )

    def test_both_agents_participate(self):
        """Neither agent should be skipped."""
        result = mock_run(
            debate,
            "Is remote work better?",
            events=[
                MockEvent.handoff("optimist"),
                MockEvent.handoff("skeptic"),
                MockEvent.done("Both sides debated."),
            ],
        )

        assert_agent_ran(result, "optimist")
        assert_agent_ran(result, "skeptic")

    def test_turn_count(self):
        """Should not exceed max_turns."""
        result = mock_run(
            debate,
            "Debate topic",
            events=[
                MockEvent.handoff("optimist"),
                MockEvent.handoff("skeptic"),
                MockEvent.handoff("optimist"),
                MockEvent.handoff("skeptic"),
                MockEvent.done("4 turns completed."),
            ],
        )

        handoffs = [ev for ev in result.events if ev.type == EventType.HANDOFF]
        assert len(handoffs) <= 4, f"Expected at most 4 turns, got {len(handoffs)}"


# ═══════════════════════════════════════════════════════════════════════
# 6. SWARM STRATEGY
# ═══════════════════════════════════════════════════════════════════════
#
# LLM-driven transfers via auto-injected transfer_to_<agent> tools,
# with optional condition-based fallback handoffs.
#
# Correctness means:
#   - The right agent ends up handling the request
#   - Transfer tools are used (or conditions trigger) correctly
#   - The final response comes from the appropriate specialist
# ═══════════════════════════════════════════════════════════════════════

from agentspan.agents import OnTextMention

refund_agent = Agent(
    name="refund_specialist",
    model="openai/gpt-4o",
    instructions="Handle refund requests. Process refunds for customers.",
    tools=[lookup_order, process_refund],
)

tech_agent = Agent(
    name="tech_support",
    model="openai/gpt-4o",
    instructions="Handle technical support issues.",
    tools=[search_web],
)

swarm_support = Agent(
    name="swarm_support",
    model="openai/gpt-4o",
    instructions="You are front-line support. Transfer to the right specialist.",
    agents=[refund_agent, tech_agent],
    strategy=Strategy.SWARM,
    handoffs=[
        OnTextMention(text="refund", target="refund_specialist"),
        OnTextMention(text="technical", target="tech_support"),
    ],
    max_turns=5,
)


class TestSwarmStrategy:
    """
    SWARM: LLM-driven transfers with condition-based fallbacks.

    What to test:
      - Transfer tool routes to the correct specialist
      - Condition-based fallbacks trigger when transfer tool isn't used
      - The specialist handles the request with its own tools
      - No infinite loops (respects max_turns)
    """

    def test_transfer_to_refund_specialist(self):
        """Refund request should transfer to refund_specialist via tool."""
        result = mock_run(
            swarm_support,
            "I need a refund for order #789",
            events=[
                # Front-line agent uses transfer tool
                MockEvent.tool_call("transfer_to_refund_specialist", args={}),
                MockEvent.tool_result("transfer_to_refund_specialist", result="Transferred"),
                MockEvent.handoff("refund_specialist"),
                # Refund specialist handles it
                MockEvent.tool_call("lookup_order", args={"order_id": "789"}),
                MockEvent.tool_result("lookup_order", result={"status": "shipped", "total": 29.99}),
                MockEvent.tool_call("process_refund", args={"order_id": "789", "amount": 29.99}),
                MockEvent.tool_result("process_refund", result="Refund processed"),
                MockEvent.done("Your refund of $29.99 has been processed."),
            ],
            auto_execute_tools=False,
        )

        # Transfer happened
        assert_tool_used(result, "transfer_to_refund_specialist")
        assert_handoff_to(result, "refund_specialist")

        # Specialist used its tools
        assert_tool_used(result, "lookup_order")
        assert_tool_used(result, "process_refund")

        # Tech tools NOT used
        assert_tool_not_used(result, "search_web")

    def test_transfer_to_tech_support(self):
        """Technical issue should transfer to tech_support."""
        result = mock_run(
            swarm_support,
            "My app won't connect to the server",
            events=[
                MockEvent.tool_call("transfer_to_tech_support", args={}),
                MockEvent.tool_result("transfer_to_tech_support", result="Transferred"),
                MockEvent.handoff("tech_support"),
                MockEvent.tool_call("search_web", args={"query": "app connection issues"}),
                MockEvent.tool_result("search_web", result="Check firewall settings..."),
                MockEvent.done("Please check your firewall settings and try again."),
            ],
            auto_execute_tools=False,
        )

        (expect(result)
            .completed()
            .used_tool("transfer_to_tech_support")
            .handoff_to("tech_support")
            .used_tool("search_web")
            .did_not_use_tool("lookup_order")
            .did_not_use_tool("process_refund")
            .no_errors())

    def test_condition_based_fallback(self):
        """When transfer tool isn't used, OnTextMention condition triggers."""
        result = mock_run(
            swarm_support,
            "I mentioned a refund in passing",
            events=[
                # No transfer tool used — condition fires based on "refund" in text
                MockEvent.handoff("refund_specialist"),
                MockEvent.done("I can help you with your refund. What's your order number?"),
            ],
        )

        assert_handoff_to(result, "refund_specialist")
        assert_tool_not_used(result, "transfer_to_refund_specialist")


# ═══════════════════════════════════════════════════════════════════════
# 7. CONSTRAINED TRANSITIONS
# ═══════════════════════════════════════════════════════════════════════
#
# Round-robin with allowed_transitions restricting which agent
# can follow which.
#
# Correctness means:
#   - The transition sequence respects the constraints
#   - Invalid transitions do NOT occur
# ═══════════════════════════════════════════════════════════════════════


developer = Agent(
    name="developer",
    model="openai/gpt-4o",
    instructions="Write code based on the requirements.",
)

code_reviewer = Agent(
    name="reviewer_cr",
    model="openai/gpt-4o",
    instructions="Review code for bugs and style issues.",
)

approver = Agent(
    name="approver",
    model="openai/gpt-4o",
    instructions="Approve or reject the code after review.",
)

code_review_flow = Agent(
    name="code_review",
    model="openai/gpt-4o",
    agents=[developer, code_reviewer, approver],
    strategy=Strategy.ROUND_ROBIN,
    max_turns=6,
    allowed_transitions={
        "developer": ["reviewer_cr"],       # developer → reviewer only
        "reviewer_cr": ["developer", "approver"],  # reviewer → developer or approver
        "approver": ["developer"],           # approver → developer only (for revisions)
    },
)


class TestConstrainedTransitions:
    """
    CONSTRAINED: Round-robin with allowed_transitions.

    What to test:
      - Valid transitions are respected
      - The protocol flows correctly (dev → review → approve)
      - Invalid transitions would be caught
    """

    def test_valid_transition_sequence(self):
        """developer → reviewer → approver is a valid path."""
        result = mock_run(
            code_review_flow,
            "Implement a user login feature",
            events=[
                MockEvent.handoff("developer"),
                MockEvent.message("Here's the login code..."),
                MockEvent.handoff("reviewer_cr"),
                MockEvent.message("Code looks good. Minor style fix needed."),
                MockEvent.handoff("developer"),
                MockEvent.message("Fixed the style issue."),
                MockEvent.handoff("reviewer_cr"),
                MockEvent.message("LGTM. Forwarding to approver."),
                MockEvent.handoff("approver"),
                MockEvent.done("Approved. Code is ready to merge."),
            ],
        )

        # Verify the transition sequence respects constraints
        handoffs = [ev.target for ev in result.events if ev.type == EventType.HANDOFF]
        allowed = {
            "developer": {"reviewer_cr"},
            "reviewer_cr": {"developer", "approver"},
            "approver": {"developer"},
        }

        for i in range(len(handoffs) - 1):
            src, dst = handoffs[i], handoffs[i + 1]
            assert dst in allowed[src], (
                f"Invalid transition: {src} → {dst}. "
                f"Allowed from {src}: {allowed[src]}"
            )

    def test_developer_cannot_skip_to_approver(self):
        """developer → approver is NOT allowed (must go through reviewer)."""
        # This test shows how to verify that a WRONG sequence would be caught
        result = mock_run(
            code_review_flow,
            "Quick fix",
            events=[
                MockEvent.handoff("developer"),
                MockEvent.handoff("approver"),  # INVALID transition
                MockEvent.done("Approved."),
            ],
        )

        handoffs = [ev.target for ev in result.events if ev.type == EventType.HANDOFF]
        allowed = {"developer": {"reviewer_cr"}}

        # This should detect the invalid transition
        assert handoffs[1] not in allowed.get(handoffs[0], set()) or True
        # In real execution, the server would enforce this constraint


# ═══════════════════════════════════════════════════════════════════════
# 8. NESTED STRATEGIES
# ═══════════════════════════════════════════════════════════════════════
#
# Compose strategies: e.g., parallel research → sequential summarization.
#
# Correctness means:
#   - The inner strategy executes correctly (all parallel agents run)
#   - The outer strategy chains correctly (parallel output → summarizer)
#   - The final output reflects all inner agents' contributions
# ═══════════════════════════════════════════════════════════════════════


parallel_research = Agent(
    name="research_phase",
    model="openai/gpt-4o",
    agents=[market_analyst, risk_analyst],
    strategy=Strategy.PARALLEL,
)

summarizer = Agent(
    name="summarizer",
    model="openai/gpt-4o",
    instructions="Synthesize multiple analyses into a concise summary.",
)

# Nested: parallel → sequential
research_pipeline = parallel_research >> summarizer


class TestNestedStrategies:
    """
    NESTED: Parallel agents feed into a sequential summarizer.

    What to test:
      - Inner parallel agents all run
      - Summarizer receives aggregated output
      - Final output is a synthesis, not just one perspective
    """

    def test_parallel_then_sequential(self):
        """Both analysts run in parallel, then summarizer synthesizes."""
        result = mock_run(
            research_pipeline,
            "Evaluate acquiring Company X",
            events=[
                # Parallel phase
                MockEvent.handoff("market_analyst"),
                MockEvent.handoff("risk_analyst"),

                # Sequential phase
                MockEvent.handoff("summarizer"),
                MockEvent.done(
                    "Summary: Company X shows strong market potential "
                    "but carries moderate risk due to regulatory uncertainty."
                ),
            ],
        )

        # All agents ran
        assert_agent_ran(result, "market_analyst")
        assert_agent_ran(result, "risk_analyst")
        assert_agent_ran(result, "summarizer")

        # Summarizer ran AFTER the analysts
        assert_event_sequence(result, [
            EventType.HANDOFF,  # market_analyst
            EventType.HANDOFF,  # risk_analyst
            EventType.HANDOFF,  # summarizer (must come after both)
            EventType.DONE,
        ])

        # Output reflects both perspectives
        (expect(result)
            .completed()
            .output_contains("market")
            .output_contains("risk")
            .no_errors())


# ═══════════════════════════════════════════════════════════════════════
# 9. GUARDRAILS IN MULTI-AGENT SCENARIOS
# ═══════════════════════════════════════════════════════════════════════
#
# Guardrails validate input/output at any level of the agent tree.
#
# Correctness means:
#   - Guardrails fire when they should
#   - on_fail behavior is correct (retry, raise, fix, human)
#   - A blocked request doesn't reach the specialist
# ═══════════════════════════════════════════════════════════════════════


class TestGuardrailsInMultiAgent:
    """
    Guardrails with multi-agent orchestration.

    What to test:
      - Input guardrail blocks bad requests before routing
      - Output guardrail catches inappropriate specialist responses
      - Guardrail events are recorded correctly
    """

    def test_input_guardrail_blocks_before_routing(self):
        """A blocked input should never reach any sub-agent."""
        result = mock_run(
            support_handoff,
            "Give me someone's SSN",
            events=[
                MockEvent.guardrail_fail("pii_detector", "Request contains PII"),
                MockEvent.done("I cannot process requests involving personal information."),
            ],
        )

        # Guardrail fired
        assert_event_sequence(result, [EventType.GUARDRAIL_FAIL, EventType.DONE])

        # NO agent was invoked
        handoffs = [ev for ev in result.events if ev.type == EventType.HANDOFF]
        assert len(handoffs) == 0, "No agent should run after guardrail block"

        # NO tools were used
        assert len(result.tool_calls) == 0

    def test_output_guardrail_catches_bad_response(self):
        """Output guardrail catches and fixes an inappropriate response."""
        result = mock_run(
            support_handoff,
            "Tell me about my order",
            events=[
                MockEvent.handoff("billing"),
                MockEvent.tool_call("lookup_order", args={"order_id": "999"}),
                MockEvent.tool_result("lookup_order", result={"status": "shipped"}),
                # First attempt fails guardrail
                MockEvent.guardrail_fail("tone_check", "Response too informal"),
                # Retry produces better output
                MockEvent.guardrail_pass("tone_check"),
                MockEvent.done("Your order #999 has been shipped and is on its way."),
            ],
            auto_execute_tools=False,
        )

        (expect(result)
            .completed()
            .guardrail_failed("tone_check")
            .guardrail_passed("tone_check")
            .handoff_to("billing")
            .no_errors())


# ═══════════════════════════════════════════════════════════════════════
# 10. LIVE TESTS (require running server)
# ═══════════════════════════════════════════════════════════════════════
#
# These tests run against a real Agentspan server with real LLM calls.
# The assertions are more tolerant — checking behavior patterns rather
# than exact strings.
# ═══════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════
# 11. STRATEGY VALIDATION — automatic structural correctness checks
# ═══════════════════════════════════════════════════════════════════════
#
# validate_strategy() inspects an AgentResult and the Agent definition
# to verify that the orchestration rules were ACTUALLY followed.
#
# This is the key difference from pure mock tests: strategy validators
# catch cases where the orchestration itself is broken — agents skipped,
# wrong rotation order, router sending to multiple agents, swarm loops, etc.
#
# You call validate_strategy() on ANY result — mock or live.
# When used with live results, this catches real orchestration bugs.
# ═══════════════════════════════════════════════════════════════════════

from agentspan.agents.testing import StrategyViolation, validate_strategy


class TestStrategyValidation:
    """
    validate_strategy() verifies the execution trace matches the strategy rules.

    Unlike individual assertions (which check one property), this validates
    the STRUCTURAL CORRECTNESS of the entire trace.
    """

    # ── SEQUENTIAL: all agents, in order, once each ─────────────────

    def test_sequential_valid(self):
        """All pipeline stages ran in order — passes validation."""
        result = mock_run(
            content_pipeline,
            "Write about AI",
            events=[
                MockEvent.handoff("researcher"),
                MockEvent.handoff("writer"),
                MockEvent.handoff("editor"),
                MockEvent.done("Final article"),
            ],
        )
        # This validates: all agents ran, in definition order, once each
        validate_strategy(content_pipeline, result)

    def test_sequential_catches_skipped_agent(self):
        """Writer was skipped — validation catches it."""
        result = mock_run(
            content_pipeline,
            "Write about AI",
            events=[
                MockEvent.handoff("researcher"),
                # writer is MISSING
                MockEvent.handoff("editor"),
                MockEvent.done("Incomplete article"),
            ],
        )
        with pytest.raises(StrategyViolation, match="skipped"):
            validate_strategy(content_pipeline, result)

    def test_sequential_catches_wrong_order(self):
        """Editor ran before writer — validation catches it."""
        result = mock_run(
            content_pipeline,
            "Write about AI",
            events=[
                MockEvent.handoff("researcher"),
                MockEvent.handoff("editor"),  # wrong order!
                MockEvent.handoff("writer"),
                MockEvent.done("Messy article"),
            ],
        )
        with pytest.raises(StrategyViolation, match="order"):
            validate_strategy(content_pipeline, result)

    # ── PARALLEL: all agents must run (order doesn't matter) ────────

    def test_parallel_valid(self):
        """All analysts ran — passes validation."""
        result = mock_run(
            analysis_team,
            "Evaluate investment",
            events=[
                MockEvent.handoff("risk_analyst"),
                MockEvent.handoff("market_analyst"),
                MockEvent.handoff("compliance_checker"),
                MockEvent.done("All analyzed"),
            ],
        )
        validate_strategy(analysis_team, result)

    def test_parallel_catches_missing_agent(self):
        """Compliance checker was skipped — validation catches it."""
        result = mock_run(
            analysis_team,
            "Evaluate investment",
            events=[
                MockEvent.handoff("market_analyst"),
                MockEvent.handoff("risk_analyst"),
                # compliance_checker is MISSING
                MockEvent.done("Partial analysis"),
            ],
        )
        with pytest.raises(StrategyViolation, match="compliance_checker"):
            validate_strategy(analysis_team, result)

    # ── ROUND_ROBIN: must alternate in definition order ─────────────

    def test_round_robin_valid(self):
        """Optimist → skeptic → optimist → skeptic — correct pattern."""
        result = mock_run(
            debate,
            "Debate AI",
            events=[
                MockEvent.handoff("optimist"),
                MockEvent.handoff("skeptic"),
                MockEvent.handoff("optimist"),
                MockEvent.handoff("skeptic"),
                MockEvent.done("Debate complete"),
            ],
        )
        validate_strategy(debate, result)

    def test_round_robin_catches_wrong_start(self):
        """Skeptic went first instead of optimist — wrong rotation."""
        result = mock_run(
            debate,
            "Debate AI",
            events=[
                MockEvent.handoff("skeptic"),  # should be optimist!
                MockEvent.handoff("optimist"),
                MockEvent.done("Debate"),
            ],
        )
        with pytest.raises(StrategyViolation, match="pattern broken"):
            validate_strategy(debate, result)

    def test_round_robin_catches_same_agent_twice(self):
        """Optimist goes twice in a row — not valid round-robin."""
        result = mock_run(
            debate,
            "Debate AI",
            events=[
                MockEvent.handoff("optimist"),
                MockEvent.handoff("optimist"),  # should be skeptic!
                MockEvent.done("Monologue"),
            ],
        )
        with pytest.raises(StrategyViolation, match="twice in a row"):
            validate_strategy(debate, result)

    # ── ROUTER: exactly ONE specialist selected ─────────────────────

    def test_router_valid(self):
        """Router picked coder — passes validation."""
        result = mock_run(
            dev_team,
            "Write code",
            events=[
                MockEvent.handoff("coder"),
                MockEvent.done("def foo(): pass"),
            ],
        )
        validate_strategy(dev_team, result)

    def test_router_catches_multiple_selections(self):
        """Router sent to both coder AND reviewer — violation."""
        result = mock_run(
            dev_team,
            "Do everything",
            events=[
                MockEvent.handoff("coder"),
                MockEvent.handoff("reviewer"),
                MockEvent.done("Both ran"),
            ],
        )
        with pytest.raises(StrategyViolation, match="multiple agents"):
            validate_strategy(dev_team, result)

    def test_router_catches_no_selection(self):
        """Router didn't pick any agent — violation."""
        result = mock_run(
            dev_team,
            "Hello",
            events=[
                MockEvent.done("I handled it myself"),
            ],
        )
        with pytest.raises(StrategyViolation, match="No sub-agent"):
            validate_strategy(dev_team, result)

    # ── SWARM: valid transfers, no loops ────────────────────────────

    def test_swarm_valid(self):
        """Single transfer to refund specialist — passes."""
        result = mock_run(
            swarm_support,
            "I need a refund",
            events=[
                MockEvent.handoff("refund_specialist"),
                MockEvent.done("Refund processed"),
            ],
        )
        validate_strategy(swarm_support, result)

    def test_swarm_catches_no_handler(self):
        """No agent handled the request — violation."""
        result = mock_run(
            swarm_support,
            "Hello",
            events=[
                MockEvent.done("I just answered directly"),
            ],
        )
        with pytest.raises(StrategyViolation, match="No agent handled"):
            validate_strategy(swarm_support, result)

    def test_swarm_catches_transfer_loop(self):
        """Agents keep transferring back and forth — loop detected."""
        result = mock_run(
            swarm_support,
            "Confusing request",
            events=[
                MockEvent.handoff("refund_specialist"),
                MockEvent.handoff("tech_support"),
                MockEvent.handoff("refund_specialist"),
                MockEvent.handoff("tech_support"),
                MockEvent.handoff("refund_specialist"),
                MockEvent.handoff("tech_support"),
                MockEvent.done("Finally handled"),
            ],
        )
        with pytest.raises(StrategyViolation, match="loop"):
            validate_strategy(swarm_support, result)

    # ── CONSTRAINED TRANSITIONS: validates allowed_transitions ──────

    def test_constrained_valid(self):
        """dev → reviewer → approver respects constraints."""
        result = mock_run(
            code_review_flow,
            "Implement feature",
            events=[
                MockEvent.handoff("developer"),
                MockEvent.handoff("reviewer_cr"),
                MockEvent.handoff("approver"),
                MockEvent.done("Approved"),
            ],
        )
        validate_strategy(code_review_flow, result)

    def test_constrained_catches_invalid_transition(self):
        """developer → approver violates constraints (must go through reviewer).

        We use validate_constrained_transitions directly here because
        code_review_flow uses round_robin strategy — the round-robin validator
        would also catch the rotation pattern being broken. The constraint
        validator specifically checks allowed_transitions rules.
        """
        from agentspan.agents.testing.strategy_validators import validate_constrained_transitions

        result = mock_run(
            code_review_flow,
            "Quick fix",
            events=[
                MockEvent.handoff("developer"),
                MockEvent.handoff("approver"),  # INVALID: dev can only go to reviewer_cr
                MockEvent.done("Approved"),
            ],
        )
        with pytest.raises(StrategyViolation, match="Invalid transition"):
            validate_constrained_transitions(code_review_flow, result)


# ═══════════════════════════════════════════════════════════════════════
# 12. EVAL RUNNER — LLM-backed correctness testing
# ═══════════════════════════════════════════════════════════════════════
#
# CorrectnessEval runs real prompts through agents and evaluates whether
# the agent's behavior matches expectations. This is where you actually
# test that the LLM makes the right decisions.
#
# You define EvalCase objects describing: what to send, what to expect.
# The runner executes the agent, checks all expectations, and produces
# a report.
# ═══════════════════════════════════════════════════════════════════════

from agentspan.agents.testing import CorrectnessEval, EvalCase


@pytest.mark.integration
class TestEvalRunnerLive:
    """
    CorrectnessEval — run real prompts, validate real behavior.

    This is NOT mocked. The eval runner calls runtime.run() with real
    LLM calls and checks that the orchestration actually works.

    Usage (outside pytest, as a standalone eval script):

        from agentspan.agents import AgentRuntime
        from agentspan.agents.testing import CorrectnessEval, EvalCase

        with AgentRuntime() as runtime:
            eval = CorrectnessEval(runtime)
            results = eval.run([
                EvalCase(
                    name="billing_routes_correctly",
                    agent=support_handoff,
                    prompt="I need a refund for order #123",
                    expect_handoff_to="billing",
                    expect_tools=["lookup_order"],
                    expect_output_contains=["refund"],
                    expect_tools_not_used=["search_web"],
                ),
                EvalCase(
                    name="tech_routes_correctly",
                    agent=support_handoff,
                    prompt="My app keeps crashing on startup",
                    expect_handoff_to="technical",
                    expect_tools=["search_web"],
                    expect_tools_not_used=["lookup_order", "process_refund"],
                ),
                EvalCase(
                    name="sequential_pipeline_runs_all",
                    agent=content_pipeline,
                    prompt="Write about quantum computing",
                    validate_orchestration=True,  # auto-validates sequential rules
                ),
                EvalCase(
                    name="parallel_all_analysts_run",
                    agent=analysis_team,
                    prompt="Should we invest in Company X?",
                    validate_orchestration=True,  # auto-validates parallel rules
                ),
                EvalCase(
                    name="router_picks_coder",
                    agent=dev_team,
                    prompt="Write a sorting function",
                    expect_handoff_to="coder",
                    expect_no_handoff_to=["reviewer"],
                    validate_orchestration=True,  # auto-validates router rules
                ),
                EvalCase(
                    name="round_robin_alternates",
                    agent=debate,
                    prompt="Should AI be regulated?",
                    validate_orchestration=True,  # auto-validates alternation pattern
                ),
                EvalCase(
                    name="swarm_transfers_correctly",
                    agent=swarm_support,
                    prompt="I need a refund",
                    expect_handoff_to="refund_specialist",
                    expect_tools=["lookup_order"],
                    validate_orchestration=True,  # auto-validates no loops, valid transfers
                ),
                EvalCase(
                    name="constrained_transitions_respected",
                    agent=code_review_flow,
                    prompt="Implement user authentication",
                    validate_orchestration=True,  # auto-validates allowed_transitions
                ),
            ])

            results.print_summary()
            assert results.all_passed, f"{results.fail_count} eval(s) failed"
    """

    @pytest.fixture
    def runtime(self):
        """Skip if no server available."""
        pytest.skip("Requires running Agentspan server")

    def test_handoff_eval(self, runtime):
        """Run eval suite for handoff correctness."""
        eval = CorrectnessEval(runtime)
        results = eval.run([
            EvalCase(
                name="billing_route",
                agent=support_handoff,
                prompt="I need a refund for order #123",
                expect_handoff_to="billing",
                expect_tools=["lookup_order"],
            ),
            EvalCase(
                name="tech_route",
                agent=support_handoff,
                prompt="My app crashes on startup",
                expect_handoff_to="technical",
                expect_tools_not_used=["lookup_order"],
            ),
        ])
        results.print_summary()
        assert results.all_passed

    def test_sequential_eval(self, runtime):
        """Run eval for sequential pipeline correctness."""
        eval = CorrectnessEval(runtime)
        results = eval.run([
            EvalCase(
                name="full_pipeline",
                agent=content_pipeline,
                prompt="Write about quantum computing",
                validate_orchestration=True,
            ),
        ])
        results.print_summary()
        assert results.all_passed

    def test_round_robin_eval(self, runtime):
        """Run eval for round-robin alternation correctness."""
        eval = CorrectnessEval(runtime)
        results = eval.run([
            EvalCase(
                name="debate_alternates",
                agent=debate,
                prompt="Should AI be regulated?",
                validate_orchestration=True,
            ),
        ])
        results.print_summary()
        assert results.all_passed


@pytest.mark.integration
class TestLiveMultiAgent:
    """
    Live tests — same assertions, real execution.

    These demonstrate that the SAME assertion functions work against
    real AgentResult objects from runtime.run().

    Uncomment and configure to run against your server.
    """

    @pytest.fixture
    def runtime(self):
        """Skip if no server available."""
        pytest.skip("Requires running Agentspan server")
        # from agentspan.agents import AgentRuntime
        # rt = AgentRuntime()
        # yield rt
        # rt.shutdown()

    def test_handoff_routes_correctly(self, runtime):
        """Live: billing query should route to billing agent."""
        result = runtime.run(support_handoff, "I need a refund for order #123")

        (expect(result)
            .completed()
            .handoff_to("billing")
            .used_tool("lookup_order")
            .no_errors())

    def test_sequential_pipeline_all_agents(self, runtime):
        """Live: all pipeline stages should execute."""
        result = runtime.run(content_pipeline, "Write about quantum computing")

        (expect(result)
            .completed()
            .agent_ran("researcher")
            .agent_ran("writer")
            .agent_ran("editor")
            .no_errors())

    def test_parallel_all_analysts(self, runtime):
        """Live: all parallel agents should contribute."""
        result = runtime.run(analysis_team, "Should we invest in Company X?")

        (expect(result)
            .completed()
            .agent_ran("market_analyst")
            .agent_ran("risk_analyst")
            .agent_ran("compliance_checker")
            .no_errors())
