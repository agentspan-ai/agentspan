#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""109 — Plan-Execute-Replan loop on top of PAE.

The ``Strategy.PLAN_EXECUTE`` harness gives you a deterministic compiled
DAG per run (planner LLM → JSON plan → Conductor sub-workflow → result).
What it does NOT give you natively is the **outer loop**: run the
pipeline, look at the output, decide whether to continue / replan /
finish, and iterate.

This example builds that loop in user code, using PAE as the deterministic
inner engine and Python as the adaptive outer controller. The pattern:

    iteration N:
        1. compile + execute plan_N via PAE (deterministic)
        2. read the artifacts the run produced (file contents in this case)
        3. decide(): done | replan
        4. if replan, build plan_{N+1} with feedback baked into the
           per-op generate.instructions
        5. loop

Why do this in user code rather than inside PAE? Because the loop
boundary is where adaptability meets determinism — each iteration's
plan executes deterministically, but the *sequence* of plans adapts to
what each iteration produced. PAE's fallback agent is a one-shot eject
seat for hard failures, not an iterative refinement loop.

The task domain here is a research report with a quality gate
(word-count threshold). The decider is rule-based (a single integer
comparison) so the example is cheap and reproducible. Swap in an LLM
decider for real subjective-quality cases — the loop shape is the same.

What to look for in the output:
  * Iteration 1 produces a report at < target word count.
  * The decider returns ``replan`` with a deficit number attached.
  * Iteration 2's plan instructions ask the LLM to write longer
    sections — derived from the deficit, not the original brief.
  * The loop exits when the threshold is met OR ``max_iterations`` hits.

Requirements:
  - AGENTSPAN_SERVER_URL=http://localhost:6767/api (default)
  - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini (default)
  - An LLM key for the chosen model (sections are generated, not static).
"""

import json
import os
import sys
import tempfile

from conductor.ai.agents import AgentRuntime, Generate, Op, Plan, Step, plan_execute, tool

# ── Configuration ────────────────────────────────────────────────
WORK_DIR = os.path.join(tempfile.gettempdir(), "plan-execute-replan")
TARGET_WORD_COUNT = 600
MAX_ITERATIONS = 3
SECTION_COUNT = 3


# ── Tools ────────────────────────────────────────────────────────
# Same shape as example 85's tools, scoped to this WORK_DIR. File-based
# IO sidesteps the F4 finding (per-step outputs not surfaced on
# AgentResult): each iteration just reads from disk between runs.


@tool
def create_directory(path: str) -> str:
    """Create a directory (and parents) if missing."""
    full = os.path.join(WORK_DIR, path)
    os.makedirs(full, exist_ok=True)
    return f"created {full}"


@tool
def write_file(path: str, content: str) -> str:
    """Write ``content`` to ``path`` (relative to the work dir)."""
    full = os.path.join(WORK_DIR, path)
    os.makedirs(os.path.dirname(full) or WORK_DIR, exist_ok=True)
    with open(full, "w") as f:
        f.write(content)
    return f"wrote {len(content)} bytes to {full}"


@tool
def assemble_files(output_path: str, input_paths: str, separator: str = "\n\n") -> str:
    """Concatenate JSON-listed input files into ``output_path``."""
    paths = json.loads(input_paths)
    parts = []
    for p in paths:
        full = os.path.join(WORK_DIR, p)
        if os.path.exists(full):
            with open(full) as f:
                parts.append(f.read())
        else:
            parts.append(f"[missing: {p}]")
    combined = separator.join(parts)
    out_full = os.path.join(WORK_DIR, output_path)
    os.makedirs(os.path.dirname(out_full) or WORK_DIR, exist_ok=True)
    with open(out_full, "w") as f:
        f.write(combined)
    return f"assembled {len(paths)} files into {out_full} ({len(combined)} bytes)"


@tool
def check_word_count(path: str, min_words: int) -> str:
    """Return a JSON status describing whether ``path`` meets ``min_words``."""
    full = os.path.join(WORK_DIR, path)
    if not os.path.exists(full):
        return json.dumps({"passed": False, "word_count": 0, "error": f"missing: {path}"})
    with open(full) as f:
        wc = len(f.read().split())
    return json.dumps({"passed": wc >= min_words, "word_count": wc, "min_words": min_words})


# ── Plan builders ────────────────────────────────────────────────


def _section_path(iteration: int, idx: int) -> str:
    """Each iteration writes its sections under a per-iteration subdir so
    later iterations can read the prior ones without collisions."""
    return f"iter{iteration}/section_{idx}.md"


def _report_path(iteration: int) -> str:
    return f"iter{iteration}/report.md"


def build_initial_plan(topic: str, iteration: int, target_words_per_section: int) -> Plan:
    """A 3-step plan: setup → write N sections in parallel → assemble.

    Each section's content is LLM-generated via ``Generate`` so we get
    actual prose. Word-count check is intentionally NOT inside the plan
    — the outer loop reads it from disk so a failure routes to *replan*
    instead of *fallback*.
    """
    section_paths = [_section_path(iteration, i) for i in range(SECTION_COUNT)]
    return Plan(
        steps=[
            Step("setup", operations=[Op("create_directory", args={"path": f"iter{iteration}"})]),
            Step(
                "write_sections",
                depends_on=["setup"],
                parallel=True,
                operations=[
                    Op(
                        "write_file",
                        generate=Generate(
                            instructions=(
                                f"Write section {i + 1} of {SECTION_COUNT} on the topic: '{topic}'. "
                                f"Target ~{target_words_per_section} words. Markdown with a section "
                                f"heading. No preamble, no closing remarks."
                            ),
                            output_schema=(
                                f'{{"path": "{section_paths[i]}", "content": "<section markdown>"}}'
                            ),
                            max_tokens=2048,
                        ),
                    )
                    for i in range(SECTION_COUNT)
                ],
            ),
            Step(
                "assemble",
                depends_on=["write_sections"],
                operations=[
                    Op(
                        "assemble_files",
                        args={
                            "output_path": _report_path(iteration),
                            "input_paths": json.dumps(section_paths),
                        },
                    )
                ],
            ),
        ],
    )


def build_replan(
    topic: str,
    iteration: int,
    prior_word_count: int,
    target_word_count: int,
) -> Plan:
    """Build the next iteration's plan with the deficit baked into the
    per-section ``generate.instructions``. The LLM sees a concrete
    "previous attempt produced X words, target is Y, write longer sections"
    signal — much stronger than the original brief.
    """
    deficit = max(0, target_word_count - prior_word_count)
    # Distribute the missing words across sections, with a 30% safety
    # margin so we converge rather than oscillating just under target.
    bump_per_section = (deficit // SECTION_COUNT) + max(50, deficit // 3)
    new_target_per_section = (target_word_count // SECTION_COUNT) + bump_per_section

    section_paths = [_section_path(iteration, i) for i in range(SECTION_COUNT)]
    return Plan(
        steps=[
            Step("setup", operations=[Op("create_directory", args={"path": f"iter{iteration}"})]),
            Step(
                "write_sections",
                depends_on=["setup"],
                parallel=True,
                operations=[
                    Op(
                        "write_file",
                        generate=Generate(
                            instructions=(
                                f"Write section {i + 1} of {SECTION_COUNT} on the topic: '{topic}'. "
                                f"Target ~{new_target_per_section} words — the previous attempt "
                                f"produced only {prior_word_count} words across all sections "
                                f"(target {target_word_count}); write substantially longer this "
                                f"time. Markdown with a section heading. No preamble."
                            ),
                            output_schema=(
                                f'{{"path": "{section_paths[i]}", "content": "<longer section markdown>"}}'
                            ),
                            max_tokens=4096,
                        ),
                    )
                    for i in range(SECTION_COUNT)
                ],
            ),
            Step(
                "assemble",
                depends_on=["write_sections"],
                operations=[
                    Op(
                        "assemble_files",
                        args={
                            "output_path": _report_path(iteration),
                            "input_paths": json.dumps(section_paths),
                        },
                    )
                ],
            ),
        ],
    )


# ── Decider ──────────────────────────────────────────────────────


def decide(word_count: int, target: int, iteration: int, max_iter: int) -> dict:
    """Rule-based decision: done if we hit the target, done if we've
    burned the iteration budget, replan otherwise.

    Swap this for an LLM call (``runtime.run(decider_agent, ...)``)
    when the quality signal is subjective rather than measurable. The
    loop shape — read result, decide, optionally replan — does not
    change."""
    if word_count >= target:
        return {
            "action": "done",
            "reason": f"word_count={word_count} ≥ target={target}",
            "word_count": word_count,
        }
    if iteration + 1 >= max_iter:
        return {
            "action": "done",
            "reason": (
                f"max_iterations={max_iter} reached; final word_count={word_count} "
                f"(target was {target})"
            ),
            "word_count": word_count,
        }
    return {
        "action": "replan",
        "reason": f"word_count={word_count} < target={target}; replan",
        "word_count": word_count,
    }


# ── Loop ─────────────────────────────────────────────────────────


def run_replan_loop(
    runtime: AgentRuntime,
    harness,
    topic: str,
    *,
    target_words: int = TARGET_WORD_COUNT,
    max_iterations: int = MAX_ITERATIONS,
    initial_words_per_section: int = 100,
) -> dict:
    """The outer loop. Each iteration:

    1. Run the PAE harness with the current plan (deterministic inner).
    2. Read the resulting report from disk (file-based per-step output).
    3. Run ``check_word_count`` locally to get the quality signal.
    4. Hand the signal to ``decide()``.
    5. If "replan", build the next plan and loop. Otherwise return.

    Returns a history of every iteration plus the final decision —
    useful for debugging which plans converged and which didn't.
    """
    history = []
    plan = build_initial_plan(topic, iteration=0, target_words_per_section=initial_words_per_section)

    for iteration in range(max_iterations):
        print(f"\n── iteration {iteration} ─────────────────────────────")
        result = runtime.run(harness, topic, plan=plan, timeout=240)

        # Read the assembled report from disk (file-based output bridges
        # the F4 gap — see the design review notes accompanying this file).
        report_full = os.path.join(WORK_DIR, _report_path(iteration))
        if os.path.exists(report_full):
            with open(report_full) as f:
                wc = len(f.read().split())
        else:
            wc = 0

        decision = decide(wc, target_words, iteration, max_iterations)
        print(f"  status={result.status} words={wc} → {decision['action']}: {decision['reason']}")
        history.append({"iteration": iteration, "decision": decision, "execution_id": result.execution_id})

        if decision["action"] == "done":
            return {"final_iteration": iteration, "decision": decision, "history": history}

        # Build the next plan, feeding the deficit into the LLM's instructions.
        plan = build_replan(
            topic,
            iteration=iteration + 1,
            prior_word_count=wc,
            target_word_count=target_words,
        )

    # Defensive: max_iterations exhausted without a done decision. This
    # shouldn't happen because decide() returns done at the boundary.
    return {"final_iteration": max_iterations - 1, "decision": history[-1]["decision"], "history": history}


# ── Entry point ──────────────────────────────────────────────────


def main(argv: list[str]) -> None:
    topic = argv[1] if len(argv) > 1 else "The role of orchestration in autonomous AI agents"

    print(f"topic: {topic}")
    print(f"work_dir: {WORK_DIR}")
    print(f"target: {TARGET_WORD_COUNT} words, max {MAX_ITERATIONS} iterations")

    harness = plan_execute(
        name="report_replan",
        tools=[create_directory, write_file, assemble_files, check_word_count],
        planner_instructions="(planner unused; plans supplied directly each iteration)",
        model=os.environ.get("AGENTSPAN_LLM_MODEL", "anthropic/claude-sonnet-4-6"),
    )

    with AgentRuntime() as runtime:
        outcome = run_replan_loop(runtime, harness, topic)

    print("\n── outcome ──────────────────────────────────────────")
    print(json.dumps(outcome["decision"], indent=2))
    print(f"\nFinal report: {os.path.join(WORK_DIR, _report_path(outcome['final_iteration']))}")
    print(f"Iterations run: {len(outcome['history'])}")


if __name__ == "__main__":
    main(sys.argv)
