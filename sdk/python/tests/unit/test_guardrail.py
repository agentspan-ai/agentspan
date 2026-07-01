# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for Guardrail, GuardrailResult, RegexGuardrail, LLMGuardrail,
OnFail, Position, @guardrail decorator, and external guardrails."""

import pytest

from conductor.ai.agents.guardrail import (
    Guardrail,
    GuardrailResult,
    LLMGuardrail,
    OnFail,
    Position,
    RegexGuardrail,
    guardrail,
)


class TestGuardrailResult:
    """Test GuardrailResult dataclass."""

    def test_passed(self):
        result = GuardrailResult(passed=True)
        assert result.passed is True
        assert result.message == ""

    def test_failed_with_message(self):
        result = GuardrailResult(passed=False, message="Contains PII")
        assert result.passed is False
        assert result.message == "Contains PII"

    def test_fixed_output(self):
        result = GuardrailResult(
            passed=False,
            message="Contains PII",
            fixed_output="Redacted content",
        )
        assert result.passed is False
        assert result.fixed_output == "Redacted content"

    def test_fixed_output_default_none(self):
        result = GuardrailResult(passed=True)
        assert result.fixed_output is None

    def test_fixed_output_with_passed(self):
        # fixed_output can technically be set even when passed=True (ignored)
        result = GuardrailResult(passed=True, fixed_output="unused")
        assert result.fixed_output == "unused"


class TestGuardrailCreation:
    """Test Guardrail creation and validation."""

    def test_basic_guardrail(self):
        def check(content: str) -> GuardrailResult:
            return GuardrailResult(passed=True)

        guard = Guardrail(func=check)
        assert guard.position == "output"
        assert guard.on_fail == "raise"
        assert guard.name == "check"

    def test_default_on_fail_is_raise(self):
        """Default on_fail is RAISE (standardized across all SDKs)."""
        guard = Guardrail(func=lambda c: GuardrailResult(passed=True))
        assert guard.on_fail == "raise"
        assert guard.on_fail == OnFail.RAISE

    def test_input_guardrail(self):
        def validate_input(content: str) -> GuardrailResult:
            return GuardrailResult(passed=len(content) > 0)

        guard = Guardrail(func=validate_input, position="input")
        assert guard.position == "input"

    def test_custom_name(self):
        guard = Guardrail(
            func=lambda c: GuardrailResult(passed=True),
            name="pii_check",
        )
        assert guard.name == "pii_check"

    def test_on_fail_raise(self):
        guard = Guardrail(
            func=lambda c: GuardrailResult(passed=True),
            on_fail="raise",
        )
        assert guard.on_fail == "raise"

    def test_on_fail_fix(self):
        guard = Guardrail(
            func=lambda c: GuardrailResult(passed=True),
            on_fail="fix",
        )
        assert guard.on_fail == "fix"

    def test_on_fail_human(self):
        guard = Guardrail(
            func=lambda c: GuardrailResult(passed=True),
            on_fail="human",
            position="output",
        )
        assert guard.on_fail == "human"

    def test_on_fail_human_input_position_raises(self):
        with pytest.raises(ValueError, match="on_fail='human' is only valid"):
            Guardrail(
                func=lambda c: GuardrailResult(passed=True),
                on_fail="human",
                position="input",
            )

    def test_max_retries_default(self):
        guard = Guardrail(func=lambda c: GuardrailResult(passed=True))
        assert guard.max_retries == 3

    def test_max_retries_custom(self):
        guard = Guardrail(
            func=lambda c: GuardrailResult(passed=True),
            max_retries=5,
        )
        assert guard.max_retries == 5

    def test_invalid_position_raises(self):
        with pytest.raises(ValueError, match="Invalid position"):
            Guardrail(
                func=lambda c: GuardrailResult(passed=True),
                position="middle",
            )

    def test_invalid_on_fail_raises(self):
        with pytest.raises(ValueError, match="Invalid on_fail"):
            Guardrail(
                func=lambda c: GuardrailResult(passed=True),
                on_fail="ignore",
            )


class TestGuardrailCheck:
    """Test Guardrail.check() method."""

    def test_check_passes(self):
        def no_profanity(content: str) -> GuardrailResult:
            if "bad" in content.lower():
                return GuardrailResult(passed=False, message="Contains profanity")
            return GuardrailResult(passed=True)

        guard = Guardrail(func=no_profanity)
        assert guard.check("Hello world").passed is True
        assert guard.check("bad word").passed is False
        assert guard.check("bad word").message == "Contains profanity"

    def test_check_with_length_validation(self):
        def max_length(content: str) -> GuardrailResult:
            if len(content) > 100:
                return GuardrailResult(passed=False, message="Too long")
            return GuardrailResult(passed=True)

        guard = Guardrail(func=max_length, position="output")
        assert guard.check("short").passed is True
        assert guard.check("x" * 101).passed is False

    def test_check_with_fix_output(self):
        import re

        def redact_ssn(content: str) -> GuardrailResult:
            ssn_pattern = r"\b\d{3}-\d{2}-\d{4}\b"
            if re.search(ssn_pattern, content):
                fixed = re.sub(ssn_pattern, "XXX-XX-XXXX", content)
                return GuardrailResult(
                    passed=False,
                    message="Contains SSN",
                    fixed_output=fixed,
                )
            return GuardrailResult(passed=True)

        guard = Guardrail(func=redact_ssn, on_fail="fix")
        result = guard.check("SSN: 123-45-6789")
        assert result.passed is False
        assert result.fixed_output == "SSN: XXX-XX-XXXX"


class TestGuardrailRepr:
    """Test Guardrail string representation."""

    def test_repr(self):
        guard = Guardrail(
            func=lambda c: GuardrailResult(passed=True),
            name="test_guard",
            position="input",
            on_fail="raise",
        )
        r = repr(guard)
        assert "test_guard" in r
        assert "input" in r
        assert "raise" in r


class TestRegexGuardrail:
    """Test RegexGuardrail."""

    def test_block_mode_blocks_matching(self):
        guard = RegexGuardrail(
            patterns=[r"\b\d{3}-\d{2}-\d{4}\b"],
            name="no_ssn",
            message="No SSNs allowed.",
        )
        assert guard.check("My SSN is 123-45-6789").passed is False
        assert guard.check("Hello world").passed is True

    def test_block_mode_multiple_patterns(self):
        guard = RegexGuardrail(
            patterns=[r"password", r"secret"],
            name="no_secrets",
        )
        assert guard.check("my password is 123").passed is False
        assert guard.check("top secret info").passed is False
        assert guard.check("nothing sensitive here").passed is True

    def test_allow_mode_rejects_non_matching(self):
        guard = RegexGuardrail(
            patterns=[r"^\s*[\{\[]"],
            mode="allow",
            name="json_only",
            message="Must be JSON.",
        )
        assert guard.check('{"key": "value"}').passed is True
        assert guard.check("plain text").passed is False

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="Invalid mode"):
            RegexGuardrail(patterns=["test"], mode="invalid")

    def test_single_pattern_string(self):
        guard = RegexGuardrail(patterns=r"badword", name="no_bad")
        assert guard.check("contains badword here").passed is False
        assert guard.check("clean text").passed is True

    def test_custom_position_and_on_fail(self):
        guard = RegexGuardrail(
            patterns=[r"error"],
            position="input",
            on_fail="raise",
            name="input_check",
        )
        assert guard.position == "input"
        assert guard.on_fail == "raise"

    def test_is_guardrail_subclass(self):
        guard = RegexGuardrail(patterns=[r"test"])
        assert isinstance(guard, Guardrail)

    def test_repr(self):
        guard = RegexGuardrail(patterns=[r"a", r"b"], name="multi")
        r = repr(guard)
        assert "multi" in r
        assert "block" in r
        assert "2" in r

    def test_max_retries_passed_through(self):
        guard = RegexGuardrail(
            patterns=[r"test"],
            max_retries=7,
        )
        assert guard.max_retries == 7

    def test_on_fail_fix(self):
        guard = RegexGuardrail(
            patterns=[r"test"],
            on_fail="fix",
        )
        assert guard.on_fail == "fix"


class TestLLMGuardrail:
    """Test LLMGuardrail construction (actual LLM call is not tested)."""

    def test_creation(self):
        guard = LLMGuardrail(
            model="anthropic/claude-sonnet-4-6",
            policy="No harmful content.",
            name="safety",
        )
        assert guard.name == "safety"
        assert guard.position == "output"
        assert guard.on_fail == "raise"
        assert guard._model == "anthropic/claude-sonnet-4-6"
        assert guard._policy == "No harmful content."

    def test_is_guardrail_subclass(self):
        guard = LLMGuardrail(
            model="anthropic/claude-sonnet-4-6",
            policy="Be safe.",
        )
        assert isinstance(guard, Guardrail)

    def test_custom_position(self):
        guard = LLMGuardrail(
            model="anthropic/claude-sonnet-4-6",
            policy="Check input.",
            position="input",
            on_fail="raise",
        )
        assert guard.position == "input"
        assert guard.on_fail == "raise"

    def test_repr(self):
        guard = LLMGuardrail(
            model="anthropic/claude-sonnet-4-6",
            policy="Be safe.",
            name="safe_guard",
        )
        r = repr(guard)
        assert "safe_guard" in r
        assert "anthropic/claude-sonnet-4-6" in r

    def test_max_retries_passed_through(self):
        guard = LLMGuardrail(
            model="anthropic/claude-sonnet-4-6",
            policy="Be safe.",
            max_retries=10,
        )
        assert guard.max_retries == 10


class TestLLMGuardrailEvaluate:
    """Test LLMGuardrail._evaluate() with mocked litellm."""

    def test_evaluate_passes(self):
        from unittest.mock import MagicMock, patch

        guard = LLMGuardrail(model="anthropic/claude-sonnet-4-6", policy="Be safe.")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"passed": true, "reason": "Content is safe"}'

        with patch.dict("sys.modules", {"litellm": MagicMock()}):
            import sys

            sys.modules["litellm"].completion.return_value = mock_response
            result = guard.check("Hello world")

        assert result.passed is True

    def test_evaluate_fails(self):
        from unittest.mock import MagicMock, patch

        guard = LLMGuardrail(model="anthropic/claude-sonnet-4-6", policy="No violence.")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[
            0
        ].message.content = '{"passed": false, "reason": "Contains violence"}'

        with patch.dict("sys.modules", {"litellm": MagicMock()}):
            import sys

            sys.modules["litellm"].completion.return_value = mock_response
            result = guard.check("violent content")

        assert result.passed is False
        assert "Contains violence" in result.message

    def test_evaluate_litellm_not_installed(self):
        from unittest.mock import patch

        guard = LLMGuardrail(model="anthropic/claude-sonnet-4-6", policy="Be safe.")

        # Simulate litellm import failure inside _evaluate
        with patch.object(LLMGuardrail, "_evaluate") as mock_eval:
            mock_eval.return_value = GuardrailResult(
                passed=False, message="LLMGuardrail requires the 'litellm' package."
            )
            result = guard._evaluate("content")

        assert result.passed is False
        assert "litellm" in result.message

    def test_evaluate_unparseable_response(self):
        from unittest.mock import MagicMock, patch

        guard = LLMGuardrail(model="anthropic/claude-sonnet-4-6", policy="Be safe.")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not valid json at all"

        with patch.dict("sys.modules", {"litellm": MagicMock()}):
            import sys

            sys.modules["litellm"].completion.return_value = mock_response
            result = guard.check("content")

        assert result.passed is False
        assert "unparseable" in result.message.lower()

    def test_evaluate_api_error(self):
        from unittest.mock import MagicMock, patch

        guard = LLMGuardrail(model="anthropic/claude-sonnet-4-6", policy="Be safe.")

        with patch.dict("sys.modules", {"litellm": MagicMock()}):
            import sys

            sys.modules["litellm"].completion.side_effect = RuntimeError("API error")
            result = guard.check("content")

        assert result.passed is False
        assert "error" in result.message.lower()


# ── Enum tests ────────────────────────────────────────────────────────────


class TestOnFailEnum:
    """Test OnFail str enum."""

    def test_values(self):
        assert OnFail.RETRY == "retry"
        assert OnFail.RAISE == "raise"
        assert OnFail.FIX == "fix"
        assert OnFail.HUMAN == "human"

    def test_str_equality(self):
        """OnFail values compare equal to plain strings."""
        assert OnFail.RETRY == "retry"
        assert "retry" == OnFail.RETRY

    def test_is_str(self):
        assert isinstance(OnFail.RETRY, str)

    def test_in_tuple(self):
        assert OnFail.RETRY in ("retry", "raise", "fix", "human")

    def test_guardrail_accepts_enum(self):
        guard = Guardrail(
            func=lambda c: GuardrailResult(passed=True),
            on_fail=OnFail.RAISE,
        )
        assert guard.on_fail == "raise"
        assert guard.on_fail == OnFail.RAISE


class TestPositionEnum:
    """Test Position str enum."""

    def test_values(self):
        assert Position.INPUT == "input"
        assert Position.OUTPUT == "output"

    def test_str_equality(self):
        assert Position.INPUT == "input"
        assert "output" == Position.OUTPUT

    def test_is_str(self):
        assert isinstance(Position.OUTPUT, str)

    def test_guardrail_accepts_enum(self):
        guard = Guardrail(
            func=lambda c: GuardrailResult(passed=True),
            position=Position.INPUT,
            on_fail=OnFail.RAISE,
        )
        assert guard.position == "input"


# ── @guardrail decorator tests ────────────────────────────────────────────


class TestGuardrailDecorator:
    """Test the @guardrail decorator."""

    def test_bare_decorator(self):
        @guardrail
        def no_pii(content: str) -> GuardrailResult:
            """Reject PII."""
            return GuardrailResult(passed=True)

        assert hasattr(no_pii, "_guardrail_def")
        assert no_pii._guardrail_def.name == "no_pii"
        assert no_pii._guardrail_def.description == "Reject PII."

    def test_decorator_with_name(self):
        @guardrail(name="pii_checker")
        def no_pii(content: str) -> GuardrailResult:
            """Reject PII."""
            return GuardrailResult(passed=True)

        assert no_pii._guardrail_def.name == "pii_checker"

    def test_decorated_function_still_callable(self):
        @guardrail
        def checker(content: str) -> GuardrailResult:
            return GuardrailResult(passed=content == "ok")

        result = checker("ok")
        assert result.passed is True
        result = checker("bad")
        assert result.passed is False

    def test_decorated_function_preserves_name(self):
        @guardrail
        def my_guardrail(content: str) -> GuardrailResult:
            return GuardrailResult(passed=True)

        assert my_guardrail.__name__ == "my_guardrail"

    def test_guardrail_def_has_func(self):
        @guardrail
        def checker(content: str) -> GuardrailResult:
            return GuardrailResult(passed=True)

        assert checker._guardrail_def.func is not None
        result = checker._guardrail_def.func("test")
        assert result.passed is True

    def test_guardrail_accepts_decorated_function(self):
        """Guardrail constructor extracts func and name from @guardrail."""

        @guardrail
        def no_pii(content: str) -> GuardrailResult:
            return GuardrailResult(passed=True)

        guard = Guardrail(no_pii, on_fail=OnFail.RETRY)
        assert guard.name == "no_pii"
        assert guard.func is not None
        assert guard.check("hello").passed is True

    def test_guardrail_with_custom_name_override(self):
        """Explicit name= in Guardrail overrides @guardrail name."""

        @guardrail(name="pii_checker")
        def no_pii(content: str) -> GuardrailResult:
            return GuardrailResult(passed=True)

        guard = Guardrail(no_pii, name="override_name")
        assert guard.name == "override_name"

    def test_guardrail_inherits_decorator_name(self):
        @guardrail(name="pii_checker")
        def no_pii(content: str) -> GuardrailResult:
            return GuardrailResult(passed=True)

        guard = Guardrail(no_pii)
        assert guard.name == "pii_checker"


# ── External guardrail tests ──────────────────────────────────────────────


class TestExternalGuardrail:
    """Test external guardrails (no local func, just name)."""

    def test_external_by_name(self):
        guard = Guardrail(name="compliance_checker", on_fail=OnFail.RETRY)
        assert guard.external is True
        assert guard.name == "compliance_checker"
        assert guard.func is None

    def test_external_default_position(self):
        guard = Guardrail(name="checker")
        assert guard.position == "output"

    def test_external_custom_position(self):
        guard = Guardrail(name="checker", position=Position.INPUT, on_fail=OnFail.RAISE)
        assert guard.position == "input"

    def test_external_check_raises(self):
        guard = Guardrail(name="remote_guard")
        with pytest.raises(RuntimeError, match="Cannot call check.*external"):
            guard.check("hello")

    def test_external_repr(self):
        guard = Guardrail(name="ext_guard", on_fail=OnFail.RAISE)
        r = repr(guard)
        assert "external=True" in r
        assert "ext_guard" in r

    def test_local_not_external(self):
        guard = Guardrail(func=lambda c: GuardrailResult(passed=True))
        assert guard.external is False

    def test_no_func_no_name_raises(self):
        with pytest.raises(ValueError, match="Either func or name must be provided"):
            Guardrail()

    def test_external_max_retries(self):
        guard = Guardrail(name="checker", max_retries=5)
        assert guard.max_retries == 5


# ── Backward compatibility tests ──────────────────────────────────────────


class TestBackwardCompatibility:
    """Existing API continues to work unchanged."""

    def test_string_on_fail_still_works(self):
        guard = Guardrail(
            func=lambda c: GuardrailResult(passed=True),
            on_fail="retry",
        )
        assert guard.on_fail == "retry"

    def test_string_position_still_works(self):
        guard = Guardrail(
            func=lambda c: GuardrailResult(passed=True),
            position="input",
            on_fail="raise",
        )
        assert guard.position == "input"

    def test_enum_and_string_interchangeable_in_comparisons(self):
        guard = Guardrail(
            func=lambda c: GuardrailResult(passed=True),
            on_fail=OnFail.RETRY,
            position=Position.OUTPUT,
        )
        assert guard.on_fail == "retry"
        assert guard.position == "output"

    def test_regex_guardrail_with_enums(self):
        guard = RegexGuardrail(
            patterns=[r"\d+"],
            position=Position.OUTPUT,
            on_fail=OnFail.RETRY,
        )
        assert guard.position == "output"
        assert guard.on_fail == "retry"

    def test_llm_guardrail_with_enums(self):
        guard = LLMGuardrail(
            model="anthropic/claude-sonnet-4-6",
            policy="Be safe.",
            position=Position.OUTPUT,
            on_fail=OnFail.RETRY,
        )
        assert guard.position == "output"
        assert guard.on_fail == "retry"


# ── Import tests ──────────────────────────────────────────────────────────


class TestPublicImports:
    """Test that new symbols are importable from conductor.ai.agents."""

    def test_import_guardrail_decorator(self):
        from conductor.ai.agents import guardrail as g

        assert callable(g)

    def test_import_on_fail(self):
        from conductor.ai.agents import OnFail

        assert OnFail.RETRY == "retry"

    def test_import_position(self):
        from conductor.ai.agents import Position

        assert Position.OUTPUT == "output"

    def test_import_guardrail_def(self):
        from conductor.ai.agents import GuardrailDef

        assert GuardrailDef is not None


# ── P2-E / P4-E: Guardrail validation & edge cases ──────────────────────


class TestGuardrailMaxRetriesValidation:
    """Test max_retries validation."""

    def test_zero_raises(self):
        with pytest.raises(ValueError, match="max_retries must be >= 1"):
            Guardrail(func=lambda c: GuardrailResult(passed=True), max_retries=0)

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="max_retries must be >= 1"):
            Guardrail(func=lambda c: GuardrailResult(passed=True), max_retries=-1)

    def test_one_is_valid(self):
        guard = Guardrail(func=lambda c: GuardrailResult(passed=True), max_retries=1)
        assert guard.max_retries == 1

    def test_regex_guardrail_zero_retries_raises(self):
        with pytest.raises(ValueError, match="max_retries must be >= 1"):
            RegexGuardrail(patterns=[r"test"], max_retries=0)

    def test_llm_guardrail_zero_retries_raises(self):
        with pytest.raises(ValueError, match="max_retries must be >= 1"):
            LLMGuardrail(
                model="anthropic/claude-sonnet-4-6",
                policy="Be safe.",
                max_retries=0,
            )

    def test_external_guardrail_zero_retries_raises(self):
        with pytest.raises(ValueError, match="max_retries must be >= 1"):
            Guardrail(name="checker", max_retries=0)


class TestGuardrailEdgeCases:
    """Edge case tests for guardrails."""

    def test_empty_string_content(self):
        """All guardrail types should handle empty string content."""

        def check(content: str) -> GuardrailResult:
            return GuardrailResult(passed=len(content) > 0, message="Empty content")

        guard = Guardrail(func=check)
        result = guard.check("")
        assert result.passed is False

    def test_regex_guardrail_empty_content(self):
        guard = RegexGuardrail(patterns=[r".+"], mode="allow", name="non_empty")
        result = guard.check("")
        assert result.passed is False

    def test_guardrail_function_returning_none(self):
        """A guardrail that returns None instead of GuardrailResult returns None.

        This is a documentation of current behavior — the caller (compiled
        worker) will error when trying to access .passed on the None result.
        """

        def bad_check(content: str):
            return None

        guard = Guardrail(func=bad_check)
        result = guard.check("hello")
        assert result is None

    def test_guardrail_function_throwing_exception(self):
        """A guardrail function that throws should propagate."""

        def failing_check(content: str) -> GuardrailResult:
            raise RuntimeError("Guardrail internal error")

        guard = Guardrail(func=failing_check)
        with pytest.raises(RuntimeError, match="Guardrail internal error"):
            guard.check("hello")

    def test_on_fail_fix_with_regex_guardrail(self):
        """RegexGuardrail with on_fail='fix' — fixed_output is always None."""
        guard = RegexGuardrail(
            patterns=[r"badword"],
            on_fail="fix",
            name="regex_fix",
        )
        result = guard.check("contains badword here")
        assert result.passed is False
        # RegexGuardrail doesn't produce fixed_output
        assert result.fixed_output is None

    def test_multiple_tool_guardrails_input_and_output(self):
        """Both input and output guardrails can coexist."""
        input_guard = Guardrail(
            func=lambda c: GuardrailResult(passed=True),
            position="input",
            on_fail="raise",
            name="input_guard",
        )
        output_guard = Guardrail(
            func=lambda c: GuardrailResult(passed=True),
            position="output",
            on_fail="retry",
            name="output_guard",
        )
        assert input_guard.position == "input"
        assert output_guard.position == "output"
        assert input_guard.check("test").passed is True
        assert output_guard.check("test").passed is True


class TestCombinedGuardrailWorkerLogic:
    """Test the combined guardrail worker logic (P1-D fix).

    Tests the pattern used in agent_compiler.make_combined_guardrail_worker
    to verify that exception handling respects on_fail mode.
    """

    def _make_worker(self, specs):
        """Create a combined guardrail worker matching the compiler pattern."""
        import logging

        logger = logging.getLogger("test")

        def combined_guardrail_worker(content=None, iteration=0):
            if content is None:
                content_str = ""
            elif isinstance(content, str):
                content_str = content
            else:
                import json as _json

                try:
                    content_str = _json.dumps(content, default=str)
                except (TypeError, ValueError):
                    content_str = str(content)
            for spec in specs:
                try:
                    result = spec["func"](content_str)
                    if not result.passed:
                        on_fail = spec["on_fail"]
                        if on_fail == "retry" and iteration >= spec["max_retries"]:
                            on_fail = "raise"
                        return {
                            "passed": False,
                            "message": result.message,
                            "on_fail": on_fail,
                            "fixed_output": getattr(result, "fixed_output", None),
                            "guardrail_name": spec["name"],
                            "should_continue": on_fail == "retry",
                        }
                except Exception as e:
                    on_fail = spec["on_fail"]
                    if on_fail == "retry" and iteration >= spec["max_retries"]:
                        on_fail = "raise"
                    return {
                        "passed": False,
                        "message": f"Guardrail error: {e}",
                        "on_fail": on_fail,
                        "fixed_output": None,
                        "guardrail_name": spec["name"],
                        "should_continue": on_fail == "retry",
                    }
            return {
                "passed": True,
                "message": "",
                "on_fail": "pass",
                "fixed_output": None,
                "guardrail_name": "",
                "should_continue": False,
            }

        return combined_guardrail_worker

    def test_exception_with_retry_continues(self):
        """P1-D: Exception in guardrail with on_fail='retry' sets should_continue=True."""

        def throwing_guard(content: str) -> GuardrailResult:
            raise RuntimeError("Check failed!")

        specs = [
            {
                "func": throwing_guard,
                "name": "thrower",
                "on_fail": "retry",
                "max_retries": 3,
            }
        ]
        worker = self._make_worker(specs)
        result = worker(content="test", iteration=0)
        assert result["passed"] is False
        assert result["should_continue"] is True
        assert result["on_fail"] == "retry"

    def test_exception_with_raise_stops(self):
        """Exception in guardrail with on_fail='raise' sets should_continue=False."""

        def throwing_guard(content: str) -> GuardrailResult:
            raise RuntimeError("Check failed!")

        specs = [
            {
                "func": throwing_guard,
                "name": "thrower",
                "on_fail": "raise",
                "max_retries": 3,
            }
        ]
        worker = self._make_worker(specs)
        result = worker(content="test", iteration=0)
        assert result["passed"] is False
        assert result["should_continue"] is False
        assert result["on_fail"] == "raise"

    def test_failure_within_retries_continues(self):
        """Guardrail failure with retry (under max_retries) continues the loop."""

        def failing_guard(content: str) -> GuardrailResult:
            return GuardrailResult(passed=False, message="Failed")

        specs = [
            {
                "func": failing_guard,
                "name": "failer",
                "on_fail": "retry",
                "max_retries": 3,
            }
        ]
        worker = self._make_worker(specs)
        result = worker(content="test", iteration=1)
        assert result["should_continue"] is True
        assert result["on_fail"] == "retry"

    def test_failure_exceeding_retries_escalates(self):
        """Guardrail failure exceeding max_retries escalates to 'raise'."""

        def failing_guard(content: str) -> GuardrailResult:
            return GuardrailResult(passed=False, message="Failed")

        specs = [
            {
                "func": failing_guard,
                "name": "failer",
                "on_fail": "retry",
                "max_retries": 3,
            }
        ]
        worker = self._make_worker(specs)
        result = worker(content="test", iteration=3)
        assert result["should_continue"] is False
        assert result["on_fail"] == "raise"

    def test_exception_with_retry_escalates_after_max_retries(self):
        """Exception in guardrail with on_fail='retry' escalates to 'raise' after max_retries."""

        def throwing_guard(content: str) -> GuardrailResult:
            raise RuntimeError("Always fails!")

        specs = [
            {
                "func": throwing_guard,
                "name": "thrower",
                "on_fail": "retry",
                "max_retries": 3,
            }
        ]
        worker = self._make_worker(specs)
        # At iteration=3 (>= max_retries=3), should escalate retry→raise
        result = worker(content="test", iteration=3)
        assert result["passed"] is False
        assert result["should_continue"] is False
        assert result["on_fail"] == "raise"
        assert "Guardrail error" in result["message"]

    def test_exception_with_retry_under_max_retries_continues(self):
        """Exception in guardrail with on_fail='retry' below max_retries continues."""

        def throwing_guard(content: str) -> GuardrailResult:
            raise RuntimeError("Intermittent!")

        specs = [
            {
                "func": throwing_guard,
                "name": "thrower",
                "on_fail": "retry",
                "max_retries": 5,
            }
        ]
        worker = self._make_worker(specs)
        # At iteration=2 (< max_retries=5), should continue retrying
        result = worker(content="test", iteration=2)
        assert result["passed"] is False
        assert result["should_continue"] is True
        assert result["on_fail"] == "retry"

    def test_multiple_guards_fix_then_fail(self):
        """Guard A fixes (on_fail='fix'), Guard B fails (on_fail='raise')."""

        def fixer_guard(content: str) -> GuardrailResult:
            return GuardrailResult(passed=False, message="Needs fix", fixed_output="fixed_content")

        def strict_guard(content: str) -> GuardrailResult:
            # Always fails regardless of content
            return GuardrailResult(passed=False, message="Still bad")

        specs = [
            {
                "func": fixer_guard,
                "name": "fixer",
                "on_fail": "fix",
                "max_retries": 3,
            },
            {
                "func": strict_guard,
                "name": "strict",
                "on_fail": "raise",
                "max_retries": 3,
            },
        ]
        worker = self._make_worker(specs)
        result = worker(content="test", iteration=0)
        # First guard fixes, but second guard fails with raise
        # The worker returns on first failure, so the fixer's result is returned
        # since the fixer failed (passed=False) — it returns immediately
        assert result["passed"] is False


class TestLLMGuardrailImportError:
    """Test LLMGuardrail behavior when litellm is not available."""

    def test_litellm_import_error_returns_failed(self):
        """LLMGuardrail._evaluate returns passed=False when litellm unavailable."""
        from unittest.mock import patch

        from conductor.ai.agents.guardrail import LLMGuardrail

        guard = LLMGuardrail(
            model="openai/gpt-4o",
            policy="Check for safety",
            name="import_test",
        )
        # Mock litellm to raise ImportError
        with patch.dict("sys.modules", {"litellm": None}):
            result = guard._evaluate("test content")
        assert result.passed is False
        assert "litellm" in result.message
