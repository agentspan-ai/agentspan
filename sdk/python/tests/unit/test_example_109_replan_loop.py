# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for the plan-execute-replan loop scaffolding in example 109.

These pin the pure-function invariants of the loop (initial plan shape,
replan plan deficit-baking, decider rule) so a future refactor that
breaks them is caught immediately — no server, no LLM, no Conductor.

The example is the canonical demonstration of how to layer iterative
refinement on top of PAE's deterministic single-shot execution. If
``decide()`` or ``build_replan()`` regress, the documented pattern stops
working.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


def _load_example():
    """Load 109 as a module without going through ``examples`` package."""
    # __file__ → sdk/python/tests/unit/test_example_109_replan_loop.py
    # parents[2] → sdk/python (the directory containing examples/).
    py_root = Path(__file__).resolve().parents[2]
    src = py_root / "examples" / "109_plan_execute_replan.py"
    spec = importlib.util.spec_from_file_location("ex109", src)
    module = importlib.util.module_from_spec(spec)
    # The example imports ``settings`` from examples/; skip that — it has its
    # own sys.path expectations and we don't need it for pure-function tests.
    sys.path.insert(0, str(src.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def test_build_initial_plan_has_setup_then_parallel_write_then_assemble():
    """Initial plan must be 3 steps: setup (sequential), write (parallel,
    N ops), assemble (sequential, depends on write). The compiled
    Conductor DAG layout depends on this shape."""
    ex = _load_example()
    plan = ex.build_initial_plan("any topic", iteration=0, target_words_per_section=100)
    d = plan.to_dict()
    assert [s["id"] for s in d["steps"]] == ["setup", "write_sections", "assemble"]
    assert d["steps"][1].get("parallel") is True
    assert len(d["steps"][1]["operations"]) == ex.SECTION_COUNT
    assert d["steps"][2]["depends_on"] == ["write_sections"]


def test_initial_plan_first_op_uses_generate_not_args():
    """Section bodies must be LLM-generated, not literal args. If a refactor
    flips this to args (e.g. someone hard-codes section text), the
    iteration story breaks: every replan would re-write identical
    content."""
    ex = _load_example()
    plan = ex.build_initial_plan("any topic", iteration=0, target_words_per_section=100)
    d = plan.to_dict()
    write_op = d["steps"][1]["operations"][0]
    assert "generate" in write_op
    assert "args" not in write_op
    assert "instructions" in write_op["generate"]


def test_build_replan_bakes_deficit_into_instructions():
    """The whole point of the replan path: the LLM must see the prior
    word count and the target so the next iteration's content is
    substantially longer. If the instructions look identical to the
    initial brief, the loop will oscillate at the same word count
    forever."""
    ex = _load_example()
    plan = ex.build_replan(
        "any topic", iteration=1, prior_word_count=120, target_word_count=600
    )
    instr = plan.to_dict()["steps"][1]["operations"][0]["generate"]["instructions"]
    assert "120" in instr, "prior word count must appear in instructions"
    assert "600" in instr, "target word count must appear in instructions"
    assert "longer" in instr.lower() or "substantially" in instr.lower()


def test_build_replan_uses_per_iteration_subdir():
    """Each iteration's sections must be written to a unique directory
    so iteration N+1 doesn't overwrite N. Otherwise debugging
    convergence is impossible."""
    ex = _load_example()
    plan = ex.build_replan(
        "any topic", iteration=2, prior_word_count=100, target_word_count=600
    )
    d = plan.to_dict()
    output_schema = d["steps"][1]["operations"][0]["generate"]["output_schema"]
    assert "iter2/" in output_schema
    assemble_args = d["steps"][2]["operations"][0]["args"]
    assert "iter2/" in assemble_args["output_path"]


def test_decide_done_when_threshold_met():
    """The terminal condition: word count at or above target ends the loop."""
    ex = _load_example()
    d = ex.decide(700, target=600, iteration=0, max_iter=3)
    assert d["action"] == "done"
    assert d["word_count"] == 700


def test_decide_replan_when_below_threshold_and_budget_remains():
    """Mid-loop condition: below target, iterations remaining → replan."""
    ex = _load_example()
    d = ex.decide(400, target=600, iteration=0, max_iter=3)
    assert d["action"] == "replan"
    assert d["word_count"] == 400


def test_decide_done_when_max_iterations_reached_even_if_below_target():
    """Safety condition: never loop past max_iter. A user staring at a
    runaway budget is the worst PAE failure mode — burn iteration count
    before continuing into iteration max_iter."""
    ex = _load_example()
    d = ex.decide(400, target=600, iteration=2, max_iter=3)
    assert d["action"] == "done"
    assert "max_iterations" in d["reason"]


def test_decide_done_when_max_iterations_reached_at_boundary():
    """``iteration + 1 >= max_iter`` is the boundary. Off-by-one in
    either direction is a test the rule must catch."""
    ex = _load_example()
    # iteration=1, max_iter=2 means one more attempt would put us at
    # iteration 2 which equals max_iter — terminate now.
    d = ex.decide(400, target=600, iteration=1, max_iter=2)
    assert d["action"] == "done"


def test_replan_target_grows_with_deficit():
    """The replanner's bump-per-section heuristic must scale with the
    deficit — a larger gap demands more words. Otherwise we converge
    arbitrarily slowly."""
    ex = _load_example()
    small_gap = ex.build_replan("t", 1, prior_word_count=550, target_word_count=600)
    big_gap = ex.build_replan("t", 1, prior_word_count=100, target_word_count=600)
    small_instr = small_gap.to_dict()["steps"][1]["operations"][0]["generate"]["instructions"]
    big_instr = big_gap.to_dict()["steps"][1]["operations"][0]["generate"]["instructions"]
    # Extract the target-words number from each (it's the leading number
    # after "~"). Cheap parse: look for "Target ~" + digits.
    import re

    small_target = int(re.search(r"Target ~(\d+)", small_instr).group(1))
    big_target = int(re.search(r"Target ~(\d+)", big_instr).group(1))
    assert big_target > small_target, (
        f"bigger deficit must produce a larger per-section target; "
        f"got small={small_target} big={big_target}"
    )
