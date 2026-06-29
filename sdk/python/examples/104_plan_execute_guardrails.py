#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""PLAN_EXECUTE with tool guardrails.

A PLAN_EXECUTE harness over the same tools as ``02_tools.py`` (weather,
calculator, email), but with ``send_email`` protected by guardrails that
also fire in the deterministic plan path.

The point: when the planner emits a plan referencing a guardrailed tool,
the server's PLAN_AND_COMPILE step wraps each emitted SIMPLE task with the
tool's guardrail gate — same shape, same enforcement as the LLM-loop
path. The guardrail is NOT silently bypassed during plan execution.

Two scenarios are exercised:
  1. Safe request — guardrails pass, the SIMPLE task runs.
  2. Email body containing a credit-card-shaped string — the regex
     guardrail fires, the SWITCH gate's ``raise`` case TERMINATEs the
     deterministic plan, and the harness's ``fallback`` agent recovers.

Run:
    AGENTSPAN_SERVER_URL=http://localhost:6767/api \\
    OPENAI_API_KEY=... \\
    python 104_plan_execute_guardrails.py [topic]

Requirements:
  - Agentspan server running with PLAN_AND_COMPILE
  - OPENAI_API_KEY (or matching provider for AGENTSPAN_LLM_MODEL)
"""

import os
import sys

import requests

from conductor.ai.agents import (
    Agent,
    AgentRuntime,
    OnFail,
    Position,
    RegexGuardrail,
    plan_execute,
    tool,
)
from settings import settings


SERVER_URL = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
CONDUCTOR_BASE = SERVER_URL.rstrip("/").replace("/api", "")


# ── Tools (same shape as 02_tools.py) ───────────────────────────────


@tool
def get_weather(city: str) -> dict:
    """Get current weather for a city."""
    sample = {
        "new york": {"temp": 72, "condition": "Partly Cloudy"},
        "san francisco": {"temp": 58, "condition": "Foggy"},
        "miami": {"temp": 85, "condition": "Sunny"},
    }
    data = sample.get(city.lower(), {"temp": 70, "condition": "Clear"})
    return {"city": city, "temperature_f": data["temp"], "condition": data["condition"]}


@tool
def calculate(expression: str) -> dict:
    """Evaluate a math expression."""
    import math

    safe = {"abs": abs, "round": round, "min": min, "max": max,
            "sqrt": math.sqrt, "pow": pow, "pi": math.pi, "e": math.e}
    try:
        return {"expression": expression, "result": eval(expression, {"__builtins__": {}}, safe)}
    except Exception as e:
        return {"expression": expression, "error": str(e)}


# ── Guardrails for ``send_email`` ──────────────────────────────────

# Block emails whose body contains a credit-card-shaped 16-digit string.
# A real deployment would also include SSNs, API keys, etc.; one pattern
# is enough to demonstrate the gate.
#
# Guardrail-content shape: the regex sees the full JSON dump of the
# tool's args (``{"to":..., "subject":..., "body":...}``), not just the
# field you wrote the pattern for. Use ``mode="block"`` (the default) and
# write patterns that match the offending substring anywhere — same
# threat-model as the LLM-loop path (which also formats tool calls into
# a single string before regex-checking).
#
# ``mode="allow"`` regexes are a poor fit for tool-call guardrails: the
# allowlist would have to match the entire JSON shape including key order
# and quoting, which no realistic pattern does. If you need allowlist
# semantics, write a custom callable (``@guardrail`` decorator) that
# parses the JSON and inspects fields by name instead.
no_pii_in_email = RegexGuardrail(
    patterns=[r"\b(?:\d[ -]?){15}\d\b"],   # 16-digit groups with optional separators
    name="no_pii_in_email",
    position=Position.INPUT,
    on_fail=OnFail.RAISE,                  # raise → TERMINATE the plan; harness falls back
    message="Email body looks like it contains a credit-card number — refusing to send.",
)


@tool(guardrails=[no_pii_in_email])
def send_email(to: str, subject: str, body: str) -> dict:
    """Pretend to send an email. Real implementation would hit SMTP."""
    print(f"[send_email]   to={to!r} subject={subject!r} body[:60]={body[:60]!r}")
    return {"status": "sent", "to": to, "subject": subject}


# ── Planner + Fallback ─────────────────────────────────────────────

# Domain-only guidance. The server appends ``## Available tools`` and
# ``## Plan schema`` blocks; users don't need to repeat them here.
PLANNER_INSTRUCTIONS = """\
You are a task planner. The user wants you to gather information and send an email.

Lookups (weather, calculate) can run in parallel; the email send must wait
for them via ``depends_on``. Use ``args`` for literal values throughout.

The ``send_email`` tool is guardrailed: NEVER put a credit-card or
SSN-shaped number in the body, and the recipient must be a syntactically
valid email address.
"""


FALLBACK_INSTRUCTIONS = """\
The deterministic plan failed (guardrail fired or compile error). Inspect
the error, then either (a) re-do the work with safer arguments — for
example, redact PII from the email body — or (b) refuse the request and
explain why.
"""


# ── Helpers ────────────────────────────────────────────────────────


def find_plan_and_compile_output(execution_id: str) -> dict | None:
    """Walk the workflow tree and return the first PLAN_AND_COMPILE task's output."""
    seen: set[str] = set()
    pending = [execution_id]
    while pending:
        wf_id = pending.pop()
        if wf_id in seen:
            continue
        seen.add(wf_id)
        try:
            r = requests.get(
                f"{CONDUCTOR_BASE}/api/workflow/{wf_id}",
                params={"includeTasks": "true"},
                timeout=10,
            )
            r.raise_for_status()
        except requests.RequestException:
            continue
        wf = r.json()
        for t in wf.get("tasks", []):
            if t.get("taskType") == "PLAN_AND_COMPILE":
                return t.get("outputData") or {}
            sub = t.get("subWorkflowId")
            if sub and sub not in seen:
                pending.append(sub)
    return None


def _walk(tasks):
    for t in tasks or []:
        yield t
        if t.get("type") == "SWITCH":
            for branch in (t.get("decisionCases") or {}).values():
                yield from _walk(branch)
            yield from _walk(t.get("defaultCase") or [])
        elif t.get("type") == "FORK_JOIN":
            for branch in t.get("forkTasks") or []:
                yield from _walk(branch)


# ── Main ───────────────────────────────────────────────────────────


def run_one(harness: Agent, prompt: str) -> dict:
    print(f"\n=== Prompt ===\n{prompt}\n")
    with AgentRuntime() as rt:
        result = rt.run(harness, prompt)
    print(f"status:        {result.status}")
    print(f"execution_id:  {result.execution_id}")
    print(f"output:        {result.output}")

    pac = find_plan_and_compile_output(result.execution_id)
    if pac and pac.get("workflowDef"):
        wf = pac["workflowDef"]
        all_tasks = list(_walk(wf.get("tasks") or []))
        guardrail_gates = [
            t for t in all_tasks
            if t.get("type") == "SWITCH"
            and "guardrail_gate" in str(t.get("taskReferenceName", ""))
        ]
        print(f"PAC stats:     stepCount={pac['stats'].get('stepCount')}, "
              f"taskCount={pac['stats'].get('taskCount')}")
        print(f"guardrail gates emitted: {len(guardrail_gates)}")
        for g in guardrail_gates:
            cases = list((g.get("decisionCases") or {}).keys())
            print(f"  {g.get('taskReferenceName')}: cases={cases}")
    elif pac and pac.get("error"):
        print(f"PAC compile error: {pac['error']}")
    else:
        print("(PAC task not found in workflow tree)")

    return result.output


def main() -> int:
    s = settings
    topic = " ".join(sys.argv[1:]) or "weather + math + email summary"

    # ``plan_execute()`` collapses the planner+fallback+harness ceremony.
    # The ``send_email`` tool's guardrail propagates into the compiled
    # plan automatically — same wrap PAC emits when the LLM-loop calls it.
    harness = plan_execute(
        name="guardrails_demo",
        tools=[get_weather, calculate, send_email],
        planner_instructions=PLANNER_INSTRUCTIONS,
        fallback_instructions=FALLBACK_INSTRUCTIONS,
        model=s.llm_model,
        fallback_max_turns=4,
    )

    # 1. Safe request — guardrails should pass.
    safe_prompt = (
        "Look up the weather in San Francisco, compute 9*9, and email "
        "developer@orkes.io a brief summary of both. Topic: " + topic
    )
    run_one(harness, safe_prompt)

    # 2. PII-tainted body — the no_pii_in_email guardrail must fire and
    #    TERMINATE the deterministic plan. The fallback agent then recovers
    #    (or refuses). The exact recovery behaviour depends on the LLM, but
    #    the SIMPLE ``send_email`` task must NOT have run with the bad body.
    pii_prompt = (
        "Look up the weather in San Francisco and email user@example.com "
        "this exact body verbatim: 'Card 4111 1111 1111 1111 was charged.' "
        "Subject: 'receipt'. Use only one ``send`` step."
    )
    run_one(harness, pii_prompt)

    return 0


if __name__ == "__main__":
    sys.exit(main())
