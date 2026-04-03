#!/usr/bin/env python3
"""
03 — Multi-Agent Strategy Tests
=================================

Test every orchestration strategy: handoff, sequential, parallel,
router, round-robin. Each section defines agents, scripts the
expected behavior with MockEvent, and asserts correctness.

Covers:
  - Strategy.HANDOFF — parent delegates to the right specialist
  - Strategy.SEQUENTIAL — pipeline with >> operator
  - Strategy.PARALLEL — concurrent execution, all agents must run
  - Strategy.ROUTER — dedicated planner picks one agent
  - Strategy.ROUND_ROBIN — agents alternate in fixed order

Run:
    pytest examples/mock_tests/03_multi_agent_strategies.py -v
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
    assert_tool_call_order,
    assert_tool_not_used,
    assert_tool_used,
    expect,
    mock_run,
)


# ═══════════════════════════════════════════════════════════════════════
# Shared tools
# ═══════════════════════════════════════════════════════════════════════


@tool
def search_docs(query: str) -> str:
    """Search documentation."""
    return f"Docs for: {query}"


@tool
def run_query(sql: str) -> list:
    """Execute a database query."""
    return [{"id": 1, "name": "result"}]


@tool
def send_notification(channel: str, message: str) -> str:
    """Send a notification."""
    return f"Sent to {channel}: {message}"


# ═══════════════════════════════════════════════════════════════════════
# 1. HANDOFF — parent picks the right specialist
# ═══════════════════════════════════════════════════════════════════════

docs_agent = Agent(
    name="docs_specialist",
    model="openai/gpt-4o",
    instructions="Answer documentation questions.",
    tools=[search_docs],
)

db_agent = Agent(
    name="db_specialist",
    model="openai/gpt-4o",
    instructions="Answer database questions.",
    tools=[run_query],
)

triage_agent = Agent(
    name="triage",
    model="openai/gpt-4o",
    instructions="Route questions to the right specialist.",
    agents=[docs_agent, db_agent],
    strategy=Strategy.HANDOFF,
)


class TestHandoff:
    """Parent LLM delegates to the right sub-agent."""

    def test_docs_question_routes_to_docs(self):
        result = mock_run(
            triage_agent,
            "How do I configure logging?",
            events=[
                MockEvent.handoff("docs_specialist"),
                MockEvent.tool_call("search_docs", args={"query": "configure logging"}),
                MockEvent.tool_result("search_docs", result="Set LOG_LEVEL=debug..."),
                MockEvent.done("Set LOG_LEVEL=debug in your config file."),
            ],
            auto_execute_tools=False,
        )

        assert_handoff_to(result, "docs_specialist")
        assert_tool_used(result, "search_docs")
        assert_tool_not_used(result, "run_query")

    def test_db_question_routes_to_db(self):
        result = mock_run(
            triage_agent,
            "How many users signed up today?",
            events=[
                MockEvent.handoff("db_specialist"),
                MockEvent.tool_call(
                    "run_query",
                    args={"sql": "SELECT count(*) FROM users WHERE created_at = today()"},
                ),
                MockEvent.tool_result("run_query", result=[{"count": 150}]),
                MockEvent.done("150 users signed up today."),
            ],
            auto_execute_tools=False,
        )

        assert_handoff_to(result, "db_specialist")
        assert_tool_used(result, "run_query")
        assert_tool_not_used(result, "search_docs")

    def test_no_cross_contamination(self):
        """DB specialist should never use docs tools."""
        result = mock_run(
            triage_agent,
            "Show me the user table schema",
            events=[
                MockEvent.handoff("db_specialist"),
                MockEvent.tool_call(
                    "run_query", args={"sql": "DESCRIBE users"}
                ),
                MockEvent.tool_result("run_query", result=[{"col": "id"}, {"col": "name"}]),
                MockEvent.done("The users table has columns: id, name."),
            ],
            auto_execute_tools=False,
        )

        (
            expect(result)
            .completed()
            .handoff_to("db_specialist")
            .used_tool("run_query")
            .did_not_use_tool("search_docs")
            .did_not_use_tool("send_notification")
            .no_errors()
        )


# ═══════════════════════════════════════════════════════════════════════
# 2. SEQUENTIAL — agents run in order, output feeds forward
# ═══════════════════════════════════════════════════════════════════════

researcher = Agent(
    name="researcher",
    model="openai/gpt-4o",
    instructions="Research the topic thoroughly.",
    tools=[search_docs],
)

drafter = Agent(
    name="drafter",
    model="openai/gpt-4o",
    instructions="Write a draft based on the research.",
)

reviewer = Agent(
    name="reviewer",
    model="openai/gpt-4o",
    instructions="Review and polish the draft.",
)

# >> operator composes a sequential pipeline
content_pipeline = researcher >> drafter >> reviewer


class TestSequential:
    """Agents execute in order: researcher → drafter → reviewer."""

    def test_all_agents_run_in_order(self):
        result = mock_run(
            content_pipeline,
            "Write a guide on API testing",
            events=[
                MockEvent.handoff("researcher"),
                MockEvent.tool_call("search_docs", args={"query": "API testing"}),
                MockEvent.tool_result("search_docs", result="API testing best practices..."),
                MockEvent.handoff("drafter"),
                MockEvent.thinking("Organizing the research into a guide..."),
                MockEvent.handoff("reviewer"),
                MockEvent.done("# API Testing Guide\n\n...polished content..."),
            ],
            auto_execute_tools=False,
        )

        assert_agent_ran(result, "researcher")
        assert_agent_ran(result, "drafter")
        assert_agent_ran(result, "reviewer")

        # Verify ordering
        assert_event_sequence(
            result,
            [
                EventType.HANDOFF,   # researcher
                EventType.TOOL_CALL, # researcher uses search_docs
                EventType.HANDOFF,   # drafter
                EventType.HANDOFF,   # reviewer
                EventType.DONE,
            ],
        )

    def test_pipeline_order_is_correct(self):
        """Handoff targets appear in definition order."""
        result = mock_run(
            content_pipeline,
            "Write about microservices",
            events=[
                MockEvent.handoff("researcher"),
                MockEvent.handoff("drafter"),
                MockEvent.handoff("reviewer"),
                MockEvent.done("Final article."),
            ],
        )

        handoff_targets = [
            ev.target for ev in result.events if ev.type == EventType.HANDOFF
        ]
        assert handoff_targets == ["researcher", "drafter", "reviewer"]


# ═══════════════════════════════════════════════════════════════════════
# 3. PARALLEL — all agents run concurrently
# ═══════════════════════════════════════════════════════════════════════

security_auditor = Agent(
    name="security_auditor",
    model="openai/gpt-4o",
    instructions="Audit for security vulnerabilities.",
)

performance_auditor = Agent(
    name="performance_auditor",
    model="openai/gpt-4o",
    instructions="Audit for performance bottlenecks.",
)

accessibility_auditor = Agent(
    name="accessibility_auditor",
    model="openai/gpt-4o",
    instructions="Audit for accessibility compliance.",
)

audit_team = Agent(
    name="audit",
    model="openai/gpt-4o",
    agents=[security_auditor, performance_auditor, accessibility_auditor],
    strategy=Strategy.PARALLEL,
)


class TestParallel:
    """All agents in the group must run — order doesn't matter."""

    def test_all_auditors_run(self):
        result = mock_run(
            audit_team,
            "Audit the checkout page",
            events=[
                MockEvent.handoff("security_auditor"),
                MockEvent.handoff("performance_auditor"),
                MockEvent.handoff("accessibility_auditor"),
                MockEvent.done(
                    "Security: No XSS issues. "
                    "Performance: Page loads in 1.2s. "
                    "Accessibility: Missing alt tags on 3 images."
                ),
            ],
        )

        assert_agent_ran(result, "security_auditor")
        assert_agent_ran(result, "performance_auditor")
        assert_agent_ran(result, "accessibility_auditor")
        assert_no_errors(result)

    def test_missing_agent_is_detectable(self):
        """If an agent is missing from events, assert_agent_ran catches it."""
        result = mock_run(
            audit_team,
            "Audit the login page",
            events=[
                MockEvent.handoff("security_auditor"),
                MockEvent.handoff("performance_auditor"),
                # accessibility_auditor is MISSING
                MockEvent.done("Partial audit."),
            ],
        )

        assert_agent_ran(result, "security_auditor")
        assert_agent_ran(result, "performance_auditor")

        with pytest.raises(AssertionError, match="accessibility_auditor"):
            assert_agent_ran(result, "accessibility_auditor")

    def test_output_reflects_all_perspectives(self):
        result = mock_run(
            audit_team,
            "Audit dashboard",
            events=[
                MockEvent.handoff("security_auditor"),
                MockEvent.handoff("performance_auditor"),
                MockEvent.handoff("accessibility_auditor"),
                MockEvent.done(
                    "Security: clean. Performance: fast. Accessibility: compliant."
                ),
            ],
        )

        (
            expect(result)
            .completed()
            .output_contains("Security")
            .output_contains("Performance")
            .output_contains("Accessibility")
            .no_errors()
        )


# ═══════════════════════════════════════════════════════════════════════
# 4. ROUTER — dedicated planner picks one specialist
# ═══════════════════════════════════════════════════════════════════════

planner = Agent(
    name="planner",
    model="openai/gpt-4o",
    instructions="Route bugs to backend, UI issues to frontend.",
)

backend_dev = Agent(
    name="backend",
    model="openai/gpt-4o",
    instructions="Fix backend/API bugs.",
    tools=[run_query],
)

frontend_dev = Agent(
    name="frontend",
    model="openai/gpt-4o",
    instructions="Fix frontend/UI bugs.",
)

bug_triage = Agent(
    name="bug_triage",
    model="openai/gpt-4o",
    agents=[backend_dev, frontend_dev],
    strategy=Strategy.ROUTER,
    router=planner,
)


class TestRouter:
    """Dedicated router agent picks exactly one specialist."""

    def test_api_bug_routes_to_backend(self):
        result = mock_run(
            bug_triage,
            "The /users endpoint returns 500",
            events=[
                MockEvent.handoff("backend"),
                MockEvent.tool_call("run_query", args={"sql": "SELECT * FROM error_log"}),
                MockEvent.tool_result("run_query", result=[{"error": "null pointer"}]),
                MockEvent.done("Fixed the null pointer in the users endpoint."),
            ],
            auto_execute_tools=False,
        )

        assert_handoff_to(result, "backend")
        assert_tool_used(result, "run_query")

    def test_ui_bug_routes_to_frontend(self):
        result = mock_run(
            bug_triage,
            "The submit button is invisible on mobile",
            events=[
                MockEvent.handoff("frontend"),
                MockEvent.done("Added responsive CSS for the submit button."),
            ],
        )

        assert_handoff_to(result, "frontend")
        assert_tool_not_used(result, "run_query")

    def test_only_one_specialist_runs(self):
        """Router must pick ONE agent, not both."""
        result = mock_run(
            bug_triage,
            "Fix the login page",
            events=[
                MockEvent.handoff("frontend"),
                MockEvent.done("Fixed the CSS."),
            ],
        )

        assert_handoff_to(result, "frontend")
        with pytest.raises(AssertionError):
            assert_handoff_to(result, "backend")


# ═══════════════════════════════════════════════════════════════════════
# 5. ROUND_ROBIN — agents alternate in fixed rotation
# ═══════════════════════════════════════════════════════════════════════

proposer = Agent(
    name="proposer",
    model="openai/gpt-4o",
    instructions="Propose solutions to the problem.",
)

critic = Agent(
    name="critic",
    model="openai/gpt-4o",
    instructions="Find flaws in the proposed solution.",
)

debate = Agent(
    name="design_review",
    model="openai/gpt-4o",
    agents=[proposer, critic],
    strategy=Strategy.ROUND_ROBIN,
    max_turns=4,
)


class TestRoundRobin:
    """Agents alternate: proposer → critic → proposer → critic."""

    def test_alternating_pattern(self):
        result = mock_run(
            debate,
            "How should we handle rate limiting?",
            events=[
                MockEvent.handoff("proposer"),
                MockEvent.message("Use a token bucket with 100 req/min."),
                MockEvent.handoff("critic"),
                MockEvent.message("What about burst traffic? 100 is too low."),
                MockEvent.handoff("proposer"),
                MockEvent.message("OK, 100 sustained + 200 burst with sliding window."),
                MockEvent.handoff("critic"),
                MockEvent.message("Better. But add per-user limits too."),
                MockEvent.done("Agreed: token bucket, 100/min sustained, 200 burst, per-user."),
            ],
        )

        handoffs = [ev.target for ev in result.events if ev.type == EventType.HANDOFF]
        assert handoffs == ["proposer", "critic", "proposer", "critic"]

    def test_both_agents_participate(self):
        result = mock_run(
            debate,
            "Should we use GraphQL or REST?",
            events=[
                MockEvent.handoff("proposer"),
                MockEvent.handoff("critic"),
                MockEvent.done("Decision made."),
            ],
        )

        assert_agent_ran(result, "proposer")
        assert_agent_ran(result, "critic")

    def test_respects_max_turns(self):
        """Should not exceed max_turns=4 handoffs."""
        result = mock_run(
            debate,
            "Debate caching strategy",
            events=[
                MockEvent.handoff("proposer"),
                MockEvent.handoff("critic"),
                MockEvent.handoff("proposer"),
                MockEvent.handoff("critic"),
                MockEvent.done("4 turns completed."),
            ],
        )

        handoffs = [ev for ev in result.events if ev.type == EventType.HANDOFF]
        assert len(handoffs) <= 4
