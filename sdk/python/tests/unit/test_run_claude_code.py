"""Tests for validation.scripts.run_claude_code helpers."""

from __future__ import annotations

import pytest

from validation.scripts.run_claude_code import (
    _expand_env_vars,
    _iteration_example_name,
    _per_iteration_summary,
    _resolved_iterations,
)


def test_expands_bare_dollar_var(monkeypatch):
    monkeypatch.setenv("OCG_API_KEY", "sk-test-123")
    out = _expand_env_vars("Auth: X-Api-Key: $OCG_API_KEY")
    assert out == "Auth: X-Api-Key: sk-test-123"


def test_expands_braced_var(monkeypatch):
    monkeypatch.setenv("OCG_API_KEY", "sk-test-456")
    out = _expand_env_vars("Auth: X-Api-Key: ${OCG_API_KEY}")
    assert out == "Auth: X-Api-Key: sk-test-456"


def test_raises_when_env_var_missing(monkeypatch):
    monkeypatch.delenv("OCG_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OCG_API_KEY"):
        _expand_env_vars("Auth: $OCG_API_KEY")


def test_does_not_expand_lowercase_identifiers(monkeypatch):
    # $foo and $1 should not be treated as env vars — only UPPER_SNAKE names.
    monkeypatch.setenv("foo", "should-not-appear")
    out = _expand_env_vars("price is $1 and $foo bar")
    assert out == "price is $1 and $foo bar"


def test_expands_multiple_vars(monkeypatch):
    monkeypatch.setenv("A_KEY", "alpha")
    monkeypatch.setenv("B_KEY", "beta")
    out = _expand_env_vars("$A_KEY and ${B_KEY}")
    assert out == "alpha and beta"


# --- iteration helpers -------------------------------------------------------


def test_iteration_example_name_is_one_indexed():
    # 1-indexed so the first iteration reads as "iter_1" not "iter_0";
    # downstream judge/report grouping relies on this exact format.
    assert _iteration_example_name("cc_compare", 1) == "cc_compare_iter_1"
    assert _iteration_example_name("cc_compare", 5) == "cc_compare_iter_5"


def test_iteration_example_name_preserves_stem():
    assert _iteration_example_name("other_eval", 3) == "other_eval_iter_3"


def test_per_iteration_summary_aggregates_tokens_and_completion():
    examples = [
        {"status": "COMPLETED", "tokens_total": 100, "duration_s": 1.0},
        {"status": "COMPLETED", "tokens_total": 200, "duration_s": 2.5},
        {"status": "ERROR", "tokens_total": 0, "duration_s": 0.1},
        {"status": "COMPLETED", "tokens_total": 150, "duration_s": 1.5},
        {"status": "COMPLETED", "tokens_total": 250, "duration_s": 3.0},
    ]
    summary = _per_iteration_summary(examples)

    assert summary["iterations"] == 5
    assert summary["completed"] == 4
    assert summary["tokens_total"] == 700
    assert summary["duration_s"] == pytest.approx(8.1)
    assert len(summary["per_iteration"]) == 5
    assert summary["per_iteration"][0] == {
        "iter": 1,
        "status": "COMPLETED",
        "tokens_total": 100,
        "duration_s": 1.0,
    }
    assert summary["per_iteration"][2]["status"] == "ERROR"


def test_per_iteration_summary_empty():
    summary = _per_iteration_summary([])
    assert summary == {
        "iterations": 0,
        "completed": 0,
        "tokens_total": 0,
        "duration_s": 0.0,
        "per_iteration": [],
    }


# --- iteration override ------------------------------------------------------


def test_resolved_iterations_cli_override_wins():
    assert _resolved_iterations({"iterations": 5}, 1) == 1


def test_resolved_iterations_falls_back_to_config():
    assert _resolved_iterations({"iterations": 7}, None) == 7


def test_resolved_iterations_defaults_to_one_when_missing():
    assert _resolved_iterations({}, None) == 1


def test_resolved_iterations_zero_override_is_respected():
    # Explicit 0 passes through the helper; range validation lives in main().
    assert _resolved_iterations({"iterations": 5}, 0) == 0
