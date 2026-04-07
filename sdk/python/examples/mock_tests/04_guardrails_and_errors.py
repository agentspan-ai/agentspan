#!/usr/bin/env python3
"""
04 — Guardrails, Errors, and Edge Cases
=========================================

Test safety features: input/output guardrails, error handling,
human-in-the-loop (HITL) pauses, and edge-case scenarios.

Covers:
  - Guardrail pass/fail events
  - Input guardrails blocking before agent runs
  - Output guardrails catching and retrying
  - Error events and failed status
  - HITL waiting events
  - Message events in conversation flow
  - assert_guardrail_passed / assert_guardrail_failed
  - assert_events_contain

Run:
    pytest examples/mock_tests/04_guardrails_and_errors.py -v
"""

import pytest

from agentspan.agents import Agent, Strategy, tool
from agentspan.agents.result import EventType
from agentspan.agents.testing import (
    MockEvent,
    assert_event_sequence,
    assert_guardrail_failed,
    assert_guardrail_passed,
    assert_handoff_to,
    assert_no_errors,
    assert_output_contains,
    assert_status,
    assert_tool_not_used,
    assert_tool_used,
    assert_events_contain,
    expect,
    mock_run,
)


# ── Tools ────────────────────────────────────────────────────────────


@tool
def query_user_data(user_id: str) -> dict:
    """Fetch user data from the database."""
    return {"user_id": user_id, "name": "Alice", "email": "alice@example.com"}


@tool
def update_user(user_id: str, field: str, value: str) -> str:
    """Update a user field."""
    return f"Updated {field} to {value} for user {user_id}"


@tool
def delete_account(user_id: str) -> str:
    """Permanently delete a user account."""
    return f"Account {user_id} deleted"


# ── Agents ───────────────────────────────────────────────────────────

support_agent = Agent(
    name="support",
    model="openai/gpt-4o",
    instructions="Help users manage their accounts. Never share raw PII.",
    tools=[query_user_data, update_user, delete_account],
)


# ═══════════════════════════════════════════════════════════════════════
# 1. GUARDRAIL TESTS
# ═══════════════════════════════════════════════════════════════════════


class TestInputGuardrails:
    """Input guardrails block bad requests before the agent acts."""

    def test_pii_request_blocked(self):
        """Asking for raw PII triggers the input guardrail."""
        result = mock_run(
            support_agent,
            "Give me Alice's SSN and credit card number",
            events=[
                MockEvent.guardrail_fail(
                    "pii_detector", "Request asks for sensitive PII"
                ),
                MockEvent.done(
                    "I cannot share sensitive personal information like SSNs or credit cards."
                ),
            ],
        )

        assert_guardrail_failed(result, "pii_detector")

        # No tools should have been called — guardrail blocked first
        assert_tool_not_used(result, "query_user_data")
        assert_tool_not_used(result, "update_user")

        # No handoffs happened
        handoffs = [ev for ev in result.events if ev.type == EventType.HANDOFF]
        assert len(handoffs) == 0

    def test_safe_request_passes(self):
        """Normal requests pass the guardrail and proceed."""
        result = mock_run(
            support_agent,
            "What's my account status?",
            events=[
                MockEvent.guardrail_pass("pii_detector"),
                MockEvent.tool_call("query_user_data", args={"user_id": "U-123"}),
                MockEvent.tool_result(
                    "query_user_data", result={"status": "active"}
                ),
                MockEvent.done("Your account is active."),
            ],
            auto_execute_tools=False,
        )

        assert_guardrail_passed(result, "pii_detector")
        assert_tool_used(result, "query_user_data")
        assert_no_errors(result)


class TestOutputGuardrails:
    """Output guardrails catch inappropriate responses and trigger retries."""

    def test_first_attempt_fails_retry_passes(self):
        """Agent's first response is too informal, gets retried."""
        result = mock_run(
            support_agent,
            "Update my email address",
            events=[
                MockEvent.tool_call(
                    "update_user",
                    args={"user_id": "U-123", "field": "email", "value": "new@example.com"},
                ),
                MockEvent.tool_result("update_user", result="Updated email"),
                # First response fails the tone guardrail
                MockEvent.guardrail_fail("tone_check", "Response too casual"),
                # Retry produces a professional response
                MockEvent.guardrail_pass("tone_check"),
                MockEvent.done(
                    "Your email has been successfully updated to new@example.com."
                ),
            ],
            auto_execute_tools=False,
        )

        (
            expect(result)
            .completed()
            .guardrail_failed("tone_check")
            .guardrail_passed("tone_check")
            .used_tool("update_user")
            .no_errors()
        )

    def test_multiple_guardrails(self):
        """Multiple guardrails can pass/fail independently."""
        result = mock_run(
            support_agent,
            "Delete my account",
            events=[
                MockEvent.guardrail_pass("auth_check"),
                MockEvent.guardrail_pass("rate_limit"),
                MockEvent.tool_call("delete_account", args={"user_id": "U-123"}),
                MockEvent.tool_result("delete_account", result="Deleted"),
                MockEvent.guardrail_pass("pii_scrubber"),
                MockEvent.done("Your account has been permanently deleted."),
            ],
            auto_execute_tools=False,
        )

        assert_guardrail_passed(result, "auth_check")
        assert_guardrail_passed(result, "rate_limit")
        assert_guardrail_passed(result, "pii_scrubber")


# ═══════════════════════════════════════════════════════════════════════
# 2. ERROR HANDLING
# ═══════════════════════════════════════════════════════════════════════


class TestErrorHandling:
    """Agent encounters errors during execution."""

    def test_tool_error(self):
        """A tool call results in an error event."""
        result = mock_run(
            support_agent,
            "Look up user XYZ",
            events=[
                MockEvent.tool_call("query_user_data", args={"user_id": "XYZ"}),
                MockEvent.error("User XYZ not found in database"),
            ],
            auto_execute_tools=False,
        )

        assert_status(result, "FAILED")
        expect(result).failed()

    def test_error_contains_message(self):
        """The error event has a descriptive message."""
        result = mock_run(
            support_agent,
            "Crash please",
            events=[
                MockEvent.error("Internal server error: connection timeout"),
            ],
        )

        assert_events_contain(result, EventType.ERROR)

    def test_no_errors_assertion_catches_errors(self):
        """assert_no_errors raises when an error event exists."""
        result = mock_run(
            support_agent,
            "Do something broken",
            events=[
                MockEvent.tool_call("query_user_data", args={"user_id": "bad"}),
                MockEvent.error("Database connection failed"),
            ],
            auto_execute_tools=False,
        )

        with pytest.raises(AssertionError):
            assert_no_errors(result)


# ═══════════════════════════════════════════════════════════════════════
# 3. HUMAN-IN-THE-LOOP (HITL)
# ═══════════════════════════════════════════════════════════════════════


class TestHumanInTheLoop:
    """Agent pauses for human approval before taking destructive actions."""

    def test_waiting_event_before_delete(self):
        """Agent pauses for human confirmation before deleting an account."""
        result = mock_run(
            support_agent,
            "Delete my account permanently",
            events=[
                MockEvent.waiting("Confirm: permanently delete account U-123?"),
                # Human approves
                MockEvent.tool_call("delete_account", args={"user_id": "U-123"}),
                MockEvent.tool_result("delete_account", result="Account deleted"),
                MockEvent.done("Your account has been permanently deleted."),
            ],
            auto_execute_tools=False,
        )

        # Waiting event was recorded
        assert_events_contain(result, EventType.WAITING)

        # After approval, the action proceeded
        assert_tool_used(result, "delete_account")
        assert_status(result, "COMPLETED")

    def test_waiting_then_rejection(self):
        """Human rejects — agent does NOT proceed with the action."""
        result = mock_run(
            support_agent,
            "Delete everything",
            events=[
                MockEvent.waiting("Confirm: delete all data?"),
                MockEvent.done("Action cancelled. Your data is safe."),
            ],
        )

        assert_events_contain(result, EventType.WAITING)
        assert_tool_not_used(result, "delete_account")
        assert_output_contains(result, "cancelled", case_sensitive=False)


# ═══════════════════════════════════════════════════════════════════════
# 4. GUARDRAILS IN MULTI-AGENT SCENARIOS
# ═══════════════════════════════════════════════════════════════════════

safe_agent = Agent(
    name="safe_handler",
    model="openai/gpt-4o",
    instructions="Handle safe requests.",
    tools=[query_user_data],
)

risky_agent = Agent(
    name="risky_handler",
    model="openai/gpt-4o",
    instructions="Handle requests requiring elevated permissions.",
    tools=[update_user, delete_account],
)

gated_support = Agent(
    name="gated_support",
    model="openai/gpt-4o",
    instructions="Route requests. Risky actions require guardrail approval.",
    agents=[safe_agent, risky_agent],
    strategy=Strategy.HANDOFF,
)


class TestGuardrailsInMultiAgent:
    """Guardrails interact with multi-agent routing."""

    def test_guardrail_blocks_before_routing(self):
        """A blocked input should never reach any sub-agent."""
        result = mock_run(
            gated_support,
            "Hack into admin account",
            events=[
                MockEvent.guardrail_fail("intent_classifier", "Malicious intent detected"),
                MockEvent.done("I cannot assist with unauthorized access."),
            ],
        )

        assert_guardrail_failed(result, "intent_classifier")

        # No agent was invoked
        handoffs = [ev for ev in result.events if ev.type == EventType.HANDOFF]
        assert len(handoffs) == 0

    def test_guardrail_passes_then_routes(self):
        """Safe requests pass guardrail, then route to the right agent."""
        result = mock_run(
            gated_support,
            "Update my display name",
            events=[
                MockEvent.guardrail_pass("intent_classifier"),
                MockEvent.handoff("risky_handler"),
                MockEvent.tool_call(
                    "update_user",
                    args={"user_id": "U-123", "field": "name", "value": "Bob"},
                ),
                MockEvent.tool_result("update_user", result="Updated"),
                MockEvent.done("Your display name has been updated to Bob."),
            ],
            auto_execute_tools=False,
        )

        assert_guardrail_passed(result, "intent_classifier")
        assert_handoff_to(result, "risky_handler")
        assert_tool_used(result, "update_user")

    def test_output_guardrail_on_sub_agent(self):
        """Output guardrail catches sub-agent leaking raw PII."""
        result = mock_run(
            gated_support,
            "Show me my profile",
            events=[
                MockEvent.handoff("safe_handler"),
                MockEvent.tool_call("query_user_data", args={"user_id": "U-123"}),
                MockEvent.tool_result(
                    "query_user_data",
                    result={"name": "Alice", "email": "alice@example.com", "ssn": "123-45-6789"},
                ),
                # Output guardrail catches the SSN leak
                MockEvent.guardrail_fail("pii_scrubber", "Response contains SSN"),
                MockEvent.guardrail_pass("pii_scrubber"),
                MockEvent.done("Your profile: Name: Alice, Email: alice@example.com."),
            ],
            auto_execute_tools=False,
        )

        (
            expect(result)
            .completed()
            .handoff_to("safe_handler")
            .guardrail_failed("pii_scrubber")
            .guardrail_passed("pii_scrubber")
            .output_contains("Alice")
            .no_errors()
        )

        # SSN should NOT be in the final output
        assert "123-45-6789" not in str(result.output)
