#!/usr/bin/env python3
"""Deterministic verifier for the previousResponseId / context-window fix.

Run against any executed agentspan workflow to check the structural invariants
that were broken in executions cfca8846, 3d5177a8, 9652d956, d29d0267, etc.:

    python3 sdk/python/scripts/verify_fix.py <workflow_id>
    python3 sdk/python/scripts/verify_fix.py 1c2f5baf-f62a-4093-bed6-44ae8951e85a

Exits 0 on PASS, 1 on FAIL. No LLM, no flakiness — just inspects the
LLM_CHAT_COMPLETE task inputs/outputs that the server already persisted.

Checks (each independent):
  1. previousResponseId is NEVER set on any LLM task's inputData
     (proves the conductor AIModelTaskMapper.threadPreviousResponseId
     disable is in the running jar)
  2. chars/token ratio per turn stays >= 2.0
     (BPE floor for JSON is ~2.5; anything below 2.0 implies phantom
     tokens from server-side state we don't control — the symptom that
     drove the context_length_exceeded loop)
  3. No LLM-emitted tool call uses a name absent from the agent's
     declared tools array
     (proves the enrichToolsScript prefill-leak guard works)
  4. condenseIfNeeded fires before any single LLM task billed > 90%
     of the model's context window
     (proves the proactive trigger threshold is sane)
  5. No iteration ends with status FAILED + 400 context_length_exceeded
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

SERVER_BASE = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api").rstrip("/")
# tolerate URLs given with or without /api suffix
if SERVER_BASE.endswith("/api"):
    SERVER_BASE = SERVER_BASE[: -len("/api")]

# OpenAI BPE practical floor for JSON-shaped content. Below this, the token
# count must be coming from somewhere we didn't send (e.g. previous_response_id
# carry-over).
JSON_BPE_FLOOR = 2.0


def fetch_workflow(workflow_id: str) -> dict:
    url = f"{SERVER_BASE}/api/workflow/{workflow_id}?includeTasks=true"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"HTTP {e.code} fetching {url}: {e.read()[:300]!r}\n")
        sys.exit(2)
    except urllib.error.URLError as e:
        sys.stderr.write(f"Connection failed for {url}: {e}\n")
        sys.exit(2)


def llm_tasks(wf: dict) -> list[dict]:
    return [t for t in wf.get("tasks", []) if t.get("taskType") == "LLM_CHAT_COMPLETE"]


def check_no_previous_response_id(llms: list[dict]) -> tuple[bool, str]:
    offenders = [
        (i, (t.get("inputData") or {}).get("previousResponseId"))
        for i, t in enumerate(llms)
        if (t.get("inputData") or {}).get("previousResponseId")
    ]
    if offenders:
        sample = offenders[:3]
        return False, f"previousResponseId set on {len(offenders)} iter(s): {sample}"
    return True, f"previousResponseId is None on all {len(llms)} iter(s)"


def check_chars_per_token_floor(llms: list[dict]) -> tuple[bool, str]:
    violations = []
    ratios = []
    for i, t in enumerate(llms):
        ind = t.get("inputData") or {}
        od = t.get("outputData") or {}
        prompt = od.get("promptTokens")
        if not prompt or prompt <= 0:
            continue
        chars = len(json.dumps(ind))
        ratio = chars / prompt
        ratios.append(ratio)
        if ratio < JSON_BPE_FLOOR:
            violations.append((i, round(ratio, 2), chars, prompt))
    if violations:
        return False, (
            f"{len(violations)} iter(s) have chars/token below {JSON_BPE_FLOOR} "
            f"(phantom token billing): {violations[:5]}"
        )
    if not ratios:
        return True, "no billed iterations to measure (nothing failed yet)"
    return True, (
        f"chars/token in range [{min(ratios):.2f}, {max(ratios):.2f}] across "
        f"{len(ratios)} billed iter(s) — no phantom tokens"
    )


def check_no_unknown_tool_dispatches(wf: dict, llms: list[dict]) -> tuple[bool, str]:
    # Collect the declared tool names from the *first* LLM task's input.
    if not llms:
        return True, "no LLM tasks to check"
    declared = set()
    for tool in (llms[0].get("inputData") or {}).get("tools") or []:
        if isinstance(tool, dict) and tool.get("name"):
            declared.add(tool["name"])
    # Any task whose taskDefName isn't a system task, isn't a prefill, and isn't
    # in declared, is a leak.
    sys_types = {
        "LLM_CHAT_COMPLETE",
        "INLINE",
        "FORK",
        "JOIN",
        "FORK_JOIN",
        "FORK_JOIN_DYNAMIC",
        "SWITCH",
        "SET_VARIABLE",
        "DO_WHILE",
        "SUB_WORKFLOW",
    }
    leaks = []
    for t in wf.get("tasks", []):
        ref = t.get("referenceTaskName") or ""
        name = t.get("taskDefName") or ""
        typ = t.get("taskType") or ""
        if typ in sys_types:
            continue
        if "_prefill_" in ref:
            continue  # prefill tasks are deterministic, not LLM-emitted
        # Anything else is an LLM-dispatched tool call. Its name must be declared.
        if not name or name in sys_types:
            continue
        # Internal agentspan tasks (ctx_inject, stop_when, etc.) — skip.
        if name.startswith("issue_fixer_") or name.endswith("_stop_when"):
            continue
        if name not in declared:
            leaks.append((ref, name, typ))
    if leaks:
        return False, (
            f"{len(leaks)} task(s) dispatched with names absent from declared "
            f"tools={sorted(declared)}: {leaks[:5]}"
        )
    return True, f"all dispatched tool tasks match the declared {len(declared)}-tool array"


def check_proactive_trigger_before_wall(llms: list[dict]) -> tuple[bool, str]:
    # If any iter's promptTokens exceeded 90% of (contextWindow - maxTokens),
    # condenseIfNeeded should have fired no later than that turn.
    misses = []
    for i, t in enumerate(llms):
        ind = t.get("inputData") or {}
        od = t.get("outputData") or {}
        prompt = od.get("promptTokens")
        if not prompt:
            continue
        # We don't know contextWindow exactly without modelContextWindows lookup,
        # but for gpt-5.3-codex (the typical coder model) it's 400_000.
        # Coder configures maxTokens=32000, so inputBudget = 368_000.
        # 90% of that is 331_200.
        if prompt > 331_200 and not ind.get("_condensation"):
            misses.append((i, prompt))
    if misses:
        return False, (
            f"{len(misses)} iter(s) sent > 90% of inputBudget without condensation: {misses[:3]}"
        )
    return True, "proactive condensation fired (or not needed) before 90% wall"


def check_no_context_overflow_failures(wf: dict, llms: list[dict]) -> tuple[bool, str]:
    failures = []
    for i, t in enumerate(llms):
        if t.get("status") != "FAILED":
            continue
        reason = t.get("reasonForIncompletion") or ""
        if "context_length_exceeded" in reason:
            failures.append(i)
    if failures:
        return False, f"context_length_exceeded on iter(s) {failures}"
    return True, "no context_length_exceeded failures in this workflow"


# Inspection-budget enforcement: the gate at
# ``_record_inspection`` is supposed to fire after
# ``_CODER_INSPECTION_BUDGET_BEFORE_EDIT`` (= 10) calls before the first
# successful edit. With the in-memory counter (pre-fix) the gate never fired
# because each worker process had its own counter — observed in workflow
# ``fb257ccd-e3e2-468e-9a4b-50b0b3284b15`` where 408 inspections went through
# unblocked. Cap chosen with slack for the FORK_JOIN cohort already in flight
# when the gate fires (the LLM may emit 4–6 parallel calls in one turn).
INSPECTION_HARD_CAP = 25
INSPECTION_TOOL_NAMES = {
    "grep_search",
    "read_file",
    "read_symbol",
    "glob_find",
    "file_outline",
    "search_symbols",
    "list_directory",
}
EDIT_TOOL_NAMES = {"write_file", "edit_file", "edit_files", "apply_patch"}


def check_coder_inspection_budget(wf: dict, _llms: list[dict]) -> tuple[bool, str]:
    if wf.get("workflowName") != "issue_fixer_coder":
        return True, "not an issue_fixer_coder workflow; skipping"
    counts: dict[str, int] = {}
    for t in wf.get("tasks", []):
        name = t.get("taskDefName") or ""
        ref = t.get("referenceTaskName") or ""
        if "_prefill_" in ref:
            continue
        if name in INSPECTION_TOOL_NAMES:
            counts[name] = counts.get(name, 0) + 1
    total = sum(counts.values())
    if total > INSPECTION_HARD_CAP:
        return False, (
            f"coder ran {total} inspections ({counts}) — exceeds cap of "
            f"{INSPECTION_HARD_CAP}. Budget gate at _record_inspection should "
            f"have fired after 10 + cohort-slack"
        )
    return True, f"coder ran {total} inspections ({counts}); within cap"


def check_coder_actually_edited(wf: dict, _llms: list[dict]) -> tuple[bool, str]:
    if wf.get("workflowName") != "issue_fixer_coder":
        return True, "not an issue_fixer_coder workflow; skipping"
    edits = 0
    by_tool: dict[str, int] = {}
    for t in wf.get("tasks", []):
        name = t.get("taskDefName") or ""
        ref = t.get("referenceTaskName") or ""
        if "_prefill_" in ref:
            continue
        if name in EDIT_TOOL_NAMES:
            edits += 1
            by_tool[name] = by_tool.get(name, 0) + 1
    if edits == 0:
        return False, (
            "coder made ZERO file edits — investigation-only loop. Budget "
            "gate or instructions failed to force action."
        )
    return True, f"coder dispatched {edits} edit(s): {by_tool}"


def check_coder_wrote_implementation_report(wf: dict, _llms: list[dict]) -> tuple[bool, str]:
    if wf.get("workflowName") != "issue_fixer_coder":
        return True, "not an issue_fixer_coder workflow; skipping"
    count = sum(
        1 for t in wf.get("tasks", []) if t.get("taskDefName") == "write_implementation_report"
    )
    if count == 0:
        return False, (
            "coder never called write_implementation_report — agent did not "
            "wrap up (either successfully or with a blocker)"
        )
    return True, f"write_implementation_report called {count} time(s)"


CHECKS = [
    ("no previousResponseId on LLM tasks", check_no_previous_response_id),
    ("chars/token >= 2.0 (no phantom tokens)", check_chars_per_token_floor),
    ("no LLM-dispatched tool calls outside declared tools[]", check_no_unknown_tool_dispatches),
    ("proactive condensation triggers before wall", check_proactive_trigger_before_wall),
    ("no context_length_exceeded failures", check_no_context_overflow_failures),
    ("coder inspection budget enforced", check_coder_inspection_budget),
    ("coder actually edited at least one file", check_coder_actually_edited),
    ("coder wrote an implementation report", check_coder_wrote_implementation_report),
]


def main() -> int:
    if len(sys.argv) != 2:
        sys.stderr.write(f"usage: {sys.argv[0]} <workflow_id>\n")
        return 2
    workflow_id = sys.argv[1]
    print(f"verifying workflow {workflow_id} against {SERVER_BASE}")
    wf = fetch_workflow(workflow_id)
    llms = llm_tasks(wf)
    print(
        f"  workflowName={wf.get('workflowName')!r}  status={wf.get('status')!r}  "
        f"LLM iters={len(llms)}"
    )
    print()

    wf_aware = {
        check_no_unknown_tool_dispatches,
        check_no_context_overflow_failures,
        check_coder_inspection_budget,
        check_coder_actually_edited,
        check_coder_wrote_implementation_report,
    }
    all_pass = True
    for label, fn in CHECKS:
        try:
            if fn in wf_aware:
                ok, msg = fn(wf, llms)
            else:
                ok, msg = fn(llms)
        except Exception as exc:
            ok, msg = False, f"check raised: {exc!r}"
        marker = "PASS" if ok else "FAIL"
        print(f"  [{marker}] {label}")
        print(f"         {msg}")
        if not ok:
            all_pass = False

    print()
    print("=" * 60)
    print("RESULT:", "PASS" if all_pass else "FAIL")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
