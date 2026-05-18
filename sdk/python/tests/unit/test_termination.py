# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for termination conditions."""

import pytest

from agentspan.agents.termination import (
    MaxMessageTermination,
    StopMessageTermination,
    TerminationResult,
    TextMentionTermination,
    TokenUsageTermination,
    _AndTermination,
    _OrTermination,
)


class TestTerminationResult:
    """Test TerminationResult dataclass."""

    def test_not_terminated(self):
        result = TerminationResult(should_terminate=False)
        assert result.should_terminate is False
        assert result.reason == ""

    def test_terminated_with_reason(self):
        result = TerminationResult(should_terminate=True, reason="Max tokens exceeded")
        assert result.should_terminate is True
        assert result.reason == "Max tokens exceeded"


class TestTextMentionTermination:
    """Test TextMentionTermination."""

    def test_triggers_on_mention(self):
        cond = TextMentionTermination("DONE")
        ctx = {"result": "I'm all DONE now.", "messages": [], "iteration": 1}
        result = cond.should_terminate(ctx)
        assert result.should_terminate is True
        assert "DONE" in result.reason

    def test_case_insensitive_by_default(self):
        cond = TextMentionTermination("terminate")
        ctx = {"result": "We should TERMINATE now.", "messages": [], "iteration": 1}
        result = cond.should_terminate(ctx)
        assert result.should_terminate is True

    def test_case_sensitive(self):
        cond = TextMentionTermination("DONE", case_sensitive=True)
        ctx = {"result": "I'm done now.", "messages": [], "iteration": 1}
        result = cond.should_terminate(ctx)
        assert result.should_terminate is False

        ctx = {"result": "I'm DONE now.", "messages": [], "iteration": 1}
        result = cond.should_terminate(ctx)
        assert result.should_terminate is True

    def test_no_match(self):
        cond = TextMentionTermination("STOP")
        ctx = {"result": "The answer is 42.", "messages": [], "iteration": 1}
        result = cond.should_terminate(ctx)
        assert result.should_terminate is False

    def test_empty_result(self):
        cond = TextMentionTermination("DONE")
        ctx = {"result": "", "messages": [], "iteration": 0}
        result = cond.should_terminate(ctx)
        assert result.should_terminate is False

    def test_missing_result_key(self):
        cond = TextMentionTermination("DONE")
        ctx = {"messages": [], "iteration": 0}
        result = cond.should_terminate(ctx)
        assert result.should_terminate is False

    def test_repr(self):
        cond = TextMentionTermination("FINISH")
        assert "FINISH" in repr(cond)


class TestStopMessageTermination:
    """Test StopMessageTermination."""

    def test_exact_match(self):
        cond = StopMessageTermination("TERMINATE")
        ctx = {"result": "TERMINATE", "messages": [], "iteration": 1}
        result = cond.should_terminate(ctx)
        assert result.should_terminate is True

    def test_strips_whitespace(self):
        cond = StopMessageTermination("STOP")
        ctx = {"result": "  STOP  ", "messages": [], "iteration": 1}
        result = cond.should_terminate(ctx)
        assert result.should_terminate is True

    def test_no_match_on_substring(self):
        cond = StopMessageTermination("TERMINATE")
        ctx = {"result": "Please TERMINATE the process.", "messages": [], "iteration": 1}
        result = cond.should_terminate(ctx)
        assert result.should_terminate is False

    def test_default_message(self):
        cond = StopMessageTermination()
        ctx = {"result": "TERMINATE", "messages": [], "iteration": 1}
        result = cond.should_terminate(ctx)
        assert result.should_terminate is True

    def test_repr(self):
        cond = StopMessageTermination("DONE")
        assert "DONE" in repr(cond)


class TestMaxMessageTermination:
    """Test MaxMessageTermination."""

    def test_under_limit(self):
        cond = MaxMessageTermination(5)
        ctx = {"result": "", "messages": [{"role": "user"}] * 3, "iteration": 1}
        result = cond.should_terminate(ctx)
        assert result.should_terminate is False

    def test_at_limit(self):
        cond = MaxMessageTermination(5)
        ctx = {"result": "", "messages": [{"role": "user"}] * 5, "iteration": 1}
        result = cond.should_terminate(ctx)
        assert result.should_terminate is True

    def test_over_limit(self):
        cond = MaxMessageTermination(3)
        ctx = {"result": "", "messages": [{"role": "user"}] * 10, "iteration": 1}
        result = cond.should_terminate(ctx)
        assert result.should_terminate is True

    def test_empty_messages(self):
        cond = MaxMessageTermination(5)
        ctx = {"result": "", "messages": [], "iteration": 0}
        result = cond.should_terminate(ctx)
        assert result.should_terminate is False

    def test_invalid_max_raises(self):
        with pytest.raises(ValueError, match="max_messages must be >= 1"):
            MaxMessageTermination(0)

    def test_iteration_fallback_when_messages_empty(self):
        """Falls back to iteration count when messages list is empty."""
        cond = MaxMessageTermination(3)
        # iteration >= max_messages → should terminate
        ctx = {"result": "", "messages": [], "iteration": 3}
        result = cond.should_terminate(ctx)
        assert result.should_terminate is True

        # iteration < max_messages → should not terminate
        ctx = {"result": "", "messages": [], "iteration": 2}
        result = cond.should_terminate(ctx)
        assert result.should_terminate is False

    def test_messages_takes_priority_over_iteration(self):
        """When messages is populated, it takes priority over iteration."""
        cond = MaxMessageTermination(3)
        # messages count (5) >= max_messages, even though iteration is low
        ctx = {"result": "", "messages": [{"role": "user"}] * 5, "iteration": 1}
        result = cond.should_terminate(ctx)
        assert result.should_terminate is True

    def test_non_list_messages(self):
        cond = MaxMessageTermination(5)
        ctx = {"result": "", "messages": "not a list", "iteration": 0}
        result = cond.should_terminate(ctx)
        assert result.should_terminate is False

    def test_repr(self):
        cond = MaxMessageTermination(10)
        assert "10" in repr(cond)


class TestTokenUsageTermination:
    """Test TokenUsageTermination."""

    def test_total_tokens_exceeded(self):
        cond = TokenUsageTermination(max_total_tokens=1000)
        ctx = {
            "result": "",
            "messages": [],
            "iteration": 1,
            "token_usage": {"total_tokens": 1500, "prompt_tokens": 1000, "completion_tokens": 500},
        }
        result = cond.should_terminate(ctx)
        assert result.should_terminate is True

    def test_total_tokens_under(self):
        cond = TokenUsageTermination(max_total_tokens=1000)
        ctx = {
            "result": "",
            "messages": [],
            "iteration": 1,
            "token_usage": {"total_tokens": 500},
        }
        result = cond.should_terminate(ctx)
        assert result.should_terminate is False

    def test_prompt_tokens_exceeded(self):
        cond = TokenUsageTermination(max_prompt_tokens=500)
        ctx = {
            "result": "",
            "messages": [],
            "iteration": 1,
            "token_usage": {"prompt_tokens": 600, "completion_tokens": 100, "total_tokens": 700},
        }
        result = cond.should_terminate(ctx)
        assert result.should_terminate is True

    def test_completion_tokens_exceeded(self):
        cond = TokenUsageTermination(max_completion_tokens=200)
        ctx = {
            "result": "",
            "messages": [],
            "iteration": 1,
            "token_usage": {"prompt_tokens": 100, "completion_tokens": 300, "total_tokens": 400},
        }
        result = cond.should_terminate(ctx)
        assert result.should_terminate is True

    def test_no_token_usage_key(self):
        cond = TokenUsageTermination(max_total_tokens=1000)
        ctx = {"result": "", "messages": [], "iteration": 0}
        result = cond.should_terminate(ctx)
        assert result.should_terminate is False

    def test_invalid_token_usage_type(self):
        cond = TokenUsageTermination(max_total_tokens=1000)
        ctx = {"result": "", "messages": [], "iteration": 0, "token_usage": "bad"}
        result = cond.should_terminate(ctx)
        assert result.should_terminate is False

    def test_no_limits_raises(self):
        with pytest.raises(ValueError, match="At least one token limit"):
            TokenUsageTermination()

    def test_repr(self):
        cond = TokenUsageTermination(max_total_tokens=5000, max_prompt_tokens=3000)
        r = repr(cond)
        assert "5000" in r
        assert "3000" in r


class TestAndTermination:
    """Test AND composition of conditions."""

    def test_both_trigger(self):
        a = TextMentionTermination("DONE")
        b = MaxMessageTermination(3)
        combined = a & b
        ctx = {
            "result": "I'm DONE",
            "messages": [{"role": "user"}] * 5,
            "iteration": 1,
        }
        result = combined.should_terminate(ctx)
        assert result.should_terminate is True
        assert "AND" in result.reason

    def test_only_first_triggers(self):
        a = TextMentionTermination("DONE")
        b = MaxMessageTermination(10)
        combined = a & b
        ctx = {
            "result": "I'm DONE",
            "messages": [{"role": "user"}] * 3,
            "iteration": 1,
        }
        result = combined.should_terminate(ctx)
        assert result.should_terminate is False

    def test_only_second_triggers(self):
        a = TextMentionTermination("STOP")
        b = MaxMessageTermination(3)
        combined = a & b
        ctx = {
            "result": "Hello world",
            "messages": [{"role": "user"}] * 5,
            "iteration": 1,
        }
        result = combined.should_terminate(ctx)
        assert result.should_terminate is False

    def test_neither_triggers(self):
        a = TextMentionTermination("STOP")
        b = MaxMessageTermination(10)
        combined = a & b
        ctx = {
            "result": "Hello world",
            "messages": [{"role": "user"}] * 3,
            "iteration": 1,
        }
        result = combined.should_terminate(ctx)
        assert result.should_terminate is False

    def test_chained_and(self):
        a = TextMentionTermination("X")
        b = TextMentionTermination("Y")
        c = MaxMessageTermination(1)
        combined = a & b & c
        assert isinstance(combined, _AndTermination)
        assert len(combined.conditions) == 3

    def test_repr(self):
        a = TextMentionTermination("X")
        b = MaxMessageTermination(5)
        combined = a & b
        r = repr(combined)
        assert "TextMentionTermination" in r
        assert "MaxMessageTermination" in r


class TestOrTermination:
    """Test OR composition of conditions."""

    def test_first_triggers(self):
        a = TextMentionTermination("DONE")
        b = MaxMessageTermination(100)
        combined = a | b
        ctx = {
            "result": "I'm DONE",
            "messages": [{"role": "user"}] * 2,
            "iteration": 1,
        }
        result = combined.should_terminate(ctx)
        assert result.should_terminate is True

    def test_second_triggers(self):
        a = TextMentionTermination("STOP")
        b = MaxMessageTermination(3)
        combined = a | b
        ctx = {
            "result": "Hello world",
            "messages": [{"role": "user"}] * 5,
            "iteration": 1,
        }
        result = combined.should_terminate(ctx)
        assert result.should_terminate is True

    def test_neither_triggers(self):
        a = TextMentionTermination("STOP")
        b = MaxMessageTermination(100)
        combined = a | b
        ctx = {
            "result": "Hello world",
            "messages": [{"role": "user"}] * 3,
            "iteration": 1,
        }
        result = combined.should_terminate(ctx)
        assert result.should_terminate is False

    def test_chained_or(self):
        a = TextMentionTermination("X")
        b = TextMentionTermination("Y")
        c = StopMessageTermination("Z")
        combined = a | b | c
        assert isinstance(combined, _OrTermination)
        assert len(combined.conditions) == 3

    def test_repr(self):
        a = TextMentionTermination("X")
        b = MaxMessageTermination(5)
        combined = a | b
        r = repr(combined)
        assert "TextMentionTermination" in r
        assert "MaxMessageTermination" in r


class TestMixedComposition:
    """Test mixing AND and OR in the same expression."""

    def test_or_of_ands(self):
        # (text AND max_msg) OR stop_msg
        cond = (TextMentionTermination("DONE") & MaxMessageTermination(3)) | StopMessageTermination(
            "QUIT"
        )

        # Only stop_msg triggers
        ctx = {"result": "QUIT", "messages": [], "iteration": 1}
        assert cond.should_terminate(ctx).should_terminate is True

        # Only text triggers, but not enough messages for AND
        ctx = {"result": "DONE", "messages": [{"role": "user"}], "iteration": 1}
        assert cond.should_terminate(ctx).should_terminate is False

        # Both text AND max_msg trigger → AND is satisfied → OR passes
        ctx = {"result": "DONE", "messages": [{"role": "user"}] * 5, "iteration": 1}
        assert cond.should_terminate(ctx).should_terminate is True

    def test_and_of_ors(self):
        # (text OR stop_msg) AND max_msg
        cond = (
            TextMentionTermination("DONE") | StopMessageTermination("QUIT")
        ) & MaxMessageTermination(3)

        # text triggers but max_msg doesn't
        ctx = {"result": "DONE", "messages": [{"role": "user"}], "iteration": 1}
        assert cond.should_terminate(ctx).should_terminate is False

        # text triggers and max_msg triggers
        ctx = {"result": "DONE", "messages": [{"role": "user"}] * 5, "iteration": 1}
        assert cond.should_terminate(ctx).should_terminate is True
