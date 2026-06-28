#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""112 — Plan-Execute-Replan loop INSIDE a single Conductor workflow.

Examples 109/110/111 keep the replan loop in Python user code: each
iteration is a separate top-level workflow execution. This example
does the opposite — it hand-builds a Conductor WorkflowDef whose body
is a ``DO_WHILE`` task that wraps the full plan → COMPILE → EXECUTE →
review cycle, **using the real ``PLAN_AND_COMPILE`` system task plus a
dynamic ``SUB_WORKFLOW`` inside the loop**. ONE workflow ID for the
whole run; iterations show up as ``planner_llm__1``,
``plan_and_compile__1``, ``plan_exec__1``, ``reviewer_llm__1``, ... in
the same workflow's task list.

The DO_WHILE body each iteration:

  1. ``planner_llm``       — LLM proposes the next guess given history.
  2. ``extract_guess``     — INLINE parses the integer from LLM text.
  3. ``build_plan``        — INLINE wraps the integer into a PAC-shaped
                             plan JSON: a single step calling
                             ``check_guess(n=<guess>)``.
  4. ``plan_and_compile``  — the **real PAC task**: compiles the plan
                             JSON into a Conductor WorkflowDef.
  5. ``plan_exec``         — SUB_WORKFLOW that executes PAC's
                             dynamically-compiled WorkflowDef. The
                             compiled sub-workflow runs a SIMPLE task
                             against the ``check_guess`` worker we
                             register from this process.
  6. ``reviewer_llm``      — LLM looks at the verdict, emits a JSON
                             ``{continue, feedback}`` advisory.
  7. ``parse_review``      — INLINE extracts the continue flag.
  8. ``update_state``      — SET_VARIABLE pushes new bounds into
                             ``workflow.variables`` so the next
                             iteration's ``planner_llm`` sees them.

Loop condition: keep going while ``done != true`` AND iteration count
is under the budget.

This is the shape of a *first-class* ``Strategy.PLAN_EXECUTE_REPLAN``
that doesn't exist in Agentspan today (dg-review finding F1,
recommendation #2). The example builds it by hand to show the full
plan→compile→execute→replan structure end-to-end inside one workflow.

Requirements:
  - AGENTSPAN_SERVER_URL=http://localhost:6767/api (default)
  - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini (default)
  - LLM key for the chosen model.
  - AGENTSPAN_BINSEARCH_SECRET (optional override; default 642)
"""

import json
import os
import re
import sys
import time

import requests

from conductor.ai.agents import AgentRuntime, plan_execute, tool

SERVER_URL = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
BASE = SERVER_URL.rstrip("/").replace("/api", "")
MODEL = os.environ.get("AGENTSPAN_LLM_MODEL", "anthropic/claude-sonnet-4-6")
SECRET = int(os.environ.get("AGENTSPAN_BINSEARCH_SECRET", "642"))
MAX_ITER = int(os.environ.get("AGENTSPAN_DOWHILE_MAX_ITER", "12"))
WORKFLOW_NAME = "pae_replan_dowhile_demo"
WORKFLOW_VERSION = 5


def _model_split(model: str) -> tuple[str, str]:
    if "/" in model:
        provider, name = model.split("/", 1)
        return provider, name
    return "openai", model


PROVIDER, MODEL_NAME = _model_split(MODEL)


# ── The tool the compiled plan invokes ───────────────────────────


@tool
def check_guess(n: int) -> dict:
    """Compare a candidate integer to the hidden secret.

    PAC will compile a plan into a sub-workflow that calls this tool
    via a SIMPLE task. The worker for it is registered by this
    process's ``AgentRuntime``.

    Returns the verdict wrapped in ``{"result": ...}`` so PAC's
    compiled-sub-workflow ``outputParameters`` (which references
    ``${last_op.output.result}``) surfaces it to the outer DO_WHILE.
    Without the wrapper, the sub-workflow's ``output.result`` is null
    and the outer loop can't read what just happened.
    """
    n_int = int(n)
    if n_int == SECRET:
        verdict = "correct"
    elif n_int < SECRET:
        verdict = "too_low"
    else:
        verdict = "too_high"
    return {"result": {"verdict": verdict, "guess": n_int, "done": verdict == "correct"}}


# ── INLINE script bodies (GraalJS) ────────────────────────────────


EXTRACT_GUESS_JS = (
    "(function() {"
    "  var s = String($.llm_out || '');"
    "  var m = s.match(/-?\\d+/);"
    "  return m ? parseInt(m[0], 10) : null;"
    "})();"
)


# Wrap the LLM-proposed guess into the JSON plan shape PAC consumes.
# A single step with one operation that calls check_guess(n=<guess>).
BUILD_PLAN_JS = (
    "(function() {"
    "  var g = $.guess;"
    "  var plan = {"
    "    steps: ["
    "      {id: 'check', operations: ["
    "        {tool: 'check_guess', args: {n: g}}"
    "      ]}"
    "    ]"
    "  };"
    "  return JSON.stringify(plan);"
    "})();"
)


# Pull the verdict map out of the SUB_WORKFLOW's nested task output.
# The compiled plan's SIMPLE task for check_guess writes its return value
# into the sub-workflow output; PAC routes it through step_output_check.
EXTRACT_VERDICT_JS = (
    "(function() {"
    "  var ex = $.exec_output;"
    "  if (!ex) return {verdict: 'missing', guess: null, done: false,"
    "                   raw: '(no exec output)'};"
    "  if (ex.step_outputs && ex.step_outputs.check) {"
    "    return ex.step_outputs.check;"
    "  }"
    "  if (ex.result && typeof ex.result === 'object') return ex.result;"
    "  if (typeof ex.result === 'string') {"
    "    try { return JSON.parse(ex.result); } catch(e) {}"
    "  }"
    "  return {verdict: 'unknown', guess: null, done: false, raw: JSON.stringify(ex)};"
    "})();"
)


PARSE_REVIEW_JS = (
    "(function() {"
    "  var s = String($.llm_out || '');"
    "  var m = s.match(/\\{[\\s\\S]*\\}/);"
    "  if (!m) return {continue: true, feedback: '(no JSON in reviewer output)'};"
    "  try { return JSON.parse(m[0]); }"
    "  catch (e) { return {continue: true, feedback: '(JSON parse error: ' + e + ')'}; }"
    "})();"
)


# Derive new search bounds AND append to history so the next planner_llm
# sees the full prior context in ${workflow.variables.lo|hi|history}.
UPDATE_BOUNDS_JS = (
    "(function() {"
    "  var v = $.verdict;"
    "  var lo = $.lo;"
    "  var hi = $.hi;"
    "  var g = $.guess;"
    "  var h = $.history ? $.history.slice() : [];"
    "  if (v === 'too_low' && g != null && g + 1 > lo) lo = g + 1;"
    "  if (v === 'too_high' && g != null && g - 1 < hi) hi = g - 1;"
    "  h.push({guess: g, verdict: v});"
    "  return {lo: lo, hi: hi, history: h};"
    "})();"
)


# ── Workflow definition ───────────────────────────────────────────


def build_workflow_def(check_guess_tool_def: dict | None = None) -> dict:
    """Construct the Conductor WorkflowDef JSON.

    The DO_WHILE body uses the real ``PLAN_AND_COMPILE`` task plus a
    dynamic ``SUB_WORKFLOW`` so each iteration genuinely compiles a
    new plan and runs it against the registered ``check_guess`` worker.
    """
    return {
        "name": WORKFLOW_NAME,
        "version": WORKFLOW_VERSION,
        "description": "PAE plan-execute-replan loop wrapped in a single DO_WHILE with real PAC + SUB_WORKFLOW",
        "tasks": [
            {
                "name": "SET_VARIABLE",
                "taskReferenceName": "init",
                "type": "SET_VARIABLE",
                "inputParameters": {
                    "lo": 1,
                    "hi": 1000,
                    "history": [],
                    "secret": "${workflow.input.secret}",
                },
            },
            {
                "name": "DO_WHILE",
                "taskReferenceName": "loop",
                "type": "DO_WHILE",
                "inputParameters": {
                    "loop": "${loop}",
                    "extract_verdict": "${extract_verdict}",
                },
                "loopCondition": (
                    f"if ($.loop['iteration'] < {MAX_ITER} "
                    f"&& $.extract_verdict['result']['done'] != true) "
                    f"{{ true; }} else {{ false; }}"
                ),
                "loopOver": [
                    {
                        "name": "LLM_CHAT_COMPLETE",
                        "taskReferenceName": "planner_llm",
                        "type": "LLM_CHAT_COMPLETE",
                        "inputParameters": {
                            "llmProvider": PROVIDER,
                            "model": MODEL_NAME,
                            "maxTokens": 64,
                            "messages": [
                                {
                                    "role": "system",
                                    "message": (
                                        "You are a binary-search assistant searching for a "
                                        "hidden integer. You will be given the current valid "
                                        "range [low, high] and the history of prior guesses + "
                                        "their verdicts ('too_low', 'too_high'). Your job: "
                                        "pick the MIDPOINT of the current range — i.e. "
                                        "floor((low + high) / 2). Respond with ONLY that "
                                        "integer. No prose, no JSON, no explanation."
                                    ),
                                },
                                {
                                    "role": "user",
                                    "message": (
                                        "Current valid range: [${workflow.variables.lo}, "
                                        "${workflow.variables.hi}]. "
                                        "Prior guesses and verdicts: "
                                        "${workflow.variables.history}. "
                                        "Compute the midpoint of the current range and emit "
                                        "ONLY that integer."
                                    ),
                                },
                            ],
                        },
                    },
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
                    {
                        "name": "INLINE",
                        "taskReferenceName": "build_plan",
                        "type": "INLINE",
                        "inputParameters": {
                            "evaluatorType": "graaljs",
                            "expression": BUILD_PLAN_JS,
                            "guess": "${extract_guess.output.result}",
                        },
                    },
                    {
                        "name": "plan_and_compile",
                        "taskReferenceName": "plan_and_compile",
                        "type": "PLAN_AND_COMPILE",
                        "inputParameters": {
                            "planJson": "${build_plan.output.result}",
                            "parentName": WORKFLOW_NAME,
                            "model": MODEL,
                            "knownToolNames": ["check_guess"],
                            # parentTools — pass the real ToolConfig so PAC
                            # routes check_guess as a SIMPLE worker task
                            # rather than rejecting it.
                            **(
                                {"parentTools": [check_guess_tool_def]}
                                if check_guess_tool_def
                                else {}
                            ),
                        },
                    },
                    {
                        "name": "SUB_WORKFLOW",
                        "taskReferenceName": "plan_exec",
                        "type": "SUB_WORKFLOW",
                        "subWorkflowParam": {
                            "name": f"pe_{WORKFLOW_NAME}_plan",
                            "version": 1,
                            "workflowDefinition": "${plan_and_compile.output.workflowDef}",
                        },
                        "inputParameters": {
                            "prompt": "${workflow.input.secret}",
                        },
                        "optional": True,
                    },
                    {
                        "name": "INLINE",
                        "taskReferenceName": "extract_verdict",
                        "type": "INLINE",
                        "inputParameters": {
                            "evaluatorType": "graaljs",
                            "expression": EXTRACT_VERDICT_JS,
                            "exec_output": "${plan_exec.output}",
                        },
                    },
                    {
                        "name": "INLINE",
                        "taskReferenceName": "compute_bounds",
                        "type": "INLINE",
                        "inputParameters": {
                            "evaluatorType": "graaljs",
                            "expression": UPDATE_BOUNDS_JS,
                            "verdict": "${extract_verdict.output.result.verdict}",
                            "guess": "${extract_verdict.output.result.guess}",
                            "lo": "${workflow.variables.lo}",
                            "hi": "${workflow.variables.hi}",
                            "history": "${workflow.variables.history}",
                        },
                    },
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
                                        "You are a search progress evaluator. Respond with ONLY "
                                        'a JSON object: {"continue": true|false, "feedback": "..."}. '
                                        "Set continue=false only when verdict == 'correct'."
                                    ),
                                },
                                {
                                    "role": "user",
                                    "message": (
                                        "Iteration verdict: ${extract_verdict.output.result.verdict}. "
                                        "Last guess: ${extract_verdict.output.result.guess}. "
                                        "New bounds: [${compute_bounds.output.result.lo}, "
                                        "${compute_bounds.output.result.hi}]. "
                                        "Should we continue?"
                                    ),
                                },
                            ],
                        },
                    },
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
                    {
                        "name": "SET_VARIABLE",
                        "taskReferenceName": "update_state",
                        "type": "SET_VARIABLE",
                        "inputParameters": {
                            "lo": "${compute_bounds.output.result.lo}",
                            "hi": "${compute_bounds.output.result.hi}",
                            "history": "${compute_bounds.output.result.history}",
                            "secret": "${workflow.variables.secret}",
                        },
                    },
                ],
            },
        ],
        "inputParameters": ["secret"],
        "outputParameters": {
            "iterations": "${loop.output.iteration}",
            "final_verdict": "${extract_verdict.output.result}",
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
    tasks = wf.get("tasks", [])
    suffix_re = re.compile(r"^(.+?)__(\d+)$")
    by_iter: dict[int, dict] = {}
    for t in tasks:
        ref = t.get("referenceTaskName", "")
        m = suffix_re.match(ref)
        if not m:
            continue
        base, n = m.group(1), int(m.group(2))
        slot = by_iter.setdefault(n, {})
        slot[base] = t

    print(f"{'iter':>5}  {'guess':>6}  {'verdict':<10}  {'new bounds':<14}  {'continue?':>9}")
    print("─" * 65)
    for n in sorted(by_iter):
        row = by_iter[n]
        verdict_task = row.get("extract_verdict", {})
        verdict = (verdict_task.get("outputData", {}) or {}).get("result", {}) or {}
        bounds_task = row.get("compute_bounds", {})
        bounds = (bounds_task.get("outputData", {}) or {}).get("result", {}) or {}
        review = row.get("parse_review", {})
        review_out = (review.get("outputData", {}) or {}).get("result", {}) or {}
        cont = review_out.get("continue") if isinstance(review_out, dict) else None
        print(
            f"{n:>5}  {str(verdict.get('guess')):>6}  "
            f"{verdict.get('verdict', '?'):<10}  "
            f"[{bounds.get('lo')!s:>4},{bounds.get('hi')!s:>4}]  "
            f"{str(cont):>9}"
        )


def main(argv: list[str]) -> None:
    print(f"server: {BASE}")
    print(f"model:  {MODEL}")
    print(f"secret: {SECRET}")
    print(f"max:    {MAX_ITER} iterations\n")

    # 1. Build a dummy harness whose only purpose is to register the
    #    ``check_guess`` worker AND give us a serialized ToolConfig the
    #    workflow def's PAC task can use as ``parentTools``.
    print("setting up check_guess worker via AgentRuntime...")
    harness = plan_execute(
        name="check_harness",
        tools=[check_guess],
        planner_instructions="(unused — workers register at deploy time)",
        model=MODEL,
    )

    # Serialize the tool def so PAC's allowlist + SIMPLE-task emission
    # picks check_guess up correctly.
    from conductor.ai.agents.config_serializer import AgentConfigSerializer

    ac = AgentConfigSerializer().serialize(harness)
    check_guess_def = next((t for t in ac.get("tools", []) if t.get("name") == "check_guess"), None)
    if check_guess_def is None:
        raise RuntimeError("could not serialize check_guess tool config")

    with AgentRuntime() as runtime:
        # 2. Register the worker (serve, non-blocking).
        runtime.serve(harness, blocking=False)
        print("  workers serving: check_guess\n")

        # 3. Register the workflow def.
        wf_def = build_workflow_def(check_guess_tool_def=check_guess_def)
        print("registering workflow def...")
        register_workflow(wf_def)
        print(f"  OK: {WORKFLOW_NAME} v{WORKFLOW_VERSION}\n")

        # 4. Start the execution.
        print("starting execution...")
        execution_id = start_execution()
        print(f"  execution_id: {execution_id}\n")

        # 5. Poll until done.
        print("polling until done...")
        wf = poll_until_done(execution_id)
        print(f"  status: {wf['status']}\n")

    print(f"final output: {json.dumps(wf.get('output', {}), indent=2)}\n")

    print("── per-iteration summary (inside the single workflow) ──")
    print_iteration_summary(wf)
    print()

    iter_refs = sorted(
        {
            t["referenceTaskName"]
            for t in wf.get("tasks", [])
            if re.search(r"__\d+$", t.get("referenceTaskName", ""))
        }
    )
    distinct_bases = sorted({re.sub(r"__\d+$", "", r) for r in iter_refs})
    print(f"task suffixes: {len(iter_refs)} total task instances")
    print(f"distinct task types in loop body: {distinct_bases}")
    print()
    print(f"inspect: curl {BASE}/api/workflow/{execution_id}?includeTasks=true | jq .")


if __name__ == "__main__":
    main(sys.argv)
