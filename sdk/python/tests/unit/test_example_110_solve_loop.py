# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for the goal-seeking plan-execute-replan loop in example 110.

Locks the pure-logic invariants — single-candidate evaluator,
prompt-feedback construction, plan shape, per-position differentiation
— so a refactor breaks the test, not silently the loop's convergence
behaviour."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_example():
    py_root = Path(__file__).resolve().parents[2]
    src = py_root / "examples" / "110_plan_execute_replan_solve.py"
    spec = importlib.util.spec_from_file_location("ex110", src)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_evaluate_one_passes_a_known_good_sentence():
    ex = _load_example()
    # Exactly 20 words, starts with "Agentspan", contains all three keywords.
    s = (
        "Agentspan reliably compiles each deterministic loop, iteratively validated through feedback "
        "and refinement until the orchestrated outcome converges to a stable, predictable, observable system state today."
    )
    ev = ex.evaluate_one(s)
    assert ev["fails"] == [], f"known-good sentence should pass; got fails={ev['fails']}"
    assert any("word_count" in p for p in ev["passes"])
    assert any("first_word" in p for p in ev["passes"])
    assert any("keywords" in p for p in ev["passes"])


def test_evaluate_one_reports_each_failure_explicitly():
    """The replanner's signal quality depends on the per-constraint
    failure detail. A candidate failing multiple constraints must list
    every failure with its observation, not just the first."""
    ex = _load_example()
    ev = ex.evaluate_one("This is short and wrong.")
    assert len(ev["fails"]) == 4, f"all 4 should fail, got {ev['fails']}"
    joined = " ".join(ev["fails"])
    assert "word_count_off" in joined
    assert "wrong_first_word" in joined
    assert "wrong_last_word" in joined
    assert "missing_keywords" in joined


def test_evaluate_one_strips_wrapping_quotes():
    """LLMs sometimes wrap their answer in quotes. The evaluator must
    not penalise that."""
    ex = _load_example()
    s = '"Agentspan reliably compiles each deterministic loop, iteratively validated through feedback and refinement until the orchestrated outcome converges to a stable, predictable, observable system state today."'
    ev = ex.evaluate_one(s)
    assert ev["fails"] == [], f"wrapped-in-quotes sentence should still pass; got {ev['fails']}"


def test_evaluate_one_keyword_check_is_case_insensitive():
    ex = _load_example()
    # Mixed-case keywords — case-insensitive whole-word check should still
    # match. 25 words, ends with 'today', starts with 'Agentspan'.
    s = (
        "Agentspan reliably compiles each Deterministic LOOP, Iteratively Validated through Feedback "
        "and Refinement until the orchestrated outcome Converges to a stable, predictable, observable system state today."
    )
    ev = ex.evaluate_one(s)
    assert ev["fails"] == [], f"case variants of keywords should match; got {ev['fails']}"


def test_evaluate_one_keyword_check_requires_whole_word():
    """``loop`` should match ``loop`` but NOT ``looping`` — otherwise
    the LLM gets to claim a constraint with a substring trick."""
    ex = _load_example()
    # Contains 'looping' but not the standalone 'loop'.
    s = (
        "Agentspan keeps looping through deterministic feedback for "
        "fifteen consecutive minutes until the task is finally finished today."
    )
    ev = ex.evaluate_one(s)
    fails = " ".join(ev["fails"])
    assert "missing_keywords" in fails, f"substring 'looping' should not satisfy 'loop' — got passes={ev['passes']}"


def test_build_plan_initial_has_no_prior_failures_in_instructions():
    ex = _load_example()
    plan = ex.build_plan(0, prior_failures=None)
    instr = plan.to_dict()["steps"][0]["operations"][0]["generate"]["instructions"]
    assert "first attempt" in instr.lower()
    assert "previous attempts" not in instr.lower()


def test_build_plan_replan_bakes_each_prior_candidate_and_its_failures():
    """The whole point of the adaptive loop: iteration N+1's prompt
    must contain each prior candidate's text + per-constraint failure
    list. If this regresses, the LLM keeps emitting the same answer
    forever."""
    ex = _load_example()
    prior = [
        {
            "candidate": "Wrong start of the sentence here today.",
            "passes": [],
            "fails": ["word_count_off (got 8, expected 20)", "wrong_first_word (got 'Wrong')"],
        },
        {
            "candidate": "Agentspan does some things but lacks the right keywords.",
            "passes": [],
            "fails": ["missing_keywords (['deterministic', 'loop', 'feedback'])"],
        },
    ]
    plan = ex.build_plan(1, prior_failures=prior)
    instr = plan.to_dict()["steps"][0]["operations"][0]["generate"]["instructions"]
    # Each prior candidate's preview must appear so the LLM sees what was tried.
    assert "Wrong start" in instr
    assert "Agentspan does some things" in instr
    # Each unique failure mode must appear so the LLM knows what to change.
    assert "word_count_off" in instr
    assert "wrong_first_word" in instr
    assert "missing_keywords" in instr


def test_build_plan_has_propose_then_verify_with_correct_concurrency():
    """Plan shape: parallel proposers then one verifier."""
    ex = _load_example()
    plan = ex.build_plan(0, None)
    d = plan.to_dict()
    assert [s["id"] for s in d["steps"]] == ["propose", "verify"]
    assert d["steps"][0]["parallel"] is True
    assert len(d["steps"][0]["operations"]) == ex.CANDIDATES_PER_ITERATION
    assert d["steps"][1]["depends_on"] == ["propose"]
    for op in d["steps"][0]["operations"]:
        assert "generate" in op
        assert "args" not in op
    verify_op = d["steps"][1]["operations"][0]
    assert "args" in verify_op
    assert "generate" not in verify_op


def test_parallel_proposers_get_different_style_hints():
    """If all K parallel proposers get the same prompt, they emit
    identical sentences (observed empirically with both gpt-4o-mini
    and claude-haiku). Each proposer position must get a distinct
    style hint so the FORK_JOIN exploration covers ground."""
    ex = _load_example()
    plan = ex.build_plan(0, None)
    ops = plan.to_dict()["steps"][0]["operations"]
    instructions_per_op = [op["generate"]["instructions"] for op in ops]
    # Each prompt must contain a unique proposer index.
    for i, instr in enumerate(instructions_per_op):
        assert f"proposer #{i}" in instr, (
            f"op {i} prompt missing 'proposer #{i}' marker: {instr[:120]!r}"
        )
    # And no two prompts are identical (style hints differ).
    assert len(set(instructions_per_op)) == ex.CANDIDATES_PER_ITERATION, (
        "every parallel proposer must get a unique prompt"
    )


def test_verify_candidates_writes_verdict_with_winner_when_one_passes(tmp_path, monkeypatch):
    """Integration of the tool: stage candidate files on disk, invoke
    the underlying function, read the verdict it wrote."""
    ex = _load_example()
    monkeypatch.setattr(ex, "WORK_DIR", str(tmp_path))
    (tmp_path / "stage").mkdir()
    (tmp_path / "stage" / "cand_0.txt").write_text("This is way too short and wrong.")
    good = (
        "Agentspan reliably compiles each deterministic loop, iteratively validated through feedback "
        "and refinement until the orchestrated outcome converges to a stable, predictable, observable system state today."
    )
    (tmp_path / "stage" / "cand_1.txt").write_text(good)
    (tmp_path / "stage" / "cand_2.txt").write_text("Agentspan needs more work and is missing required vocabulary entirely in this attempt today now.")

    fn = getattr(ex.verify_candidates, "__wrapped__", ex.verify_candidates)
    msg = fn("stage", "stage/verdict.json")
    assert "verified 3 candidates" in msg
    import json as _json

    verdict = _json.loads((tmp_path / "stage" / "verdict.json").read_text())
    assert verdict["winner"] == good
    assert len(verdict["evaluations"]) == 3
    # Per-eval fails populated for the bad cases.
    bad = [e for e in verdict["evaluations"] if e["candidate"] != good]
    for e in bad:
        assert e["fails"], f"non-winner must have non-empty fails; got {e}"
