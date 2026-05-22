#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""112 — Plan-Execute-Replan loop INSIDE a single Conductor workflow.

Examples 109/110/111 keep the loop in Python user code: each iteration
is a separate top-level workflow execution. This example does the
opposite — it hand-builds a Conductor WorkflowDef whose body is a
``DO_WHILE`` task that wraps the full plan → execute → review cycle.
You get ONE workflow ID for the whole run, and the iterations show up
as task-ref suffixes (``planner_llm__i0``, ``planner_llm__i1``, …)
inside the same workflow's task list.

The DO_WHILE body each iteration:
  1. ``planner_llm``    — LLM proposes the next guess (the plan).
  2. ``extract_guess``  — INLINE parses the integer out of the LLM text.
  3. ``verify``         — INLINE compares the guess to the secret and
                          emits ``{verdict, done, history}``. This is
                          the deterministic "compile + execute" step
                          condensed into one INLINE for demo brevity;
                          a production version would use
                          ``PLAN_AND_COMPILE`` + ``SUB_WORKFLOW``.
  4. ``reviewer_llm``   — LLM looks at the verdict + history and emits
                          a JSON ``{continue, feedback}`` advisory.
  5. ``update_state``   — SET_VARIABLE pushes the new history/done into
                          workflow variables so the next iteration sees
                          them.

Loop condition: keep going while ``done != true`` AND iteration count
is under the budget.

This is the shape of a *first-class* ``Strategy.PLAN_EXECUTE_REPLAN``
that doesn't exist in Agentspan today (dg-review finding F1, plan
recommendation #2). The example builds it as a raw Conductor workflow
so you can see the DO_WHILE structure end-to-end before any server
changes land.

What to watch:
  * ONE top-level workflow ID.
  * ``loop`` task contains 8-12 iterations as ``__iN`` suffixes.
  * Each iteration's ``planner_llm__iN`` is a separate LLM call.
  * Final ``loop`` output reports the iteration count.

Requirements:
  - AGENTSPAN_SERVER_URL=http://localhost:6767/api (default)
  - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini (default)
  - LLM key for the chosen model.
  - AGENTSPAN_BINSEARCH_SECRET (optional override; default 642)
"""

import json
import os
import sys
import time

import requests

SERVER_URL = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
BASE = SERVER_URL.rstrip("/").replace("/api", "")
MODEL = os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o-mini")
SECRET = int(os.environ.get("AGENTSPAN_BINSEARCH_SECRET", "642"))
MAX_ITER = int(os.environ.get("AGENTSPAN_DOWHILE_MAX_ITER", "12"))
WORKFLOW_NAME = "pae_replan_dowhile_demo"
WORKFLOW_VERSION = 2


def _model_split(model: str) -> tuple[str, str]:
    if "/" in model:
        provider, name = model.split("/", 1)
        return provider, name
    return "openai", model


PROVIDER, MODEL_NAME = _model_split(MODEL)


# ── INLINE script bodies (GraalJS) ────────────────────────────────


# Pull the first integer out of whatever the LLM returned ("537",
# "Guess: 537", "**I'll guess 537**").
EXTRACT_GUESS_JS = (
    "(function() {"
    "  var s = String($.llm_out || '');"
    "  var m = s.match(/-?\\d+/);"
    "  return m ? parseInt(m[0], 10) : null;"
    "})();"
)


# Compare the guess to the secret. Push the (iteration, guess, verdict)
# triple onto the history. Emit ``done`` when correct so DO_WHILE exits.
VERIFY_JS = (
    "(function() {"
    "  var g = $.guess;"
    "  var s = $.secret;"
    "  var h = $.history ? $.history.slice() : [];"
    "  var verdict;"
    "  if (g == null) verdict = 'invalid';"
    "  else if (g == s) verdict = 'correct';"
    "  else if (g < s) verdict = 'too_low';"
    "  else verdict = 'too_high';"
    "  h.push({iter: $.iter, guess: g, verdict: verdict});"
    "  var lo = $.lo;"
    "  var hi = $.hi;"
    "  if (verdict === 'too_low' && g != null && g + 1 > lo) lo = g + 1;"
    "  if (verdict === 'too_high' && g != null && g - 1 < hi) hi = g - 1;"
    "  return {verdict: verdict, guess: g, done: (verdict === 'correct'), "
    "          history: h, lo: lo, hi: hi};"
    "})();"
)


# Parse the reviewer LLM's JSON output. We only need the ``continue`` flag.
PARSE_REVIEW_JS = (
    "(function() {"
    "  var s = String($.llm_out || '');"
    "  var m = s.match(/\\{[\\s\\S]*\\}/);"
    "  if (!m) return {continue: true, feedback: '(no JSON in reviewer output)'};"
    "  try { return JSON.parse(m[0]); }"
    "  catch (e) { return {continue: true, feedback: '(JSON parse error: ' + e + ')'}; }"
    "})();"
)


# ── Workflow definition ───────────────────────────────────────────


def build_workflow_def() -> dict:
    """Construct the Conductor WorkflowDef JSON.

    The interesting bit is the ``DO_WHILE`` task at index 1. Its
    ``loopOver`` body runs once per iteration; each task in the body
    gets a ``__iN`` suffix in the actual workflow execution so you can
    see every iteration's tasks side-by-side in the task list.
    """
    return {
        "name": WORKFLOW_NAME,
        "version": WORKFLOW_VERSION,
        "description": "PAE plan-execute-replan loop wrapped in a single DO_WHILE",
        "tasks": [
            # 1. Initialise workflow variables with the search state.
            {
                "name": "SET_VARIABLE",
                "taskReferenceName": "init",
                "type": "SET_VARIABLE",
                "inputParameters": {
                    "history": [],
                    "done": False,
                    "lo": 1,
                    "hi": 1000,
                    "secret": "${workflow.input.secret}",
                },
            },
            # 2. The loop itself.
            {
                "name": "DO_WHILE",
                "taskReferenceName": "loop",
                "type": "DO_WHILE",
                # ``inputParameters`` are re-evaluated each iteration with the
                # latest ``__iN``-suffixed task outputs, which is how the
                # loopCondition gets at the verifier's ``done`` flag. You
                # can't reach ``${workflow.variables.X}`` from inside the JS
                # condition — only the names declared here on the loop task.
                "inputParameters": {
                    "loop": "${loop}",
                    "verify": "${verify}",
                },
                # Continue while we're under the budget and not yet done.
                "loopCondition": (
                    f"if ($.loop['iteration'] < {MAX_ITER} "
                    f"&& $.verify['result']['done'] != true) "
                    f"{{ true; }} else {{ false; }}"
                ),
                "loopOver": [
                    # 2a. Planner LLM — propose the next guess given the running history.
                    {
                        "name": "LLM_CHAT_COMPLETE",
                        "taskReferenceName": "planner_llm",
                        "type": "LLM_CHAT_COMPLETE",
                        "inputParameters": {
                            "llmProvider": PROVIDER,
                            "model": MODEL_NAME,
                            "maxTokens": 128,
                            "messages": [
                                {
                                    "role": "system",
                                    "message": (
                                        "You are a binary-search assistant. You will be told the "
                                        "history of guesses and the current bounds. Respond with "
                                        "ONLY the next integer to try — no prose, no JSON, no "
                                        "explanation. Use binary search (pick the midpoint of "
                                        "the remaining range)."
                                    ),
                                },
                                {
                                    "role": "user",
                                    "message": (
                                        "Secret is an integer in [1, 1000]. "
                                        "Current bounds: [${workflow.variables.lo}, "
                                        "${workflow.variables.hi}]. "
                                        "History so far: ${workflow.variables.history}. "
                                        "Your next guess?"
                                    ),
                                },
                            ],
                        },
                    },
                    # 2b. Extract the integer the planner emitted.
                    {
                        "name": "INLINE",
                        "taskReferenceName": "extract_guess",
                        "type": "INLINE",
                        "inputParameters": {
                            "evaluatorType": "graaljs",
                            "expression": EXTRACT_GUESS_JS,
                            "llm_out": "${planner_llm.output.result}",
                        },
                    },
                    # 2c. Deterministic verifier — the "compile + execute" of this demo.
                    {
                        "name": "INLINE",
                        "taskReferenceName": "verify",
                        "type": "INLINE",
                        "inputParameters": {
                            "evaluatorType": "graaljs",
                            "expression": VERIFY_JS,
                            "guess": "${extract_guess.output.result}",
                            "secret": "${workflow.variables.secret}",
                            "history": "${workflow.variables.history}",
                            "iter": "${loop.output.iteration}",
                            "lo": "${workflow.variables.lo}",
                            "hi": "${workflow.variables.hi}",
                        },
                    },
                    # 2d. Reviewer LLM — looks at the verdict and decides whether to replan.
                    {
                        "name": "LLM_CHAT_COMPLETE",
                        "taskReferenceName": "reviewer_llm",
                        "type": "LLM_CHAT_COMPLETE",
                        "inputParameters": {
                            "llmProvider": PROVIDER,
                            "model": MODEL_NAME,
                            "maxTokens": 128,
                            "messages": [
                                {
                                    "role": "system",
                                    "message": (
                                        "You are a search progress evaluator. The user is "
                                        "running a binary-search loop and just executed one "
                                        "iteration. Respond with ONLY a JSON object: "
                                        '{"continue": true|false, "feedback": "..."}. '
                                        "Set continue=false only when verdict == 'correct'."
                                    ),
                                },
                                {
                                    "role": "user",
                                    "message": (
                                        "Iteration verdict: ${verify.output.result.verdict}. "
                                        "Last guess: ${verify.output.result.guess}. "
                                        "New bounds: [${verify.output.result.lo}, "
                                        "${verify.output.result.hi}]. "
                                        "Should we continue?"
                                    ),
                                },
                            ],
                        },
                    },
                    # 2e. Parse the reviewer's JSON.
                    {
                        "name": "INLINE",
                        "taskReferenceName": "parse_review",
                        "type": "INLINE",
                        "inputParameters": {
                            "evaluatorType": "graaljs",
                            "expression": PARSE_REVIEW_JS,
                            "llm_out": "${reviewer_llm.output.result}",
                        },
                    },
                    # 2f. Persist this iteration's state back into workflow.variables
                    # so the next iteration's planner_llm sees it via the
                    # ${workflow.variables.X} references in its messages.
                    {
                        "name": "SET_VARIABLE",
                        "taskReferenceName": "update_state",
                        "type": "SET_VARIABLE",
                        "inputParameters": {
                            "history": "${verify.output.result.history}",
                            "done": "${verify.output.result.done}",
                            "lo": "${verify.output.result.lo}",
                            "hi": "${verify.output.result.hi}",
                            "secret": "${workflow.variables.secret}",
                        },
                    },
                ],
            },
        ],
        "inputParameters": ["secret"],
        "outputParameters": {
            "iterations": "${loop.output.iteration}",
            "history": "${workflow.variables.history}",
            "done": "${workflow.variables.done}",
        },
        "schemaVersion": 2,
        "ownerEmail": "demo@example.com",
    }


# ── Server interactions ───────────────────────────────────────────


def register_workflow(wf: dict) -> None:
    r = requests.post(
        f"{BASE}/api/metadata/workflow", json=[wf], headers={"Content-Type": "application/json"}
    )
    if r.status_code not in (200, 204):
        # 409 already-registered — try a PUT update instead.
        r2 = requests.put(
            f"{BASE}/api/metadata/workflow",
            json=[wf],
            headers={"Content-Type": "application/json"},
        )
        if r2.status_code not in (200, 204):
            raise RuntimeError(
                f"workflow registration failed: POST {r.status_code} {r.text}; "
                f"PUT {r2.status_code} {r2.text}"
            )


def start_execution() -> str:
    r = requests.post(
        f"{BASE}/api/workflow/{WORKFLOW_NAME}?version={WORKFLOW_VERSION}",
        json={"secret": SECRET},
        headers={"Content-Type": "application/json"},
    )
    r.raise_for_status()
    return r.text.strip().strip('"')


def poll_until_done(execution_id: str, timeout: int = 300) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(f"{BASE}/api/workflow/{execution_id}?includeTasks=true")
        r.raise_for_status()
        wf = r.json()
        status = wf.get("status")
        if status in ("COMPLETED", "FAILED", "TERMINATED", "TIMED_OUT"):
            return wf
        time.sleep(2)
    raise TimeoutError(f"workflow {execution_id} did not complete in {timeout}s")


# ── Pretty printing ──────────────────────────────────────────────


def print_iteration_summary(wf: dict) -> None:
    """Walk the task list and print one row per DO_WHILE iteration.

    Conductor suffixes loopOver task refs with ``__<iteration>``
    (e.g. ``planner_llm__1``, ``planner_llm__2``). Group by the
    suffix to reconstruct the per-iteration view.
    """
    import re

    tasks = wf.get("tasks", [])
    suffix_re = re.compile(r"^(.+?)__(\d+)$")
    by_iter: dict[int, dict] = {}
    for t in tasks:
        ref = t.get("referenceTaskName", "")
        m = suffix_re.match(ref)
        if not m:
            continue
        base, iter_n = m.group(1), int(m.group(2))
        slot = by_iter.setdefault(iter_n, {})
        slot[base] = t

    print(f"{'iter':>5}  {'guess':>6}  {'verdict':<10}  {'new bounds':<14}  {'continue?':>9}")
    print("─" * 65)
    for n in sorted(by_iter):
        row = by_iter[n]
        verify = row.get("verify", {})
        result = verify.get("outputData", {}).get("result", {}) if verify else {}
        review = row.get("parse_review", {})
        review_out = review.get("outputData", {}).get("result", {}) if review else {}
        cont = review_out.get("continue") if isinstance(review_out, dict) else None
        guess = result.get("guess")
        verdict = result.get("verdict", "?")
        lo, hi = result.get("lo"), result.get("hi")
        print(
            f"{n:>5}  {str(guess):>6}  {verdict:<10}  "
            f"[{lo!s:>4},{hi!s:>4}]  {str(cont):>9}"
        )


def main(argv: list[str]) -> None:
    print(f"server: {BASE}")
    print(f"model:  {MODEL}")
    print(f"secret: {SECRET}")
    print(f"max:    {MAX_ITER} iterations\n")

    wf_def = build_workflow_def()
    print("registering workflow def...")
    register_workflow(wf_def)
    print(f"  OK: {WORKFLOW_NAME} v{WORKFLOW_VERSION}\n")

    print("starting execution...")
    execution_id = start_execution()
    print(f"  execution_id: {execution_id}\n")

    print("polling until done...")
    wf = poll_until_done(execution_id)
    print(f"  status: {wf['status']}\n")

    print(f"final output: {json.dumps(wf.get('output', {}), indent=2)}\n")

    print("── per-iteration summary (inside the single workflow) ──")
    print_iteration_summary(wf)
    print()

    # Surface a couple of task-ref names so you can curl them yourself.
    import re

    iter_refs = sorted(
        {
            t["referenceTaskName"]
            for t in wf.get("tasks", [])
            if re.search(r"__\d+$", t.get("referenceTaskName", ""))
        }
    )
    print(f"sample task refs ({len(iter_refs)} total):")
    for r in iter_refs[:6]:
        print(f"  {r}")
    if len(iter_refs) > 6:
        print(f"  ... (+{len(iter_refs) - 6} more)")
    print()
    print(f"inspect: curl {BASE}/api/workflow/{execution_id}?includeTasks=true | jq .")


if __name__ == "__main__":
    main(sys.argv)
