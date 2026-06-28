#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""110 — Plan-Execute-Replan goal-seeking loop.

Example 109 demonstrated the *shape* of an outer replan loop (one
candidate per iteration, threshold-driven). This example demonstrates
the *adaptive* variant: each iteration proposes K candidates in
parallel, a deterministic verifier reports a precise per-constraint
failure breakdown for each, and the next iteration's plan threads
those exact failures into the LLM's instructions. The loop terminates
the moment any one candidate clears every constraint.

    iteration N:
        1. plan = build_plan(N, prior_failures)
              ↳ if N > 0: instructions list each prior candidate +
                which specific constraints it failed.
        2. execute plan via PAE — K parallel write_candidate generate ops
           feeding a deterministic verify_candidates step.
        3. read verdict.json from disk
        4. if any candidate passed every constraint → DONE
        5. else carry the per-candidate failure breakdown into N+1

Domain: write a sentence that satisfies a small set of word-level
constraints. Generation is what LLMs do best, so the loop converges
in 1-3 iterations on default-mini models. The structural pattern
generalises to any LLM-generator + deterministic-verifier loop —
swap the verifier for ``run_pytest``, ``check_proof``, ``query_db``,
etc., and the outer loop is identical.

Roles:
- The LLM proposes candidates (creative step). It sees the goal +
  each prior candidate's exact failure modes.
- The deterministic ``verify_candidates`` tool checks each candidate
  and produces a precise per-constraint pass/fail list — no
  LLM-as-judge.
- The replanner threads failures into the next iteration's prompt so
  the LLM converges instead of repeating the same mistakes.

Constraints for this demo:
    1. The sentence starts with the word "Agentspan".
    2. It contains all three keywords: "deterministic", "loop", "feedback".
    3. It has exactly EXPECTED_WORD_COUNT words (default 20).

Requirements:
  - AGENTSPAN_SERVER_URL=http://localhost:6767/api (default)
  - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini (default)
  - LLM key for the chosen model.
"""

import json
import os
import re
import shutil
import sys
import tempfile

from conductor.ai.agents import AgentRuntime, Generate, Op, Plan, Step, plan_execute, tool

# ── Configuration ────────────────────────────────────────────────
WORK_DIR = os.path.join(tempfile.gettempdir(), "plan-execute-solve")
CANDIDATES_PER_ITERATION = 2
MAX_ITERATIONS = 6

EXPECTED_FIRST_WORD = "Agentspan"
EXPECTED_KEYWORDS = (
    "deterministic",
    "loop",
    "feedback",
    "iteratively",
    "converges",
)
# Exact-count constraints are pathological for LLMs even with feedback —
# they consistently land within ±2 of the target but rarely on the nose.
# That's a feature for this demo: it forces 2-3 iterations of refinement,
# letting the loop pattern actually show its work instead of one-shotting.
# A real production use would relax to a tolerance band; we keep it tight
# here precisely because we want to *see* the loop iterate.
WORD_COUNT_MIN = 25
WORD_COUNT_MAX = 25
EXPECTED_LAST_WORD = "today"


# ── Pure helpers (also tested in isolation) ──────────────────────


def evaluate_one(raw: str) -> dict:
    """Apply every constraint to a single candidate sentence.

    Returns a dict with ``passes`` (list of constraint names satisfied)
    and ``fails`` (list of "<rule>: <observed>" strings). The detail in
    each fail string is the load-bearing bit — that's what the
    replanner threads into the next iteration's prompt so the LLM
    knows what to change."""
    sentence = (raw or "").strip()
    # Strip surrounding quotes if the LLM wrapped its answer.
    if sentence.startswith(('"', "'")) and sentence.endswith(('"', "'")):
        sentence = sentence[1:-1].strip()

    passes: list[str] = []
    fails: list[str] = []

    # Word count — split on whitespace. Tolerance band; see WORD_COUNT_MIN/MAX above.
    words = sentence.split()
    n = len(words)
    if WORD_COUNT_MIN <= n <= WORD_COUNT_MAX:
        passes.append(f"word_count ({n} in [{WORD_COUNT_MIN}..{WORD_COUNT_MAX}])")
    else:
        fails.append(
            f"word_count_off (got {n}, expected {WORD_COUNT_MIN}..{WORD_COUNT_MAX})"
        )

    # First word.
    first = words[0].rstrip(".,!?;:") if words else ""
    if first == EXPECTED_FIRST_WORD:
        passes.append(f"first_word ({first!r})")
    else:
        fails.append(f"wrong_first_word (got {first!r}, expected {EXPECTED_FIRST_WORD!r})")

    # Last word — sentence-final punctuation stripped before comparison.
    last = words[-1].rstrip(".,!?;:") if words else ""
    if last.lower() == EXPECTED_LAST_WORD.lower():
        passes.append(f"last_word ({last!r})")
    else:
        fails.append(f"wrong_last_word (got {last!r}, expected {EXPECTED_LAST_WORD!r})")

    # Required keywords — case-insensitive whole-word check.
    lower = sentence.lower()
    missing = [kw for kw in EXPECTED_KEYWORDS if not re.search(rf"\b{re.escape(kw)}\b", lower)]
    if not missing:
        passes.append(f"keywords ({list(EXPECTED_KEYWORDS)})")
    else:
        fails.append(f"missing_keywords ({missing})")

    return {"candidate": sentence, "passes": passes, "fails": fails}


# ── Tools ────────────────────────────────────────────────────────


@tool
def write_candidate(path: str, sentence) -> str:
    """Persist one LLM-proposed candidate sentence to disk.

    Called via a ``generate`` op: the LLM produces ``{"path": "...",
    "sentence": "..."}`` and PAC templates those fields into a SIMPLE
    for this tool. ``sentence`` is declared without a type annotation
    and coerced to ``str`` because LLMs sometimes ignore output_schema
    hints and emit a different JSON type — a real-world demonstration
    of the F3 finding (output_schema is documentation, not validation).
    Tool authors carry the type-tolerance burden at the edge until a
    JSON-Schema validator lands in PAC.
    """
    full = os.path.join(WORK_DIR, path)
    os.makedirs(os.path.dirname(full) or WORK_DIR, exist_ok=True)
    with open(full, "w") as f:
        f.write(str(sentence))
    return f"wrote candidate ({len(str(sentence))} chars) to {full}"


@tool
def verify_candidates(input_dir: str, output_path: str) -> str:
    """Verify every candidate in ``input_dir`` against the constraints
    and write a structured verdict JSON to ``output_path``.

    Deterministic — no LLM-as-judge. The per-candidate ``fails`` list
    is what the outer loop feeds back into the next iteration's
    proposer prompt to drive convergence.
    """
    full_in = os.path.join(WORK_DIR, input_dir)
    evaluations: list[dict] = []
    winner: str | None = None
    if os.path.exists(full_in):
        for fname in sorted(os.listdir(full_in)):
            if not fname.startswith("cand_") or not fname.endswith(".txt"):
                continue
            with open(os.path.join(full_in, fname)) as f:
                ev = evaluate_one(f.read())
            ev["source"] = fname
            evaluations.append(ev)
            if not ev["fails"] and winner is None:
                winner = ev["candidate"]
    verdict = {"winner": winner, "evaluations": evaluations}

    full_out = os.path.join(WORK_DIR, output_path)
    os.makedirs(os.path.dirname(full_out) or WORK_DIR, exist_ok=True)
    with open(full_out, "w") as f:
        json.dump(verdict, f, indent=2)
    return f"verified {len(evaluations)} candidates → {full_out} (winner={'YES' if winner else 'NO'})"


# ── Plan builder ─────────────────────────────────────────────────


# Per-position style hints differentiate the K parallel proposers so they
# explore different parts of the answer space instead of emitting the same
# sentence K times (observed empirically when the prompt is uniform).
_STYLE_HINTS = [
    "Use a technical, matter-of-fact register.",
    "Use a more illustrative register; a concrete scenario.",
    "Use a concise, declarative register; short clauses.",
    "Pivot the framing — describe a contrast or trade-off.",
]


def _build_proposer_instructions(
    iteration: int,
    candidate_index: int,
    prior_failures: list[dict] | None,
) -> str:
    """Domain prompt + per-candidate style hint + iteration-specific
    feedback. The feedback section is what makes iteration N+1 different
    from iteration N."""
    base = (
        f"Write a single sentence that satisfies ALL of:\n"
        f"  1. Starts with the word {EXPECTED_FIRST_WORD!r}.\n"
        f"  2. Ends with the word {EXPECTED_LAST_WORD!r} (followed only by a period).\n"
        f"  3. Contains all of these words: {list(EXPECTED_KEYWORDS)}.\n"
        f"  4. Has between {WORD_COUNT_MIN} and {WORD_COUNT_MAX} words "
        f"(count: tokens separated by whitespace).\n\n"
        "Respond with ONLY the sentence, no quotes, no prose, no explanation."
    )
    style = _STYLE_HINTS[candidate_index % len(_STYLE_HINTS)]
    if not prior_failures:
        return (
            base
            + f"\n\nIteration {iteration} (first attempt). "
            f"You are proposer #{candidate_index}. {style}"
        )

    lines = []
    for f in prior_failures:
        text = f.get("candidate", "<empty>")
        # Truncate for prompt length.
        if len(text) > 120:
            text = text[:117] + "..."
        lines.append(f"  - {text!r}\n      failed: {', '.join(f['fails'])}")
    history = "\n".join(lines)
    return (
        base
        + f"\n\nIteration {iteration}, proposer #{candidate_index}. {style}\n\n"
        f"Previous attempts (all failed):\n{history}\n\n"
        "Write a DIFFERENT sentence. Use the failure breakdown to fix "
        "specifically what was wrong: if word_count was off, count "
        "your words explicitly; if a keyword was missing, include it; "
        "if the first word was wrong, start with the required one."
    )


def build_plan(iteration: int, prior_failures: list[dict] | None) -> Plan:
    """Plan for one iteration: K parallel proposers + deterministic verifier."""
    work_subdir = f"iter{iteration}"
    cand_paths = [f"{work_subdir}/cand_{i}.txt" for i in range(CANDIDATES_PER_ITERATION)]
    verdict_path = f"{work_subdir}/verdict.json"

    return Plan(
        steps=[
            Step(
                "propose",
                parallel=True,
                operations=[
                    Op(
                        "write_candidate",
                        generate=Generate(
                            instructions=_build_proposer_instructions(iteration, i, prior_failures),
                            output_schema=(
                                f'{{"path": "{cand_paths[i]}", "sentence": "<your sentence>"}}'
                            ),
                            max_tokens=512,
                        ),
                    )
                    for i in range(CANDIDATES_PER_ITERATION)
                ],
            ),
            Step(
                "verify",
                depends_on=["propose"],
                operations=[
                    Op(
                        "verify_candidates",
                        args={"input_dir": work_subdir, "output_path": verdict_path},
                    )
                ],
            ),
        ],
    )


# ── Loop ─────────────────────────────────────────────────────────


def read_verdict(iteration: int) -> dict:
    p = os.path.join(WORK_DIR, f"iter{iteration}", "verdict.json")
    if not os.path.exists(p):
        return {"winner": None, "evaluations": []}
    with open(p) as f:
        return json.load(f)


def run_solve_loop(runtime: AgentRuntime, harness, *, max_iter: int = MAX_ITERATIONS) -> dict:
    """plan → execute → replan → execute → ... until solved or budget exhausted.

    Returns ``{"winner": str|None, "iterations": int, "history": [...]}``.
    The history carries every iteration's verdict so a post-mortem can
    show how the LLM's proposals migrated toward the constraints over
    time — useful for tuning iteration budgets per domain."""
    history: list[dict] = []
    prior_failures: list[dict] | None = None

    for iteration in range(max_iter):
        print(f"\n── iteration {iteration} ─────────────────────────────")
        plan = build_plan(iteration, prior_failures)
        result = runtime.run(harness, "solve the constraint", plan=plan, timeout=240)
        verdict = read_verdict(iteration)
        history.append(
            {"iteration": iteration, "execution_id": result.execution_id, "verdict": verdict}
        )

        for ev in verdict["evaluations"]:
            tag = "✓" if (verdict.get("winner") and ev["candidate"] == verdict["winner"]) else "·"
            preview = (ev["candidate"][:80] + "...") if len(ev["candidate"]) > 80 else ev["candidate"]
            print(f"  {tag} {preview!r}")
            if ev["fails"]:
                print(f"      fails: {ev['fails']}")
            elif ev["passes"]:
                print(f"      passes: {ev['passes']}")

        if verdict.get("winner") is not None:
            print(f"  → DONE in iteration {iteration}")
            return {"winner": verdict["winner"], "iterations": iteration + 1, "history": history}

        prior_failures = list(verdict["evaluations"])

    print(f"\n  → budget exhausted after {max_iter} iterations; no winner")
    return {"winner": None, "iterations": max_iter, "history": history}


# ── Entry point ──────────────────────────────────────────────────


def main(argv: list[str]) -> None:
    if os.path.exists(WORK_DIR):
        shutil.rmtree(WORK_DIR)
    os.makedirs(WORK_DIR, exist_ok=True)

    print(f"work_dir: {WORK_DIR}")
    print(
        f"goal: sentence starting {EXPECTED_FIRST_WORD!r}, ending {EXPECTED_LAST_WORD!r}, "
        f"containing {list(EXPECTED_KEYWORDS)}, "
        f"{WORD_COUNT_MIN}-{WORD_COUNT_MAX} words"
    )
    print(f"budget: {MAX_ITERATIONS} iterations × {CANDIDATES_PER_ITERATION} candidates each")

    harness = plan_execute(
        name="sentence_solver",
        tools=[write_candidate, verify_candidates],
        planner_instructions="(planner unused; plans supplied directly each iteration)",
        model=os.environ.get("AGENTSPAN_LLM_MODEL", "anthropic/claude-sonnet-4-6"),
    )

    with AgentRuntime() as runtime:
        outcome = run_solve_loop(runtime, harness)

    print("\n── outcome ──────────────────────────────────────────")
    if outcome["winner"] is not None:
        print(f"winner: {outcome['winner']!r}")
        print(f"iterations: {outcome['iterations']}")
        # Independent verification — re-run the constraint checks here.
        ev = evaluate_one(outcome["winner"])
        print(f"independent verification: passes={ev['passes']} fails={ev['fails']}")
    else:
        print(f"no winner after {outcome['iterations']} iterations")


if __name__ == "__main__":
    main(sys.argv)
