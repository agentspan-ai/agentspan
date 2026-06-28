#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""111 — Plan-Execute-Replan with GUARANTEED many-iteration convergence.

The other replan examples (109, 110) can converge in 1-2 iterations
because their tasks are LLM-friendly. This one is built so the loop
*must* iterate many times: the verifier holds a secret integer and
each iteration only reveals one bit of information (too_low / too_high).
Optimal binary search hits a number in [1, 1000] in ~10 iterations;
an LLM with the full history typically lands in 10-15.

The loop:

    iteration N:
        1. plan = build_plan(N, history)
              ↳ history is the full list of (prior_guess, verdict) pairs;
                the LLM uses it to bound the search range.
        2. execute plan via PAE — a generate op writes a guess to disk,
           then a deterministic check_guess tool compares against the
           secret and writes a verdict JSON.
        3. read result.json
        4. if verdict == 'correct' → DONE
        5. else append (guess, verdict) to history and loop

What you'll see:
  * Iteration 0: LLM has no info, typically guesses near the middle (500).
  * Each subsequent iteration adds one row to the history block in the
    prompt; the LLM converges by halving the search range.
  * Termination on whichever iteration the guess equals the secret.

This is the same plan → execute → replan → execute pattern as 109/110,
but the *iteration count is enforced by the problem itself*. You will
see a loop running. Many times. As intended.

Requirements:
  - AGENTSPAN_SERVER_URL=http://localhost:6767/api (default)
  - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini (default)
  - LLM key for the chosen model.
  - AGENTSPAN_BINSEARCH_SECRET (optional override; default 642)
"""

import json
import os
import shutil
import sys
import tempfile

from conductor.ai.agents import AgentRuntime, Generate, Op, Plan, Step, plan_execute, tool

# ── Configuration ────────────────────────────────────────────────
WORK_DIR = os.path.join(tempfile.gettempdir(), "plan-execute-binsearch")
SECRET_MIN = 1
SECRET_MAX = 1000
MAX_ITERATIONS = 15


def _pick_secret() -> int:
    """Default secret is deliberately off the obvious binary-search
    midpoints so the LLM can't hit it on iter 0 by guessing 500.
    Override via env var to test convergence on other targets."""
    env = os.environ.get("AGENTSPAN_BINSEARCH_SECRET")
    if env:
        return int(env)
    return 642


SECRET_NUMBER = _pick_secret()


# ── Pure helper (tested in isolation) ────────────────────────────


def parse_guess(raw: str) -> int | None:
    """LLMs emit guesses as strings, ints, or sometimes "Guess: 537".
    Strip everything but digits (and a leading minus). Return None if
    no digits found — the loop reports verdict='invalid' and tries
    again."""
    if raw is None:
        return None
    s = str(raw).strip()
    sign = -1 if s.startswith("-") else 1
    digits = "".join(c for c in s if c.isdigit())
    if not digits:
        return None
    return sign * int(digits)


# ── Tools ────────────────────────────────────────────────────────


@tool
def write_guess(path: str, guess) -> str:
    """Persist the LLM's proposed guess to disk. ``guess`` is declared
    untyped because LLMs routinely emit a JSON number instead of the
    string the output_schema asks for (F3 from the design review);
    coerce here at the boundary."""
    full = os.path.join(WORK_DIR, path)
    os.makedirs(os.path.dirname(full) or WORK_DIR, exist_ok=True)
    with open(full, "w") as f:
        f.write(str(guess))
    return f"wrote guess {guess!r}"


@tool
def check_guess(guess_path: str, result_path: str) -> str:
    """Compare the guess file against the secret integer; write a
    verdict JSON. Deterministic — no LLM-as-judge."""
    full = os.path.join(WORK_DIR, guess_path)
    raw = ""
    if os.path.exists(full):
        with open(full) as f:
            raw = f.read().strip()
    parsed = parse_guess(raw)
    if parsed is None:
        verdict = {"verdict": "invalid", "guess": None, "raw": raw}
    elif parsed == SECRET_NUMBER:
        verdict = {"verdict": "correct", "guess": parsed}
    elif parsed < SECRET_NUMBER:
        verdict = {"verdict": "too_low", "guess": parsed}
    else:
        verdict = {"verdict": "too_high", "guess": parsed}
    out = os.path.join(WORK_DIR, result_path)
    os.makedirs(os.path.dirname(out) or WORK_DIR, exist_ok=True)
    with open(out, "w") as f:
        json.dump(verdict, f, indent=2)
    return f"verdict: {verdict['verdict']} (guess={verdict.get('guess')})"


# ── Plan builder ─────────────────────────────────────────────────


def _bounds_from_history(history: list[dict]) -> tuple[int, int]:
    """Derive the current low/high search bounds from the history.

    For each (guess, verdict) pair: ``too_low`` means the secret is
    strictly greater than that guess; ``too_high`` means strictly less.
    The resulting bounds are presented to the LLM in the prompt as a
    derived hint so it doesn't have to recompute them.
    """
    lo, hi = SECRET_MIN, SECRET_MAX
    for h in history:
        g = h.get("guess")
        if g is None:
            continue
        if h.get("verdict") == "too_low":
            lo = max(lo, g + 1)
        elif h.get("verdict") == "too_high":
            hi = min(hi, g - 1)
    return lo, hi


def _build_history_block(history: list[dict]) -> str:
    if not history:
        return ""
    lines = [
        f"  iter {h['iteration']}: guessed {h.get('guess')!r:>6} → {h.get('verdict')}"
        for h in history
    ]
    lo, hi = _bounds_from_history(history)
    return (
        "Your previous guesses:\n"
        + "\n".join(lines)
        + f"\n\nThe secret must therefore be in [{lo}, {hi}].\n"
    )


def build_plan(iteration: int, history: list[dict]) -> Plan:
    """One iteration's plan: write a guess, check it."""
    guess_path = f"iter{iteration}/guess.txt"
    result_path = f"iter{iteration}/result.json"
    history_block = _build_history_block(history)
    instructions = (
        f"I am thinking of an integer between {SECRET_MIN} and {SECRET_MAX} (inclusive). "
        f"You must guess it. After each guess I will reply 'too_low', 'too_high', or 'correct'.\n\n"
        f"{history_block}"
        f"Iteration {iteration}. Make your next guess. "
        f"Use binary search — pick a number in the middle of the remaining range. "
        f"Respond with ONLY the integer, no prose."
    )
    return Plan(
        steps=[
            Step(
                "guess",
                operations=[
                    Op(
                        "write_guess",
                        generate=Generate(
                            instructions=instructions,
                            output_schema=f'{{"path": "{guess_path}", "guess": "<integer>"}}',
                            max_tokens=64,
                        ),
                    )
                ],
            ),
            Step(
                "check",
                depends_on=["guess"],
                operations=[
                    Op(
                        "check_guess",
                        args={"guess_path": guess_path, "result_path": result_path},
                    )
                ],
            ),
        ],
    )


# ── Loop ─────────────────────────────────────────────────────────


def read_result(iteration: int) -> dict:
    p = os.path.join(WORK_DIR, f"iter{iteration}", "result.json")
    if not os.path.exists(p):
        return {"verdict": "missing", "guess": None}
    with open(p) as f:
        return json.load(f)


def run_binsearch_loop(runtime: AgentRuntime, harness, *, max_iter: int = MAX_ITERATIONS) -> dict:
    """plan → execute → replan → execute → ... until correct or budget exhausted."""
    history: list[dict] = []

    for iteration in range(max_iter):
        plan = build_plan(iteration, history)
        result = runtime.run(harness, "guess the number", plan=plan, timeout=120)
        v = read_result(iteration)
        guess = v.get("guess")
        verdict = v.get("verdict")
        history.append(
            {
                "iteration": iteration,
                "guess": guess,
                "verdict": verdict,
                "execution_id": result.execution_id,
            }
        )

        lo, hi = _bounds_from_history(history[:-1])  # bounds BEFORE this guess
        print(
            f"── iteration {iteration:>2}  range=[{lo:>4},{hi:>4}]  "
            f"guess={guess!s:>5}  →  {verdict:>9}  "
            f"wf={result.execution_id}"
        )

        if verdict == "correct":
            print(f"\n  → SOLVED in {iteration + 1} iterations (secret was {SECRET_NUMBER})")
            return {"solved": True, "iterations": iteration + 1, "history": history}

    print(f"\n  → budget exhausted after {max_iter} iterations; secret was {SECRET_NUMBER}")
    return {"solved": False, "iterations": max_iter, "history": history}


# ── Entry point ──────────────────────────────────────────────────


def main(argv: list[str]) -> None:
    if os.path.exists(WORK_DIR):
        shutil.rmtree(WORK_DIR)
    os.makedirs(WORK_DIR, exist_ok=True)

    print(f"work_dir: {WORK_DIR}")
    print(f"secret: hidden in [{SECRET_MIN}, {SECRET_MAX}] (actual: {SECRET_NUMBER})")
    print(f"budget: {MAX_ITERATIONS} iterations")
    print("goal:   converge via binary search\n")

    harness = plan_execute(
        name="binsearch",
        tools=[write_guess, check_guess],
        planner_instructions="(planner unused; plans supplied directly each iteration)",
        model=os.environ.get("AGENTSPAN_LLM_MODEL", "anthropic/claude-sonnet-4-6"),
    )

    with AgentRuntime() as runtime:
        outcome = run_binsearch_loop(runtime, harness)

    print("\n── outcome ──────────────────────────────────────────")
    print(f"solved:     {outcome['solved']}")
    print(f"iterations: {outcome['iterations']}")
    print("\nfull history:")
    for h in outcome["history"]:
        print(f"  iter {h['iteration']:>2}: {h.get('guess')!s:>5} → {h.get('verdict')}")


if __name__ == "__main__":
    main(sys.argv)
