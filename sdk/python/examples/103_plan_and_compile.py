#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""PLAN_AND_COMPILE — server-side plan compiler in action.

A planner agent produces a JSON DAG; the server's ``PLAN_AND_COMPILE`` Java
task converts it into a Conductor ``WorkflowDef`` that runs deterministically.
After the run finishes, this example reaches into Conductor and prints what
the compiler produced — stepCount, taskCount, the dynamic workflow's name —
so you can see the compile output, not just the agent answer.

The plan combines:
  - ``args`` operations (deterministic tool calls — no LLM)
  - ``generate`` operations (LLM produces the args, then the tool runs)
  - parallel + sequential steps (DAG via ``depends_on``)
  - a ``validation`` block with a sandboxed success_condition

Usage:
    AGENTSPAN_SERVER_URL=http://localhost:6767/api \\
    OPENAI_API_KEY=... \\
    python 103_plan_and_compile.py "Compute factorials of 1..5 and explain"

Requirements:
  - Agentspan server running with PLAN_AND_COMPILE registered
  - OPENAI_API_KEY (or whichever provider matches AGENTSPAN_LLM_MODEL)
"""

import math
import os
import sys

import requests

from conductor.ai.agents import AgentRuntime, plan_execute, tool
from settings import settings


SERVER_URL = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
CONDUCTOR_BASE = SERVER_URL.rstrip("/").replace("/api", "")


# ── Tools ───────────────────────────────────────────────────────────


@tool
def factorial(n: int) -> str:
    """Compute n! and return it as a string.

    Args:
        n: Non-negative integer. Capped at 20 to keep things sane.
    """
    if n < 0 or n > 20:
        return f"ERROR: n must be in [0, 20], got {n}"
    return str(math.factorial(n))


@tool
def write_summary(text: str) -> str:
    """Persist a short summary string. Returns it back for the validator."""
    print(f"[write_summary] {text}")
    return text


@tool
def check_summary(text: str, min_chars: int) -> str:
    """Return JSON ``{passed, length, min_chars}`` for the validator.

    Args:
        text: The summary to check.
        min_chars: Minimum acceptable length in characters.
    """
    import json as _json
    return _json.dumps({"passed": len(text) >= min_chars, "length": len(text), "min_chars": min_chars})


# ── Planner instructions ────────────────────────────────────────────

# Domain-only instructions. The server appends ``## Available tools`` and
# ``## Plan schema`` blocks at compile time — no need to repeat the JSON
# shape or tool signatures here.
PLANNER_INSTRUCTIONS = """\
You are a math-explainer planner. Plan a workflow that:

1. Computes factorials of 1, 2, 3, 4, 5 in PARALLEL using ``factorial`` (static args).
2. Writes a short prose summary about factorial growth using ``write_summary``
   (use a ``generate`` block — the LLM produces the ``text`` arg at run time).
3. Validates the summary is at least 30 characters via ``check_summary``,
   with ``success_condition: "$.passed === true"``.
"""


# ── Helpers ─────────────────────────────────────────────────────────


def find_plan_and_compile_output(execution_id: str) -> dict | None:
    """Walk the workflow tree (parent + sub-workflows) and return the first
    ``PLAN_AND_COMPILE`` task's output, or ``None`` if not found."""
    seen: set[str] = set()
    pending = [execution_id]
    while pending:
        wf_id = pending.pop()
        if wf_id in seen:
            continue
        seen.add(wf_id)
        try:
            resp = requests.get(
                f"{CONDUCTOR_BASE}/api/workflow/{wf_id}",
                params={"includeTasks": "true"},
                timeout=10,
            )
            resp.raise_for_status()
        except requests.RequestException:
            continue
        wf = resp.json()
        for t in wf.get("tasks", []):
            if t.get("taskType") == "PLAN_AND_COMPILE":
                return t.get("outputData") or {}
            sub_id = t.get("subWorkflowId")
            if sub_id and sub_id not in seen:
                pending.append(sub_id)
    return None


# ── Main ────────────────────────────────────────────────────────────


def main() -> int:
    s = settings  # already-loaded module-level Settings instance

    topic = " ".join(sys.argv[1:]) or "factorials"

    # ``plan_execute()`` builds the planner+fallback+harness trio in one
    # call. ``tools`` is the canonical plan-executable set: every
    # ``op.tool`` in the plan is validated against this list (unknown
    # names route to fallback instead of hanging a SIMPLE), and the
    # runtime starts pollers for these tools automatically.
    harness = plan_execute(
        name="plan_and_compile_demo",
        tools=[factorial, write_summary, check_summary],
        planner_instructions=PLANNER_INSTRUCTIONS,
        fallback_instructions="The plan failed. Use the available tools to recover.",
        model=s.llm_model,
        fallback_max_turns=4,
    )

    print(f"\n=== PLAN_AND_COMPILE demo ===\nTopic: {topic}\nModel: {s.llm_model}\n")

    with AgentRuntime() as rt:
        result = rt.run(harness, f"Topic: {topic}")

    print(f"\n--- agent result ---")
    print(f"status:        {result.status}")
    print(f"execution_id:  {result.execution_id}")
    print(f"output:        {result.output}\n")

    pac = find_plan_and_compile_output(result.execution_id)
    if pac is None:
        print("(!) No PLAN_AND_COMPILE task found in workflow tree —"
              " did the server pick up the new bean?")
        return 1

    print("--- PLAN_AND_COMPILE output ---")
    print(f"error:         {pac.get('error')!r}")
    print(f"workflowName:  {pac.get('workflowName')}")
    stats = pac.get("stats") or {}
    print(f"stats:         stepCount={stats.get('stepCount')}, taskCount={stats.get('taskCount')}")
    warnings = pac.get("warnings") or []
    if warnings:
        print(f"warnings:      {warnings}")

    wf_def = pac.get("workflowDef") or {}
    top_tasks = wf_def.get("tasks") or []
    print(f"\ntop-level tasks in compiled WorkflowDef ({len(top_tasks)}):")
    for t in top_tasks:
        print(f"  - {t.get('type'):12s} ref={t.get('taskReferenceName')}")

    return 0 if result.status == "COMPLETED" and not pac.get("error") else 1


if __name__ == "__main__":
    sys.exit(main())
