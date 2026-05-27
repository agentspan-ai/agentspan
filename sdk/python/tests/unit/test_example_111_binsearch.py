# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for the binary-search plan-execute-replan loop in example 111.

Pins the pure-function invariants — guess parsing, bounds derivation
from history, plan shape, history-block prompt construction — so a
refactor breaks the test, not silently the loop's convergence."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_example():
    py_root = Path(__file__).resolve().parents[2]
    src = py_root / "examples" / "111_plan_execute_replan_binsearch.py"
    spec = importlib.util.spec_from_file_location("ex111", src)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_guess_handles_plain_integer():
    ex = _load_example()
    assert ex.parse_guess("500") == 500
    assert ex.parse_guess("  642  ") == 642
    assert ex.parse_guess("1") == 1


def test_parse_guess_strips_prose_keeps_digits():
    """LLM may emit 'Guess: 537' or 'I think 750'. Strip non-digit
    noise so the verifier sees an integer."""
    ex = _load_example()
    assert ex.parse_guess("Guess: 537") == 537
    assert ex.parse_guess("My answer is 750.") == 750
    assert ex.parse_guess("750\n\nthat's my final guess") == 750


def test_parse_guess_returns_none_on_no_digits():
    ex = _load_example()
    assert ex.parse_guess("") is None
    assert ex.parse_guess("no digits here") is None
    assert ex.parse_guess(None) is None


def test_bounds_empty_history_returns_full_range():
    ex = _load_example()
    lo, hi = ex._bounds_from_history([])
    assert (lo, hi) == (ex.SECRET_MIN, ex.SECRET_MAX)


def test_bounds_narrows_with_too_low_and_too_high():
    """Each verdict must tighten exactly one side of the range. If a
    refactor flips the direction (e.g. ``too_low`` decreasing the
    upper bound), the LLM gets misleading bounds and binary search
    explodes."""
    ex = _load_example()
    h = [
        {"iteration": 0, "guess": 500, "verdict": "too_low"},
        {"iteration": 1, "guess": 750, "verdict": "too_high"},
        {"iteration": 2, "guess": 625, "verdict": "too_low"},
    ]
    lo, hi = ex._bounds_from_history(h)
    # too_low at 500 → secret > 500, lo = 501.
    # too_high at 750 → secret < 750, hi = 749.
    # too_low at 625 → secret > 625, lo = 626.
    assert lo == 626
    assert hi == 749


def test_bounds_ignores_missing_guesses():
    """If parse_guess returned None for some iteration, bounds derivation
    must skip it — otherwise a parse failure permanently corrupts the
    range and the loop diverges."""
    ex = _load_example()
    h = [
        {"iteration": 0, "guess": None, "verdict": "invalid"},
        {"iteration": 1, "guess": 500, "verdict": "too_low"},
    ]
    lo, hi = ex._bounds_from_history(h)
    assert lo == 501
    assert hi == ex.SECRET_MAX


def test_build_plan_initial_has_no_history_in_instructions():
    ex = _load_example()
    plan = ex.build_plan(0, history=[])
    instr = plan.to_dict()["steps"][0]["operations"][0]["generate"]["instructions"]
    assert "previous guesses" not in instr.lower()


def test_build_plan_replan_includes_history_and_bounds():
    """The whole point of the loop: iteration N+1's prompt must
    include every prior (guess, verdict) pair AND the derived bounds
    so the LLM can binary-search. Regressing this turns the loop into
    random guessing."""
    ex = _load_example()
    h = [
        {"iteration": 0, "guess": 500, "verdict": "too_low"},
        {"iteration": 1, "guess": 750, "verdict": "too_high"},
    ]
    plan = ex.build_plan(2, h)
    instr = plan.to_dict()["steps"][0]["operations"][0]["generate"]["instructions"]
    # Each prior guess + verdict surface in the prompt.
    assert "500" in instr
    assert "750" in instr
    assert "too_low" in instr
    assert "too_high" in instr
    # Derived bounds must be there so the LLM doesn't have to recompute.
    assert "[501, 749]" in instr, f"bounds missing from instructions: {instr!r}"


def test_build_plan_shape_is_guess_then_check_sequential():
    """One generate op (LLM proposes), one args op (verifier).
    Sequential, not parallel — each iteration is one PAE compile-and-run."""
    ex = _load_example()
    plan = ex.build_plan(0, [])
    d = plan.to_dict()
    assert [s["id"] for s in d["steps"]] == ["guess", "check"]
    # Guess step is not parallel (we want one guess per iteration).
    assert d["steps"][0].get("parallel") in (None, False)
    assert len(d["steps"][0]["operations"]) == 1
    assert "generate" in d["steps"][0]["operations"][0]
    assert d["steps"][1]["depends_on"] == ["guess"]
    assert "args" in d["steps"][1]["operations"][0]
