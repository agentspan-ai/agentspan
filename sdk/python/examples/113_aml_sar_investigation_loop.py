#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""113 — AML / SAR investigation loop with real PAC + SUB_WORKFLOW per turn.

A BSA/AML alert fires on a customer (structuring pattern). An
investigator-agent runs inside a single Conductor workflow whose body is a
DO_WHILE. Each iteration the planner LLM picks the next-best investigative
thread, PAC compiles that pick into a sub-workflow, the SUB_WORKFLOW runs
the corresponding evidence-source tool, the result joins the running
case file, and the loop continues. When the planner judges it has enough
evidence, it picks the ``finalize_disposition`` action — that tool's
output flips a ``finalized`` flag and the DO_WHILE exits.

The loop demonstrates the canonical PAE meta-planning pattern:
**iteration N+1's plan depends on the actual findings of iteration N**.
There's no fixed investigation cascade — the agent's next query is
genuinely conditional on what the prior queries returned, and on the
red-flag taxonomy applied so far.

What you'll see:
  * ONE workflow ID for the whole investigation.
  * planner_llm__N / plan_and_compile__N / plan_exec__N / ... task
    suffixes per iteration.
  * Case-file state accumulates in workflow.variables across iterations.
  * Termination on whichever iteration the planner emits
    ``finalize_disposition``.

Requirements:
  - AGENTSPAN_SERVER_URL=http://localhost:6767/api (default)
  - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini (default)
  - LLM key for the chosen model.
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
MAX_ITER = int(os.environ.get("AGENTSPAN_AML_MAX_ITER", "10"))
WORKFLOW_NAME = "aml_sar_investigation_loop"
WORKFLOW_VERSION = 5


def _model_split(model: str) -> tuple[str, str]:
    if "/" in model:
        provider, name = model.split("/", 1)
        return provider, name
    return "openai", model


PROVIDER, MODEL_NAME = _model_split(MODEL)


# ── Synthetic alert and evidence corpus ──────────────────────────
# The investigation is set up so the LLM has to actually consult multiple
# sources: the structuring pattern in transactions is a red flag, but
# without the KYC baseline (expected behavior) + the counterparty graph
# (single overseas destination) + adverse media (sector-specific
# trade-based ML reports) the case isn't airtight. The "world-check"
# negative finding teaches the LLM that absence of sanctions hits is
# NOT exoneration.


ALERT = {
    "alert_id": "AML-2026-0521-0042",
    "customer_id": "CUST-7821",
    "rule_name": "structuring_pattern",
    "summary": (
        "8 cash deposits between $9,000 and $9,500 over 5 business days; total $73,200. "
        "All under the $10,000 CTR threshold."
    ),
    "total_amount": 73200,
    "window_start": "2026-05-15",
    "window_end": "2026-05-19",
}


EVIDENCE_DB = {
    "transactions:CUST-7821": {
        "summary": (
            "8 cash deposits between $9,000-$9,500 across 3 branches over 5 days. "
            "100% followed by one outbound wire on day 6."
        ),
        "cash_deposits": [
            {"date": "2026-05-15", "amount": 9500, "branch": "NYC-12"},
            {"date": "2026-05-15", "amount": 9200, "branch": "NYC-12"},
            {"date": "2026-05-16", "amount": 9300, "branch": "NYC-04"},
            {"date": "2026-05-16", "amount": 9100, "branch": "NYC-04"},
            {"date": "2026-05-17", "amount": 9400, "branch": "NJ-21"},
            {"date": "2026-05-17", "amount": 9050, "branch": "NJ-21"},
            {"date": "2026-05-18", "amount": 9450, "branch": "NYC-12"},
            {"date": "2026-05-19", "amount": 9200, "branch": "NJ-21"},
        ],
        "outgoing": [
            {
                "date": "2026-05-20",
                "amount": 73000,
                "type": "wire",
                "destination": "PA Logistics SDN BHD, Penang, Malaysia",
            }
        ],
    },
    "kyc:CUST-7821": {
        "legal_name": "ACME Logistics Inc.",
        "incorporation": "Delaware, 2024-01-12",
        "industry_code": "488510 - Freight Transportation Arrangement",
        "expected_monthly_volume_usd": 50000,
        "expected_cash_pct_of_volume": 0.05,
        "beneficial_owners": [
            {"name": "John Doe", "pct": 75, "country": "USA"},
            {"name": "Jane Smith", "pct": 25, "country": "USA"},
        ],
        "address": "123 Main St, Suite 4B, Wilmington DE",
        "kyc_review_date": "2024-03-15",
        "edd_flag": False,
        "expected_counterparties_geo": ["USA", "Canada"],
    },
    "world_check:ACME Logistics Inc.": {
        "name_searched": "ACME Logistics Inc.",
        "sanctions_matches": [],
        "pep_matches": [],
        "ubo_matches_searched": ["John Doe", "Jane Smith"],
        "adverse_media_count": 0,
        "interpretation": "No sanctions, PEP, or adverse-media hits at the entity or UBO level.",
    },
    "adverse_media:CUST-7821": {
        "search_terms": ["freight forwarders", "Malaysia", "trade-based money laundering"],
        "hits": [
            {
                "date": "2026-03-15",
                "source": "Reuters",
                "headline": "Trade-based money laundering surges via Malaysia freight-forwarders",
                "summary": (
                    "Investigators warn that small US freight-forwarder shells are "
                    "increasingly used to layer cash through routine-looking trade "
                    "payments to Malaysia-based shell counterparties."
                ),
            },
            {
                "date": "2026-04-22",
                "source": "FinCEN advisory FIN-2026-A007",
                "headline": "Advisory on Malaysia trade-based laundering typology",
                "summary": (
                    "Typology: small freight-forwarders in DE/NJ/NY incorporate, accept "
                    "structured cash deposits, then wire to Penang-area counterparties."
                ),
            },
        ],
    },
    "counterparty_network:CUST-7821": {
        "outbound_30d": [
            {
                "name": "PA Logistics SDN BHD",
                "country": "Malaysia",
                "city": "Penang",
                "wire_count": 1,
                "total_amount_usd": 73000,
                "first_seen_with_customer": "2026-05-20",
                "world_check_status": "shell - no operating evidence",
            }
        ],
        "inbound_30d": [
            {
                "type": "cash_deposit",
                "branch_count": 3,
                "total_amount_usd": 73200,
                "count": 8,
                "all_under_10k_threshold": True,
            }
        ],
        "concentration_warning": (
            "100% of customer's inbound activity is cash, all deposits just below "
            "the $10K CTR reporting threshold. 100% of outbound is to a single "
            "newly-introduced overseas counterparty whose own profile suggests it "
            "may be a shell. Pattern matches the FinCEN typology in adverse media."
        ),
    },
}


# ── Evidence-source tools (stubbed) ──────────────────────────────


@tool
def query_transactions(customer_id: str, window_days: int = 30) -> dict:
    """Pull the customer's recent transactions over the requested window.

    Returns a structured summary plus the raw deposit + wire records that
    drove the alert. In a real deployment this hits the core banking
    system's transaction log.
    """
    data = EVIDENCE_DB.get(f"transactions:{customer_id}", {})
    return {"result": data or {"error": f"no transactions for {customer_id}"}}


@tool
def query_kyc_profile(customer_id: str) -> dict:
    """Pull CIP/CDD profile — expected behavior baseline, UBOs, EDD flag."""
    data = EVIDENCE_DB.get(f"kyc:{customer_id}", {})
    return {"result": data or {"error": f"no KYC for {customer_id}"}}


@tool
def query_world_check(name: str) -> dict:
    """Sanctions / PEP / adverse-media DB lookup by legal name."""
    # Try exact match, then any key containing the queried name.
    key = f"world_check:{name}"
    if key in EVIDENCE_DB:
        return {"result": EVIDENCE_DB[key]}
    for k, v in EVIDENCE_DB.items():
        if k.startswith("world_check:") and name.lower() in k.lower():
            return {"result": v}
    return {
        "result": {
            "name_searched": name,
            "sanctions_matches": [],
            "pep_matches": [],
            "adverse_media_count": 0,
            "interpretation": "No hits.",
        }
    }


@tool
def query_adverse_media(customer_id: str, keywords: str = "") -> dict:
    """News + regulator-advisory search keyed to the customer's industry + geos."""
    data = EVIDENCE_DB.get(f"adverse_media:{customer_id}", {"hits": []})
    return {"result": data}


@tool
def query_counterparty_network(customer_id: str, depth: int = 1) -> dict:
    """Transaction-counterparty graph for the customer, 1-hop by default."""
    data = EVIDENCE_DB.get(f"counterparty_network:{customer_id}", {})
    return {"result": data or {"error": f"no graph for {customer_id}"}}


@tool
def finalize_disposition(
    disposition: str,
    narrative: str,
    red_flags: list,
    supporting_evidence: list,
) -> dict:
    """Close the investigation with a structured disposition.

    Disposition must be one of: ``clear`` (false positive), ``escalate``
    (route to L2 for further review), ``sar_eligible`` (file a SAR).
    The narrative addresses the 5W1H. Red flags reference the BSA
    red-flag taxonomy. The ``finalized: true`` field is what the
    outer DO_WHILE checks to terminate.
    """
    return {
        "result": {
            "finalized": True,
            "disposition": disposition,
            "narrative": narrative,
            "red_flags": list(red_flags) if red_flags else [],
            "supporting_evidence": list(supporting_evidence) if supporting_evidence else [],
        }
    }


TOOLS_LIST = [
    query_transactions,
    query_kyc_profile,
    query_world_check,
    query_adverse_media,
    query_counterparty_network,
    finalize_disposition,
]


# ── INLINE script bodies (GraalJS) ────────────────────────────────
#
# Conductor's INLINE GraalJS sees nested ``${task.output.X}`` values as
# Java Maps / Lists, NOT as JS objects. ``JSON.stringify`` on a Java Map
# returns ``{}`` because Map fields don't enumerate as own properties of
# the JS proxy. Every INLINE that constructs JSON has to walk and unwrap
# Java collections first. ``TO_JS_OBJ_JS`` is the shared helper.

TO_JS_OBJ_JS = (
    "function toJSObj(v) {"
    "  if (v === null || v === undefined) return v;"
    "  if (typeof v !== 'object') return v;"
    "  if (typeof v.keySet === 'function' && typeof v.get === 'function') {"
    "    var out = {};"
    "    var it = v.keySet().iterator();"
    "    while (it.hasNext()) { var k = it.next(); out[String(k)] = toJSObj(v.get(k)); }"
    "    return out;"
    "  }"
    "  if (typeof v.iterator === 'function' && typeof v.size === 'function'"
    "      && typeof v.keySet !== 'function') {"
    "    var arr = [];"
    "    var lit = v.iterator();"
    "    while (lit.hasNext()) arr.push(toJSObj(lit.next()));"
    "    return arr;"
    "  }"
    "  if (Array.isArray(v)) return v.map(toJSObj);"
    "  var keys = Object.keys(v);"
    "  var out2 = {};"
    "  for (var i = 0; i < keys.length; i++) out2[keys[i]] = toJSObj(v[keys[i]]);"
    "  return out2;"
    "}"
)


# Pull the JSON action out of the LLM's response. Two shapes possible:
# (a) Agentspan's LLM_CHAT_COMPLETE auto-parses a JSON-mode response, so
#     ``$.llm_out`` is already a Java Map. Walk it to a JS object.
# (b) Plaintext path: ``$.llm_out`` is a string; regex out the JSON block.
EXTRACT_ACTION_JS = TO_JS_OBJ_JS + (
    "(function() {"
    "  var r = $.llm_out;"
    "  if (r === null || r === undefined) return null;"
    "  if (typeof r === 'object') return toJSObj(r);"
    "  var s = String(r);"
    "  var m = s.match(/\\{[\\s\\S]*\\}/);"
    "  if (!m) return null;"
    "  try { return JSON.parse(m[0]); }"
    "  catch (e) { return null; }"
    "})();"
)


# Wrap the planner's chosen action into a one-step plan PAC can compile.
# ``$.action`` arrives as a Java Map (most common) or string. Walk it via
# toJSObj before any JSON.stringify, or the args dict serializes as ``{}``.
BUILD_PLAN_JS = TO_JS_OBJ_JS + (
    "(function() {"
    "  var raw = $.action;"
    "  var a;"
    "  if (raw === null || raw === undefined) { a = {}; }"
    "  else if (typeof raw === 'string') {"
    "    try { a = JSON.parse(raw); } catch(e) { a = {}; }"
    "  } else { a = toJSObj(raw); }"
    "  var tool = a.tool || 'query_kyc_profile';"
    "  var args = a.args || {};"
    "  if (tool === 'query_kyc_profile' && !args.customer_id) {"
    "    args.customer_id = 'CUST-7821';"
    "  }"
    "  var plan = {steps: [{id: 'step', operations: [{tool: tool, args: args}]}]};"
    "  return JSON.stringify(plan);"
    "})();"
)


# Pull the single op's result from the compiled sub-workflow's output.
# PAC emits ``outputParameters.result = ${last_op.output.result}``; since
# our tools return ``{"result": {...}}`` the sub-workflow's
# ``output.result`` is the inner dict.
EXTRACT_RESULT_JS = TO_JS_OBJ_JS + (
    "(function() {"
    "  var ex = $.exec_output;"
    "  if (!ex) return {finalized: false, error: 'no exec output'};"
    "  var result = ex.result;"
    "  if (result && typeof result === 'object') return toJSObj(result);"
    "  if (typeof result === 'string') {"
    "    try { return JSON.parse(result); } catch(e) {}"
    "  }"
    "  return {finalized: false, error: 'unparseable result'};"
    "})();"
)


# Human-readable summary for the workflow's top-level ``output.result``
# so Conductor UIs render the disposition + narrative prominently.
SUMMARIZE_JS = TO_JS_OBJ_JS + (
    "(function() {"
    "  var fs = $.final_state ? toJSObj($.final_state) : {};"
    "  var n = $.iter_count;"
    "  var lines = [];"
    "  lines.push('AML/SAR investigation — ' + ($.alert_id || ''));"
    "  lines.push('Iterations: ' + n);"
    "  var disp = (fs.disposition || 'unknown').toUpperCase();"
    "  lines.push('Disposition: ' + disp);"
    "  var rf = fs.red_flags || [];"
    "  if (rf.length > 0) {"
    "    lines.push('Red flags (' + rf.length + '):');"
    "    for (var i = 0; i < rf.length; i++) lines.push('  - ' + rf[i]);"
    "  }"
    "  var se = fs.supporting_evidence || [];"
    "  if (se.length > 0) {"
    "    lines.push('Supporting evidence (' + se.length + '):');"
    "    for (var j = 0; j < se.length; j++) lines.push('  - ' + se[j]);"
    "  }"
    "  if (fs.narrative) {"
    "    lines.push('');"
    "    lines.push('Narrative:');"
    "    lines.push(fs.narrative);"
    "  }"
    "  return lines.join('\\n');"
    "})();"
)


# Push the iteration's (tool, args, result) onto the running case file.
# All inputs may be Java Maps/Lists; walk via toJSObj before serialization.
APPEND_CASE_FILE_JS = TO_JS_OBJ_JS + (
    "(function() {"
    "  function unwrap(v) {"
    "    if (v === null || v === undefined) return null;"
    "    if (typeof v === 'string') {"
    "      try { return JSON.parse(v); } catch(e) { return v; }"
    "    }"
    "    return toJSObj(v);"
    "  }"
    "  var cf = unwrap($.case_file) || [];"
    "  if (!Array.isArray(cf)) cf = [];"
    "  var act = unwrap($.action) || {};"
    "  var res = unwrap($.result) || {};"
    "  cf.push({"
    "    iter: $.iter,"
    "    tool: act.tool || '<unknown>',"
    "    args: act.args || {},"
    "    result: res"
    "  });"
    "  return cf;"
    "})();"
)


# ── Planner prompt rendering ─────────────────────────────────────


PLANNER_SYSTEM = (
    "You are a BSA/AML compliance investigator. An alert has been raised on a "
    "customer. You have access to 5 evidence-source tools and 1 finalize tool. "
    "Each iteration, decide whether to (a) consult the next-best evidence source "
    "to narrow the disposition, or (b) finalize the investigation.\n\n"
    "Respond with ONLY a JSON object — no prose, no markdown fences. Two shapes:\n\n"
    "  Investigate further:\n"
    "  {\"tool\": \"<one of: query_transactions, query_kyc_profile, query_world_check, "
    "query_adverse_media, query_counterparty_network>\", \"args\": { ... }}\n\n"
    "  Finalize:\n"
    "  {\"tool\": \"finalize_disposition\", \"args\": {\"disposition\": "
    "\"clear|escalate|sar_eligible\", \"narrative\": \"<5W1H narrative>\", "
    "\"red_flags\": [\"<bsa red flag>\", ...], \"supporting_evidence\": "
    "[\"<source citations>\", ...]}}\n\n"
    "Disposition guide:\n"
    "  clear        — alert is a false positive; activity is consistent with KYC.\n"
    "  escalate     — suspicious but not strong enough for SAR; refer to L2.\n"
    "  sar_eligible — pattern strongly indicates suspicious activity meriting a SAR.\n\n"
    "Investigate broadly — pull KYC, transactions, world-check, adverse media, AND "
    "counterparty graph before finalizing unless any single source already "
    "definitively closes the case. Do not repeat a query you have already run."
)


PLANNER_USER_TEMPLATE = (
    "Alert under investigation:\n${workflow.input.alert_json}\n\n"
    "Iteration: ${loop.output.iteration}.\n"
    "Case file so far (your prior tool calls + results):\n"
    "${workflow.variables.case_file}\n\n"
    "Choose your next action. Emit ONLY the JSON object."
)


# ── Workflow definition ───────────────────────────────────────────


def build_workflow_def(tool_defs: list[dict]) -> dict:
    """One Conductor WorkflowDef whose body is a DO_WHILE wrapping the
    full plan → compile → execute → review cycle. The planner's chosen
    tool is dispatched via the real PAC + SUB_WORKFLOW pair per turn.
    """
    parent_tools = list(tool_defs)
    known_tool_names = [t["name"] for t in tool_defs]

    return {
        "name": WORKFLOW_NAME,
        "version": WORKFLOW_VERSION,
        "description": "AML/SAR investigation loop — DO_WHILE wraps PAC + SUB_WORKFLOW",
        "tasks": [
            {
                "name": "SET_VARIABLE",
                "taskReferenceName": "init",
                "type": "SET_VARIABLE",
                "inputParameters": {
                    "case_file": [],
                    "alert_json": "${workflow.input.alert_json}",
                },
            },
            {
                "name": "DO_WHILE",
                "taskReferenceName": "loop",
                "type": "DO_WHILE",
                "inputParameters": {
                    "loop": "${loop}",
                    "extract_result": "${extract_result}",
                },
                "loopCondition": (
                    f"if ($.loop['iteration'] < {MAX_ITER} "
                    f"&& $.extract_result['result']['finalized'] != true) "
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
                            "maxTokens": 600,
                            "messages": [
                                {"role": "system", "message": PLANNER_SYSTEM},
                                {"role": "user", "message": PLANNER_USER_TEMPLATE},
                            ],
                        },
                    },
                    {
                        "name": "INLINE",
                        "taskReferenceName": "extract_action",
                        "type": "INLINE",
                        "inputParameters": {
                            "evaluatorType": "graaljs",
                            "expression": EXTRACT_ACTION_JS,
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
                            "action": "${extract_action.output.result}",
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
                            "knownToolNames": known_tool_names,
                            "parentTools": parent_tools,
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
                            "prompt": "${workflow.input.alert_json}",
                        },
                        "optional": True,
                    },
                    {
                        "name": "INLINE",
                        "taskReferenceName": "extract_result",
                        "type": "INLINE",
                        "inputParameters": {
                            "evaluatorType": "graaljs",
                            "expression": EXTRACT_RESULT_JS,
                            "exec_output": "${plan_exec.output}",
                        },
                    },
                    {
                        "name": "INLINE",
                        "taskReferenceName": "append_case_file",
                        "type": "INLINE",
                        "inputParameters": {
                            "evaluatorType": "graaljs",
                            "expression": APPEND_CASE_FILE_JS,
                            "case_file": "${workflow.variables.case_file}",
                            "iter": "${loop.output.iteration}",
                            "action": "${extract_action.output.result}",
                            "result": "${extract_result.output.result}",
                        },
                    },
                    {
                        "name": "SET_VARIABLE",
                        "taskReferenceName": "update_state",
                        "type": "SET_VARIABLE",
                        "inputParameters": {
                            "case_file": "${append_case_file.output.result}",
                            "alert_json": "${workflow.variables.alert_json}",
                        },
                    },
                ],
            },
            # Post-loop: build the human-readable summary the UI surfaces.
            {
                "name": "INLINE",
                "taskReferenceName": "summarize",
                "type": "INLINE",
                "inputParameters": {
                    "evaluatorType": "graaljs",
                    "expression": SUMMARIZE_JS,
                    "final_state": "${extract_result.output.result}",
                    "iter_count": "${loop.output.iteration}",
                    "alert_id": "${workflow.input.alert_id}",
                },
            },
        ],
        "inputParameters": ["alert_json", "alert_id"],
        "outputParameters": {
            "result": "${summarize.output.result}",
            "iterations": "${loop.output.iteration}",
            "final_disposition": "${extract_result.output.result}",
            "case_file": "${workflow.variables.case_file}",
        },
        "schemaVersion": 2,
        "ownerEmail": "demo@example.com",
    }


# ── Server interactions ───────────────────────────────────────────


def register_workflow(wf: dict) -> None:
    r = requests.post(
        f"{BASE}/api/metadata/workflow",
        json=[wf],
        headers={"Content-Type": "application/json"},
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


def start_execution(alert: dict) -> str:
    r = requests.post(
        f"{BASE}/api/workflow/{WORKFLOW_NAME}?version={WORKFLOW_VERSION}",
        json={
            "alert_json": json.dumps(alert),
            "alert_id": alert.get("alert_id", ""),
        },
        headers={"Content-Type": "application/json"},
    )
    r.raise_for_status()
    return r.text.strip().strip('"')


def poll_until_done(execution_id: str, timeout: int = 600) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(f"{BASE}/api/workflow/{execution_id}?includeTasks=true")
        r.raise_for_status()
        wf = r.json()
        if wf.get("status") in ("COMPLETED", "FAILED", "TERMINATED", "TIMED_OUT"):
            return wf
        time.sleep(2)
    raise TimeoutError(f"workflow {execution_id} did not complete in {timeout}s")


# ── Pretty printing ──────────────────────────────────────────────


def print_investigation_trace(wf: dict) -> None:
    """One row per investigation step: which source the LLM queried + a
    one-line gist of what came back. Final row shows the disposition."""
    tasks = wf.get("tasks", [])
    suffix_re = re.compile(r"^(.+?)__(\d+)$")
    by_iter: dict[int, dict] = {}
    for t in tasks:
        ref = t.get("referenceTaskName", "")
        m = suffix_re.match(ref)
        if not m:
            continue
        base, n = m.group(1), int(m.group(2))
        by_iter.setdefault(n, {})[base] = t

    def _parse_maybe(v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return {}
        return v or {}

    print(f"{'iter':>5}  {'action':<26}  {'outcome (gist)'}")
    print("─" * 95)
    for n in sorted(by_iter):
        row = by_iter[n]
        action_task = row.get("extract_action", {})
        action = _parse_maybe((action_task.get("outputData", {}) or {}).get("result"))
        tool_name = action.get("tool", "?") if isinstance(action, dict) else "?"
        result_task = row.get("extract_result", {})
        result = _parse_maybe((result_task.get("outputData", {}) or {}).get("result"))
        if not isinstance(result, dict):
            result = {"raw": str(result)}

        if tool_name == "finalize_disposition":
            disposition = result.get("disposition") or "?"
            gist = f"→ DISPOSITION: {str(disposition).upper()}"
        elif "error" in result:
            gist = f"error: {result['error']}"
        else:
            r_str = json.dumps(result, ensure_ascii=False)
            gist = (r_str[:90] + "…") if len(r_str) > 90 else r_str
        print(f"{n:>5}  {tool_name:<26}  {gist}")


def main(argv: list[str]) -> None:
    print(f"server: {BASE}")
    print(f"model:  {MODEL}\n")
    print(f"alert:  {ALERT['alert_id']} — {ALERT['rule_name']}")
    print(f"        customer={ALERT['customer_id']}, ${ALERT['total_amount']:,} over 5 days")
    print(f"budget: {MAX_ITER} iterations\n")

    # Register the workers via Agentspan runtime.
    print("setting up evidence-source workers via AgentRuntime...")
    harness = plan_execute(
        name="aml_tools_harness",
        tools=TOOLS_LIST,
        planner_instructions="(unused — workflow def is hand-built)",
        model=MODEL,
    )

    from conductor.ai.agents.config_serializer import AgentConfigSerializer

    ac = AgentConfigSerializer().serialize(harness)
    tool_defs = ac.get("tools", [])
    if not tool_defs:
        raise RuntimeError("could not serialize tools")

    with AgentRuntime() as runtime:
        runtime.serve(harness, blocking=False)
        print(f"  workers serving: {[t.__name__ for t in TOOLS_LIST]}\n")

        wf_def = build_workflow_def(tool_defs)
        print("registering workflow def...")
        register_workflow(wf_def)
        print(f"  OK: {WORKFLOW_NAME} v{WORKFLOW_VERSION}\n")

        print("starting investigation...")
        execution_id = start_execution(ALERT)
        print(f"  execution_id: {execution_id}\n")

        print("polling until done...")
        wf = poll_until_done(execution_id)
        print(f"  status: {wf['status']}\n")

    output = wf.get("output", {}) or {}
    final = output.get("final_disposition") or {}
    print("── investigation trace (one row per iteration) ──")
    print_investigation_trace(wf)
    print()

    print("── final disposition ─────────────────────────────────")
    disposition = final.get("disposition") or "?"
    print(f"  disposition: {str(disposition).upper()}")
    print(f"  iterations:  {output.get('iterations')}")
    rf = final.get("red_flags") or []
    if rf:
        print(f"  red flags ({len(rf)}):")
        for r_ in rf:
            print(f"    - {r_}")
    se = final.get("supporting_evidence") or []
    if se:
        print(f"  supporting evidence ({len(se)}):")
        for e in se:
            print(f"    - {e}")
    if final.get("narrative"):
        print()
        print("  narrative:")
        for line in str(final["narrative"]).split("\n"):
            print(f"    {line}")

    print(f"\ninspect: curl {BASE}/api/workflow/{execution_id}?includeTasks=true | jq .")


if __name__ == "__main__":
    main(sys.argv)
