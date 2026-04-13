"""Tests for TUI event formatting — verifies tool events translate to user-friendly messages.

Each test exercises the real format_event / render_* functions with synthetic event
objects.  No mocks, no LLM calls — all assertions are deterministic string checks.
"""

from __future__ import annotations

from typing import Any, Optional

from autopilot.tui.events import (
    _parse_validation_result,
    format_event,
    render_agent_table,
    render_spec_box,
    render_welcome,
)


# ---------------------------------------------------------------------------
# Lightweight event stub — mirrors the real SDK event interface
# ---------------------------------------------------------------------------


from agentspan.agents import AgentEvent, EventType


# ---------------------------------------------------------------------------
# Test: expand_prompt events
# ---------------------------------------------------------------------------


class TestExpandPromptFormatting:
    """Verify expand_prompt tool call/result produce user-friendly messages."""

    def test_expand_prompt_call_shows_expanding_message(self):
        event = AgentEvent(
            type=EventType.TOOL_CALL,
            tool_name="expand_prompt",
            args={"seed_prompt": "scan my emails"},
        )
        result = format_event(event)
        assert "Expanding your request" in result

    def test_expand_prompt_result_shows_checkmark(self):
        event = AgentEvent(
            type=EventType.TOOL_RESULT,
            tool_name="expand_prompt",
            result="template text here",
        )
        result = format_event(event)
        assert "\u2713" in result  # checkmark
        assert "Generated specification" in result


# ---------------------------------------------------------------------------
# Test: validation gate results (PASS / FAIL)
# ---------------------------------------------------------------------------


class TestValidationFormatting:
    """Verify validation gates produce checkmark on PASS, warning on FAIL."""

    def test_validate_spec_pass(self):
        event = AgentEvent(
            type=EventType.TOOL_RESULT,
            tool_name="validate_spec",
            result="PASS",
        )
        result = format_event(event)
        assert "\u2713" in result
        assert "Specification valid" in result

    def test_validate_spec_fail(self):
        event = AgentEvent(
            type=EventType.TOOL_RESULT,
            tool_name="validate_spec",
            result="FAIL: name is missing; instructions are empty",
        )
        result = format_event(event)
        assert "\u2717" in result  # cross
        assert "Specification issue" in result
        assert "name is missing" in result

    def test_validate_code_pass(self):
        event = AgentEvent(
            type=EventType.TOOL_RESULT,
            tool_name="validate_code",
            result="PASS",
        )
        result = format_event(event)
        assert "\u2713" in result
        assert "Code validated" in result

    def test_validate_code_fail(self):
        event = AgentEvent(
            type=EventType.TOOL_RESULT,
            tool_name="validate_code",
            result="FAIL: syntax error in worker.py",
        )
        result = format_event(event)
        assert "\u2717" in result
        assert "Code issue" in result

    def test_validate_integrations_pass(self):
        event = AgentEvent(
            type=EventType.TOOL_RESULT,
            tool_name="validate_integrations",
            result="PASS",
        )
        result = format_event(event)
        assert "\u2713" in result
        assert "Integrations available" in result

    def test_validate_integrations_fail_missing_credential(self):
        event = AgentEvent(
            type=EventType.TOOL_RESULT,
            tool_name="validate_integrations",
            result="FAIL: missing credentials: GMAIL_ACCESS_TOKEN",
        )
        result = format_event(event)
        assert "\u26a0" in result  # warning
        assert "GMAIL_ACCESS_TOKEN" in result

    def test_validate_deployment_pass(self):
        event = AgentEvent(
            type=EventType.TOOL_RESULT,
            tool_name="validate_deployment",
            result="PASS",
        )
        result = format_event(event)
        assert "\u2713" in result
        assert "Deployment check passed" in result

    def test_validate_deployment_fail(self):
        event = AgentEvent(
            type=EventType.TOOL_RESULT,
            tool_name="validate_deployment",
            result="FAIL: LoaderError -- missing workers/",
        )
        result = format_event(event)
        assert "\u2717" in result
        assert "Deployment issue" in result


# ---------------------------------------------------------------------------
# Test: _parse_validation_result helper
# ---------------------------------------------------------------------------


class TestParseValidationResult:
    """Test the PASS/FAIL parser directly."""

    def test_parse_pass(self):
        passed, detail = _parse_validation_result("PASS")
        assert passed is True
        assert detail == ""

    def test_parse_fail_with_reason(self):
        passed, detail = _parse_validation_result("FAIL: something broke")
        assert passed is False
        assert detail == "something broke"

    def test_parse_unexpected_string(self):
        passed, detail = _parse_validation_result("UNKNOWN")
        assert passed is False
        assert detail == "UNKNOWN"


# ---------------------------------------------------------------------------
# Test: deploy_agent events
# ---------------------------------------------------------------------------


class TestDeployAgentFormatting:
    """Verify deploy_agent events produce proper progress messages."""

    def test_deploy_call_shows_deploying(self):
        event = AgentEvent(
            type=EventType.TOOL_CALL,
            tool_name="deploy_agent",
            args={"agent_name": "email_monitor"},
        )
        result = format_event(event)
        assert "Deploying" in result
        assert "email_monitor" in result

    def test_deploy_result_success_shows_execution_id(self):
        event = AgentEvent(
            type=EventType.TOOL_RESULT,
            tool_name="deploy_agent",
            result="Agent 'email_monitor' deployed successfully.\nExecution ID: abc123\nStatus: ACTIVE",
        )
        result = format_event(event)
        assert "\u2713" in result
        assert "deployed" in result.lower()
        assert "abc123" in result

    def test_deploy_result_failure(self):
        event = AgentEvent(
            type=EventType.TOOL_RESULT,
            tool_name="deploy_agent",
            result="Error deploying agent 'email_monitor': connection refused",
        )
        result = format_event(event)
        assert "\u2717" in result
        assert "failed" in result.lower()


# ---------------------------------------------------------------------------
# Test: acquire_credentials events
# ---------------------------------------------------------------------------


class TestAcquireCredentialsFormatting:
    """Verify credential events produce proper messages."""

    def test_acquire_call_shows_setting_up(self):
        event = AgentEvent(
            type=EventType.TOOL_CALL,
            tool_name="acquire_credentials",
            args={"credential_name": "GMAIL_ACCESS_TOKEN"},
        )
        result = format_event(event)
        assert "Setting up credentials" in result
        assert "GMAIL_ACCESS_TOKEN" in result

    def test_acquire_result_success(self):
        event = AgentEvent(
            type=EventType.TOOL_RESULT,
            tool_name="acquire_credentials",
            result="GMAIL_ACCESS_TOKEN acquired and stored successfully.",
        )
        result = format_event(event)
        assert "\u2713" in result
        assert "acquired" in result.lower()


# ---------------------------------------------------------------------------
# Test: reply_to_user (clean display)
# ---------------------------------------------------------------------------


class TestReplyToUserFormatting:
    """Verify reply_to_user shows the message cleanly."""

    def test_reply_call_shows_message(self):
        event = AgentEvent(
            type=EventType.TOOL_CALL,
            tool_name="reply_to_user",
            args={"message": "I'll set this up for you."},
        )
        result = format_event(event)
        assert "Claw" in result
        assert "I'll set this up for you." in result

    def test_reply_result_suppressed(self):
        event = AgentEvent(
            type=EventType.TOOL_RESULT,
            tool_name="reply_to_user",
            result="ok",
        )
        result = format_event(event)
        assert result == ""


# ---------------------------------------------------------------------------
# Test: web_search
# ---------------------------------------------------------------------------


class TestWebSearchFormatting:
    """Verify web_search events show the query."""

    def test_web_search_call_shows_query(self):
        event = AgentEvent(
            type=EventType.TOOL_CALL,
            tool_name="web_search",
            args={"query": "best email APIs"},
        )
        result = format_event(event)
        assert "Searching" in result
        assert "best email APIs" in result


# ---------------------------------------------------------------------------
# Test: wait_for_message (suppressed)
# ---------------------------------------------------------------------------


class TestWaitForMessageSuppressed:
    """wait_for_message should produce no output."""

    def test_wait_call_suppressed(self):
        event = AgentEvent(
            type=EventType.TOOL_CALL,
            tool_name="wait_for_message",
            args={},
        )
        result = format_event(event)
        assert result == ""

    def test_wait_result_suppressed(self):
        event = AgentEvent(
            type=EventType.TOOL_RESULT,
            tool_name="wait_for_message",
            result={"text": "hello"},
        )
        result = format_event(event)
        assert result == ""


# ---------------------------------------------------------------------------
# Test: unknown tools show "Working..."
# ---------------------------------------------------------------------------


class TestUnknownToolFormatting:
    """Unknown tools should show 'Working...' instead of raw tool names."""

    def test_unknown_tool_shows_working(self):
        event = AgentEvent(
            type=EventType.TOOL_CALL,
            tool_name="some_internal_tool",
            args={"foo": "bar"},
        )
        result = format_event(event)
        assert "Working..." in result
        # Must NOT expose the raw tool name
        assert "some_internal_tool" not in result


# ---------------------------------------------------------------------------
# Test: THINKING events (suppressed in new UX)
# ---------------------------------------------------------------------------


class TestThinkingSuppressed:
    """THINKING events should be suppressed from user view."""

    def test_thinking_suppressed(self):
        event = AgentEvent(
            type=EventType.THINKING,
            content="Let me think about this...",
        )
        result = format_event(event)
        assert result == ""


# ---------------------------------------------------------------------------
# Test: ERROR events
# ---------------------------------------------------------------------------


class TestErrorFormatting:
    """ERROR events should show the error content clearly."""

    def test_error_shows_content(self):
        event = AgentEvent(
            type=EventType.ERROR,
            content="Connection refused to server",
        )
        result = format_event(event)
        assert "\u2717" in result
        assert "Connection refused" in result


# ---------------------------------------------------------------------------
# Test: render_spec_box
# ---------------------------------------------------------------------------


class TestRenderSpecBox:
    """Test the agent spec summary box rendering."""

    def test_spec_box_contains_agent_name(self):
        spec = {
            "name": "email_response_monitor",
            "trigger": {"type": "cron", "schedule": "0 9,18 * * *"},
            "tools": ["builtin:gmail"],
            "credentials": ["GMAIL_ACCESS_TOKEN"],
            "instructions": "- Fetch unread emails\n- Generate draft replies",
        }
        result = render_spec_box(spec)
        assert "email_response_monitor" in result

    def test_spec_box_contains_schedule(self):
        spec = {
            "name": "test_agent",
            "trigger": {"type": "cron", "schedule": "0 9 * * *"},
        }
        result = render_spec_box(spec)
        assert "0 9 * * *" in result

    def test_spec_box_contains_box_drawing_chars(self):
        spec = {"name": "test_agent"}
        result = render_spec_box(spec)
        assert "\u250c" in result  # top-left
        assert "\u2510" in result  # top-right
        assert "\u2514" in result  # bottom-left
        assert "\u2518" in result  # bottom-right
        assert "\u2502" in result  # vertical

    def test_spec_box_contains_credentials(self):
        spec = {
            "name": "my_agent",
            "credentials": ["GMAIL_ACCESS_TOKEN", "SLACK_BOT_TOKEN"],
        }
        result = render_spec_box(spec)
        assert "GMAIL_ACCESS_TOKEN" in result
        assert "SLACK_BOT_TOKEN" in result

    def test_spec_box_with_empty_spec(self):
        """Empty spec should not crash."""
        result = render_spec_box({})
        assert "\u250c" in result
        assert "\u2518" in result


# ---------------------------------------------------------------------------
# Test: render_welcome
# ---------------------------------------------------------------------------


class TestRenderWelcome:
    """Test the welcome screen rendering."""

    def test_welcome_renders_without_error(self):
        result = render_welcome()
        assert isinstance(result, str)
        assert len(result) > 50

    def test_welcome_contains_claw_branding(self):
        result = render_welcome()
        assert "Claw" in result

    def test_welcome_contains_help_hint(self):
        result = render_welcome()
        assert "/help" in result
        assert "/dashboard" in result

    def test_welcome_contains_box_drawing(self):
        result = render_welcome()
        assert "\u2554" in result  # double top-left
        assert "\u2557" in result  # double top-right
        assert "\u255a" in result  # double bottom-left
        assert "\u255d" in result  # double bottom-right

    def test_welcome_with_session_id(self):
        result = render_welcome(session_id="abc123def456ghi789")
        assert "Session:" in result
        assert "abc123def456ghi7" in result  # truncated to 16 chars

    def test_welcome_without_session_id(self):
        result = render_welcome(session_id="")
        assert "Session:" not in result

    def test_welcome_contains_description_prompt(self):
        result = render_welcome()
        assert "Describe what you want automated" in result


# ---------------------------------------------------------------------------
# Test: render_agent_table
# ---------------------------------------------------------------------------


class TestRenderAgentTable:
    """Test agent list table rendering."""

    def test_agent_table_renders(self):
        raw = "Agents:\n\nemail_monitor                ACTIVE     exec=abc123...\ndocs_reviewer                PAUSED     exec=---"
        result = render_agent_table(raw)
        assert "Name" in result
        assert "Status" in result

    def test_agent_table_short_input(self):
        """Short input should pass through without crashing."""
        result = render_agent_table("No agents found.")
        assert "No agents found." in result


# ---------------------------------------------------------------------------
# Test: signal_agent events
# ---------------------------------------------------------------------------


class TestSignalAgentFormatting:
    """Verify signal_agent events produce proper messages."""

    def test_signal_call(self):
        event = AgentEvent(
            type=EventType.TOOL_CALL,
            tool_name="signal_agent",
            args={"agent_name": "email_monitor", "message": "skip newsletters"},
        )
        result = format_event(event)
        assert "signal" in result.lower()
        assert "email_monitor" in result

    def test_signal_result_success(self):
        event = AgentEvent(
            type=EventType.TOOL_RESULT,
            tool_name="signal_agent",
            result="Signal sent to 'email_monitor': skip newsletters",
        )
        result = format_event(event)
        assert "\u2713" in result
        assert "email_monitor" in result


# ---------------------------------------------------------------------------
# Test: generate_agent events
# ---------------------------------------------------------------------------


class TestGenerateAgentFormatting:
    """Verify generate_agent events produce proper messages."""

    def test_generate_call_shows_building(self):
        event = AgentEvent(
            type=EventType.TOOL_CALL,
            tool_name="generate_agent",
            args={"agent_name": "email_monitor", "spec_yaml": "..."},
        )
        result = format_event(event)
        assert "Building agent" in result

    def test_generate_result_success(self):
        event = AgentEvent(
            type=EventType.TOOL_RESULT,
            tool_name="generate_agent",
            result="Agent 'email_monitor' created successfully.\nDirectory: /tmp/...",
        )
        result = format_event(event)
        assert "\u2713" in result
        assert "Agent files created" in result


# ---------------------------------------------------------------------------
# Test: list_agents events
# ---------------------------------------------------------------------------


class TestListAgentsFormatting:
    """Verify list_agents events render as tables."""

    def test_list_agents_call_suppressed(self):
        event = AgentEvent(
            type=EventType.TOOL_CALL,
            tool_name="list_agents",
            args={},
        )
        result = format_event(event)
        assert result == ""

    def test_list_agents_no_agents(self):
        event = AgentEvent(
            type=EventType.TOOL_RESULT,
            tool_name="list_agents",
            result="No agents found.",
        )
        result = format_event(event)
        assert "No agents found." in result


# ---------------------------------------------------------------------------
# Test: guardrail events
# ---------------------------------------------------------------------------


class TestGuardrailFormatting:
    """Verify guardrail events produce proper messages."""

    def test_guardrail_pass(self):
        event = AgentEvent(
            type=EventType.GUARDRAIL_PASS,
            guardrail_name="output_safety",
        )
        result = format_event(event)
        assert "\u2713" in result
        assert "output_safety" in result

    def test_guardrail_fail(self):
        event = AgentEvent(
            type=EventType.GUARDRAIL_FAIL,
            guardrail_name="output_safety",
            content="contains PII",
        )
        result = format_event(event)
        assert "\u2717" in result
        assert "contains PII" in result
